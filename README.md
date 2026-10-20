# Naga Synapse

A Razer Synapse replacement for Linux, for the **Razer Naga V2 Pro**
(`1532:00a7` wired, `1532:00a8` HyperSpeed receiver) and the original
**Razer Naga Pro** (`1532:008f` wired, `1532:0090` receiver).

Everything is written to the mouse's **onboard memory**, so your settings keep
working with no software running, on any computer.

- **Onboard profiles**: all 5 slots (white/red/green/blue/cyan). Create, delete,
  rename, duplicate, activate, restore defaults, import/export to JSON, back up
  everything.
- **Rebind every button**: all 30 inputs, on both the standard and the
  **Hypershift** layer. That covers the left/right/wheel buttons, wheel tilt, the
  scroll-mode (V2 Pro), DPI and bottom buttons, and every key on the 2-, 6- and
  12-button side plates. You can assign:
  - keyboard keys and combos (with turbo)
  - mouse buttons (normal, double click, turbo)
  - macros (play N times, repeat while held, toggle, sequence)
  - DPI functions (cycle, step, set stage, sensitivity clutch)
  - profile switching
  - multimedia keys, system sleep/power/wake
  - Hypershift, scroll-mode toggle, or disabled
- **Macros**: record from the keyboard and mouse (with real, fixed or no delays),
  or build them step by step: key press/down/up, typed text, mouse clicks,
  scrolling, delays and media keys. Macros are stored on the mouse and can be
  imported and exported.
- **Performance**: DPI stages (1–5, optional separate X/Y), polling rate,
  lift-off distance (where the mouse supports it), sleep timer and low-battery
  threshold.
- **Lighting**: logo, scroll wheel and thumb grid (whichever zones the mouse
  has), through the openrazer kernel driver.
- A full **command-line interface** for scripting.

## Running

Requirements: Python ≥ 3.10 and PySide6 (`pacman -S pyside6`). The CLI has no
dependencies.

```sh
python3 -m nagasynapse            # GUI, straight from this checkout
python3 -m nagasynapse.cli info   # CLI
```

To install for your user (an app menu entry plus the `nagasynapse` and
`nagasynapse-cli` commands):

```sh
scripts/install.sh            # add --udev to also install the udev rule (sudo)
```

### Device permissions

The app talks to the mouse through `/dev/hidraw*`. If you get "Permission
denied", install the udev rule and replug the mouse:

```sh
sudo install -m644 packaging/70-nagasynapse.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

The Lighting tab writes to openrazer's sysfs files, so you need
`openrazer-driver-dkms` and membership of the `openrazer` group. The rest of
the app does not need openrazer, and runs fine alongside it.

## Using the GUI

- **Customize**: pick a profile at the top, then click any button on the
  drawing. Choose what it should do in the panel on the right and press
  **Save**; the change is written to the mouse right away. Use
  **STANDARD / HYPERSHIFT** to switch layers. To use the Hypershift layer, first
  assign *Hypershift* to some button on the standard layer, then hold that button.
  When the mouse reports its side plate (the Naga Pro does), the attached plate
  is shown and marked with ●, and nothing is shown while no plate is attached.
  Clicking another plate shows its stored bindings; bindings for all three
  plates are stored.
- **Macros**: press **New**, then **Record**. Type or click inside the box and
  press **Stop**. Edit the steps if needed, then **Save to mouse**. Assign the
  macro to a button on the Customize tab (category *Macro*).
- **Profiles**: manage the 5 onboard slots. The mouse's bottom button cycles
  profiles by default, and the LED colour shows the active one.

Editing a profile does not switch the mouse to it. Use **Make active**, or the
profile button on the mouse. Changes to the active profile take effect
immediately.

**Checking a binding:** click the **TEST** strip under the drawing, then press
buttons on the mouse. It shows what each one sends, for example `Ctrl + C`,
`Mouse 4 (Back)`, or each keystroke of a macro.

## CLI examples

```sh
nagasynapse-cli info                                # device, profiles, memory
nagasynapse-cli show -a                             # bindings of the active profile
nagasynapse-cli bind 12:1 key:ctrl+c -p 1           # side button 1 -> Ctrl+C
nagasynapse-cli bind 12:2 key:f --hypershift        # Hypershift layer
nagasynapse-cli bind dpi hypershift                 # hold DPI button = Hypershift
nagasynapse-cli bind tiltleft media:voldown
nagasynapse-cli macro create "Greeting" "text:Hello there!, enter"
nagasynapse-cli bind 12:3 macro:1:times=2
nagasynapse-cli bind 12:4 macro:1:hold
nagasynapse-cli unbind 12:3                         # back to factory default
nagasynapse-cli profile create 2 --name "MMO" --copy-from 1
nagasynapse-cli profile activate 2
nagasynapse-cli dpi -p 2 --stages 400,800,1600,3200 --active 2
nagasynapse-cli export mmo.json -p 2  /  import mmo.json -p 3
nagasynapse-cli backup all.json  /  restore all.json
nagasynapse-cli memory --compact
```

Run `nagasynapse-cli --help` for the full button/action/step syntax.

## Notes and limits

- Deleting or editing a macro leaves "reclaimable" memory behind; this is how the
  firmware works. When space runs low the app compacts the memory
  automatically: it backs everything up to `~/.local/state/nagasynapse/backups/`,
  formats the macro memory and writes everything back. You can also run it from
  the Macros tab. Don't unplug the mouse while that runs.
- Profile and macro names are stored on the mouse in this app's own format.
  If you go back to Razer Synapse on Windows it will not know these names, and
  it may overwrite the onboard data when it syncs.
- If the openrazer daemon is running, it may re-apply its own DPI or lighting
  when it starts.
- The Naga V2 Pro was only tested with the wired connection; its HyperSpeed
  receiver uses the same protocol and should work. The Naga Pro was tested both
  wired and through its receiver.
- The openrazer daemon writes its saved DPI and polling rate to the mouse every
  time it starts (falling back to 1800 DPI / 500 Hz), overriding the active
  profile. Stop or mask it if you rely on onboard profiles.

## Development

```sh
python3 -m unittest discover -s tests                          # offline tests
NAGA_DEVICE_TESTS=1 python3 -m unittest tests.test_device -v   # needs the mouse
```

The hardware test uses profile slot 5 as scratch space (it must be empty), and
afterwards checks that the active profile is unchanged.

See [PROTOCOL.md](PROTOCOL.md) for the USB protocol details.

The Naga Pro support was worked out and tested on a Naga Pro (firmware 1.0).
Protocol knowledge builds on the reverse-engineering work of
[razerqdhid](https://github.com/geezmolycos/razerqdhid) (Basilisk V3),
[RazerNagaProV2Control](https://github.com/rom4ster/RazerNagaProV2Control) and
[openrazer](https://github.com/openrazer/openrazer). All of it was verified
against a Naga V2 Pro on firmware 1.03 and 3.00.

## License

Naga Synapse is licensed under the GNU General Public License, version 2 only
(`GPL-2.0-only`). See [LICENSE](LICENSE).
