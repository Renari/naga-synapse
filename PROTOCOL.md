# Razer Naga V2 Pro protocol notes

Everything here was checked against a Naga V2 Pro (wired, PID `0x00a7`) on
firmware 1.03.00 and again after updating to 3.00.00. Both versions behave the
same for everything below. The original Naga Pro uses the same protocol; its
differences are listed in [Naga Pro (2020)](#naga-pro-2020) at the end.

## Transport

- Control interface: USB interface 0 (`/dev/hidrawN` whose descriptor has a
  vendor page `0xFF00` feature report of 90 bytes).
- Every command is a 90-byte feature report (report id 0): send with
  `HIDIOCSFEATURE`, then poll `HIDIOCGFEATURE` until the status is no longer
  busy.

| offset | field |
|---|---|
| 0 | status: 0 new, 1 busy, 2 ok, 3 fail, 4 timeout, 5 unsupported |
| 1 | transaction id, `0x1f` |
| 2–3 | remaining packets (0) |
| 4 | protocol type (0) |
| 5 | data size |
| 6 | command class |
| 7 | command id (bit 7 set = read) |
| 8–87 | arguments |
| 88 | CRC = XOR of bytes 2..87 |

Commands are written below as `class:id`. Profile slot `0` is a volatile
"direct" profile, and slots `1`–`5` are the onboard profiles.

## Device

| cmd | args → response |
|---|---|
| `00:81` | → firmware `maj min patch 0` |
| `00:82` | → serial (16 ASCII bytes) |
| `00:8e` / `00:0e` | `slot` → `slot interval` (1 = 1000 Hz, 2 = 500, 8 = 125) |
| `02:84` | → `count ids…` remappable buttons (30) |
| `07:80` | → `? level` (battery 0–255) |
| `07:84` | → `? charging` |
| `07:83` / `07:03` | idle time, seconds, big endian (60–900) |
| `07:81` / `07:01` | low battery threshold (percent × 255 / 100) |

## Profiles

| cmd | args → response |
|---|---|
| `05:8a` | → total slots (5) |
| `05:80` | → number of enabled profiles |
| `05:81` | → `5 slot slot…` enabled profiles |
| `05:84` / `05:04` | active profile |
| `05:02` | `slot` create |
| `05:03` | `slot` delete |
| `05:88` | `slot start(2)` → `slot start(2) total(2) data(64)` metadata |
| `05:08` | `slot start(2) total(2) data…` write metadata (uses one flash page) |

A newly created profile starts with the factory bindings, and its DPI stages
are 400/800/1600/3200/6400.

## Buttons

`02:8c` reads and `02:0c` writes `slot button layer fn(7)`. Layer 0 is
standard and layer 1 is Hypershift.

Button ids:

| id | button |
|---|---|
| `01` `02` `03` | left, right, wheel click |
| `09` `0a` | wheel up, wheel down |
| `34` `35` | tilt left, tilt right |
| `6d` | scroll-mode button |
| `60` | DPI button |
| `0e` | bottom button |
| `05` `04` | 2-button plate: front, rear |
| `50`–`55` | 6-button plate keys 1–6 |
| `40`–`4b` | 12-button plate keys 1–12 |

The function is `class len data[5]`. The factory defaults always store `len` = 1,
so derive the payload size from the class.

| class | data |
|---|---|
| `00` | disabled |
| `01` | mouse: `button` (1 L, 2 R, 3 M, 4 back, 5 fwd, 9/0a wheel up/down, 68/69 wheel left/right) |
| `0b` | double click: `button` |
| `0e` | mouse turbo: `button interval_ms(2)` |
| `02` | key: `modifiers usage` (modifier bits: 1 LCtrl, 2 LShift, 4 LAlt, 8 LGUI, 0x10–0x80 right) |
| `0d` | key turbo: `modifiers usage interval_ms(2)` |
| `03` | macro N times: `id(2) times` |
| `04` | macro while held: `id(2)` |
| `05` | macro toggle: `id(2)` |
| `0f` | macro sequence: `id(2)` |
| `06` | DPI: `01` up, `02` down, `06` cycle up, `07` cycle down, `03 stage`, `05 x(2) y(2)` clutch |
| `07` | profile: `01` next, `02` prev, `04` cycle up, `05` cycle down, `03 slot` |
| `09` | system: `01` power down, `02` sleep, `04` wake |
| `0a` | consumer: `usage(2)` |
| `0c` | Hypershift (hold): `01` |
| `12` | scroll mode toggle: `04` (factory value) |

## DPI

- `04:86` / `04:06`: `slot active count` followed by 5 × `idx x(2) y(2) 0 0`.
- `04:85` / `04:05`: `slot x(2) y(2) 0 0` is the current DPI.

## Macros (flash)

The macro flash is 124 KiB in 256-byte pages. Macro content, macro metadata
and profile metadata each take whole pages. Deleted pages become *recycled*
and can only be reused after a format.

| cmd | args → response |
|---|---|
| `06:8e` | → `? total(4) free(4) recycled(4)` |
| `06:80` | → count(2) |
| `06:8b` | `start(2)` → `start(2) count(2) ids(32×2)` |
| `06:08` | `id(2) size(4)` allocate (the id must not exist) |
| `06:88` | `id(2)` → `id size(4)` |
| `06:09` | `id(2) offset(4) len data(≤64)` write content |
| `06:89` | `id(2) offset(4) len` → `id offset len data` |
| `06:0c` / `06:8c` | macro metadata, same layout as `05:08` / `05:88` with a 2-byte id |
| `06:03` | `id(2)` delete |
| `06:0a` | `00 00 00 02 00 00` format; poll `06:8a` until it returns `00 00 02 02 00 00` |

After a format, profile metadata still points at its old pages, and rewriting it
recycles them. That's why compaction rewrites profile metadata before macros.

Macro content is a sequence of operations:

| op | meaning |
|---|---|
| `01 uu` | key down |
| `02 uu` | key up |
| `03 ss` | system control state (0 = released) |
| `05 hh ll` | consumer state (0 = released) |
| `08 mm` | mouse button state bitmask: 1 L, 2 R, 4 M, 8 back, 0x10 fwd |
| `0a dd` | wheel, signed ticks |
| `11 tt` | delay in ms (1 byte) |
| `12 hh ll` | delay in ms (2 bytes) |

## Lighting (via openrazer)

LED ids: `04` logo, `05` thumb grid. Effects use class `0f`; see openrazer's
`razermouse_driver.c` for the Naga V2 Pro quirks.

## Naga Pro (2020)

Checked on a Naga Pro (`1532:008f` wired, `1532:0090` receiver), firmware
1.0 (`00:81` → `01 00 00 00`, USB `bcdDevice` `0x0100`). Everything above
applies unless listed here; the transaction id is `0x1f` on both connections.

- **Buttons** (`02:84` lists 30): no scroll-mode (`6d`) or DPI (`60`) button.
  Instead `0b` is DPI up (front, factory `06 01 01`) and `0c` is DPI down
  (rear, factory `06 01 02`). Reading a button the mouse doesn't have fails, so
  read the list from `02:84` rather than assuming one.
- **Factory tilt** repeats wheel up/down (`0e 01 09 00 14`, `0e 01 0a 00 14`),
  not left/right.
- **DPI** goes up to 20000.
- **Side plate**: `00:b9` → `00` none, `01` 2-button, `03` 12-button,
  `04` 6-button. The mouse also sends input report `05 0e <value>` on
  interface 1 when the plate is swapped (`05 0e 00` while it's off). A plate
  that isn't seated firmly can drop some buttons while still reporting its value.
  (Not yet checked on the V2 Pro.)
- **Layer byte**: in `02:8c` / `02:0c` replies, the layer byte echoes the layer
  of the last *write*, not the one requested; match replies on slot and button
  only. The data itself is for the requested layer.
- **Lift-off distance**: `0b:8b` / `0b:0b` `slot 04 value(2)` (`0b:83` / `0b:03`
  `slot 04 state` is calibration on/off). Values: `0000` default, `0100` /
  `0101` / `0102` = 1 / 2 / 3 mm, `0200` / `0201` / `0202` = asymmetric
  1–2 / 1–3 / 2–3 mm (from razerqdhid). Writing `0000` answers *fail* but does
  reset it.
- **Polling**: `00:0e` on the active profile applies at once; on slot 0 it is
  accepted but ignored. The live rate is the global `00:05` / `00:85`.
  Lift-off written to the active profile also applies at once.
- **Flash**: about 372 KiB (`06:8e`), with the same commands.
- **Receiver**: some commands (`00:91`, `00:93`, `00:95`, `00:9f`, `00:b8`,
  `00:bc`) are answered only through the receiver, by the receiver itself.
- **Lighting** (openrazer): logo, scroll wheel, and a generic matrix zone.

## Firmware updates

Razer's Windows updater (`NagaV2Pro_00A800A7_FirmwareUpdater_v3.00.00_r1.exe`)
is a .NET program. Its embedded `DeviceUpdater.resources` holds the
configuration and the firmware images, stored as plain Intel HEX lines
(`Dev1FWLine*` for the receiver, `Dev2FWLine*` for the mouse).

- The mouse uses a Nordic chip. To flash, the updater reboots it into a
  bootloader that enumerates as `1532:110E` (bcdDevice `0x0200`), then returns
  to `1532:00a7` when done. The 3.00 update took about 95 s.
- Flashing uses the same 90-byte feature reports. The bootloader is polled
  with `00:86` before and after.
- The updater resets the mouse to factory settings (`BacktoDefault`).
- To run the updater in a VM, pass through the USB *port* (QEMU
  `usb-host,hostbus=…,hostport=…`) rather than the device ID, and give your user
  access to `1532:110E`:
  `SUBSYSTEM=="usb", ATTR{idVendor}=="1532", ATTR{idProduct}=="110e", TAG+="uaccess"`.
  QEMU's `pcap=` option on `usb-host` records the traffic without root.
