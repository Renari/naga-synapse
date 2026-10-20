"""High level API for the onboard memory of the Razer Naga V2 Pro and Naga Pro."""

from __future__ import annotations

import json
import math
import os
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import layout
from .actions import Action
from .layout import LIFT_OFF, PLATE_BY_VALUE, PROFILE_SLOTS, POLLING_RATES, default_action
from .macros import Macro
from .transport import (HidrawInfo, HidrawTransport, RazerError, STATUS_FAIL,
                        open_device)

PAGE_SIZE = 256
DEFAULT_DPI_STAGES = (400, 800, 1600, 3200, 6400)
META_MAGIC = b"NSYN\x01"
MAX_NAME_BYTES = 60
LAYERS = (0, 1)  # 0 = standard, 1 = Hypershift

Progress = Callable[[str, float], None]


class FlashFull(RazerError):
    pass


@dataclass
class FlashUsage:
    total: int
    free: int
    recycled: int

    @property
    def used(self) -> int:
        return self.total - self.free - self.recycled


@dataclass
class DeviceInfo:
    name: str
    path: str
    firmware: str
    serial: str
    battery: int | None = None      # percent
    charging: bool | None = None


@dataclass
class ProfileData:
    """Everything stored for one onboard profile."""

    slot: int
    name: str = ""
    bindings: dict[tuple[int, int], Action] = field(default_factory=dict)
    dpi_stages: list[tuple[int, int]] = field(default_factory=list)
    dpi_active: int = 1
    polling_interval: int = 1
    lift_off: int | None = None     # None when the mouse doesn't support it

    def binding(self, button_id: int, layer: int = 0) -> Action:
        return self.bindings.get((button_id, layer), default_action(button_id))

    def to_json(self) -> dict:
        return {
            "format": "nagasynapse-profile",
            "version": 1,
            "name": self.name,
            "bindings": [
                {"button": b, "layer": l, **a.to_json()}
                for (b, l), a in sorted(self.bindings.items())
            ],
            "dpi_stages": [list(s) for s in self.dpi_stages],
            "dpi_active": self.dpi_active,
            "polling_rate": POLLING_RATES.get(self.polling_interval, 1000),
            **({"lift_off": self.lift_off} if self.lift_off is not None else {}),
        }

    @classmethod
    def from_json(cls, obj: dict, slot: int = 0) -> "ProfileData":
        if obj.get("format") != "nagasynapse-profile":
            raise ValueError("not a Naga Synapse profile file")
        rate_to_interval = {v: k for k, v in POLLING_RATES.items()}
        return cls(
            slot=slot,
            name=obj.get("name", ""),
            bindings={(int(b["button"]), int(b["layer"])): Action.from_json(b)
                      for b in obj.get("bindings", [])},
            dpi_stages=[(int(x), int(y)) for x, y in obj.get("dpi_stages", [])],
            dpi_active=int(obj.get("dpi_active", 1)),
            polling_interval=rate_to_interval.get(int(obj.get("polling_rate", 1000)), 1),
            lift_off=int(obj["lift_off"]) if "lift_off" in obj else None,
        )


def encode_meta(name: str) -> bytes:
    raw = name.encode("utf-8")[:MAX_NAME_BYTES]
    return META_MAGIC + raw.decode("utf-8", "ignore").encode("utf-8")


def decode_meta(data: bytes | None) -> str | None:
    if data and data.startswith(META_MAGIC):
        return data[len(META_MAGIC):].decode("utf-8", "replace")
    return None


def _pages(nbytes: int) -> int:
    return max(1, math.ceil(nbytes / PAGE_SIZE))


def backup_dir() -> Path:
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    path = base / "nagasynapse" / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


class NagaDevice:
    def __init__(self, transport: HidrawTransport, info: HidrawInfo):
        self.t = transport
        self.hid = info
        # The model's tables; layout's module-level ones are switched by the
        # caller (GUI thread / CLI), since other threads read them.
        self.model = layout.model_for_pid(info.pid)
        self._button_ids: list[int] | None = None

    @classmethod
    def open(cls, path: str | None = None) -> "NagaDevice":
        transport, info = open_device(path)
        return cls(transport, info)

    def close(self) -> None:
        self.t.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def _cmd(self, cls_: int, cid: int, args: bytes = b"", size: int | None = None,
             **kw):
        return self.t.command(cls_, cid, args, size, **kw)

    # ------------------------------------------------------------ general
    def firmware(self) -> str:
        a = self._cmd(0x00, 0x81, size=4).args
        return f"{a[0]}.{a[1]}.{a[2]}"

    def serial(self) -> str:
        return self._cmd(0x00, 0x82, size=16).args[:16].rstrip(b"\0").decode("ascii", "replace")

    def battery(self) -> tuple[int | None, bool | None]:
        try:
            level = self._cmd(0x07, 0x80, size=2).args[1]
            charging = self._cmd(0x07, 0x84, size=2).args[1]
            return round(level * 100 / 255), bool(charging)
        except RazerError:
            return None, None

    def device_info(self) -> DeviceInfo:
        battery, charging = self.battery()
        return DeviceInfo(self.hid.name, self.hid.path, self.firmware(),
                          self.serial(), battery, charging)

    def idle_time(self) -> int:
        """Seconds without movement before the mouse goes to sleep."""
        a = self._cmd(0x07, 0x83, size=2).args
        return (a[0] << 8) | a[1]

    def set_idle_time(self, seconds: int) -> None:
        seconds = max(60, min(900, seconds))
        self._cmd(0x07, 0x03, bytes([seconds >> 8, seconds & 0xFF]))

    def low_battery_threshold(self) -> int:
        """Battery percentage at which the mouse enters low power mode."""
        return round(self._cmd(0x07, 0x81, size=1).args[0] * 100 / 255)

    def set_low_battery_threshold(self, percent: int) -> None:
        value = round(max(5, min(100, percent)) * 255 / 100)
        self._cmd(0x07, 0x01, bytes([value]))

    def button_ids(self) -> list[int]:
        a = self._cmd(0x02, 0x84, size=0x50).args
        return list(a[1:1 + a[0]])

    def buttons(self) -> list[int]:
        """The buttons this mouse has, as it reports them (cached).

        Reading a button the mouse doesn't have fails, so whole-profile reads
        and resets use this list instead of a fixed one."""
        if self._button_ids is None:
            known = [b.id for b in self.model.buttons]
            try:
                self._button_ids = self.button_ids() or known
            except RazerError:
                self._button_ids = known
        return self._button_ids

    def side_plate(self) -> str | None:
        """The attached side plate ("side2", "side6", "side12"), or None if
        no plate is attached or the mouse can't tell (00:b9)."""
        return PLATE_BY_VALUE.get(self._cmd(0x00, 0xB9, size=1).args[0])

    # ----------------------------------------------------------- sensor
    def lift_off(self, slot: int) -> int:
        """Lift-off distance setting (see layout.LIFT_OFF)."""
        a = self._cmd(0x0B, 0x8B, bytes([slot, 0x04]), 4).args
        return (a[2] << 8) | a[3]

    def set_lift_off(self, slot: int, value: int) -> None:
        resp = self._cmd(0x0B, 0x0B, bytes([slot, 0x04, value >> 8, value & 0xFF]),
                         check=False)
        # Resetting to 0 (default) answers "fail" on the Naga Pro but does
        # reset, so trust the read-back.
        if resp.status != 2 and self.lift_off(slot) != value:
            raise RazerError("lift-off write failed", resp.status)

    # ----------------------------------------------------------- profiles
    def profile_slot_count(self) -> int:
        return self._cmd(0x05, 0x8A, size=1).args[0]

    def profiles(self) -> list[int]:
        count = self._cmd(0x05, 0x80, size=1).args[0]
        a = self._cmd(0x05, 0x81, size=1 + count).args
        return sorted(a[1:1 + count])

    def active_profile(self) -> int:
        return self._cmd(0x05, 0x84, size=1).args[0]

    def set_active_profile(self, slot: int) -> None:
        self._cmd(0x05, 0x04, bytes([slot]))

    def create_profile(self, slot: int) -> None:
        if slot not in PROFILE_SLOTS:
            raise ValueError("profile slot must be 1-5")
        self._cmd(0x05, 0x02, bytes([slot]))

    def delete_profile(self, slot: int) -> None:
        self._cmd(0x05, 0x03, bytes([slot]))

    def _read_chunked(self, cls_: int, cid: int, head: bytes, head_fmt: str) -> bytes | None:
        """Read profile/macro metadata (0x0588 / 0x068c style)."""
        data = b""
        total = None
        head_len = struct.calcsize(head_fmt)
        while total is None or len(data) < total:
            args = head + struct.pack(">H", len(data))
            resp = self._cmd(cls_, cid, args,
                             head_len + 4 + 64, check=False)
            if resp.status == STATUS_FAIL:
                return None
            if resp.status != 2:
                raise RazerError(f"metadata read failed ({resp.status})", resp.status)
            off = head_len + 2
            total = struct.unpack(">H", resp.args[off:off + 2])[0]
            chunk = resp.args[off + 2:off + 2 + 64]
            data += chunk[:total - len(data)]
            if total == 0:
                break
        return data

    def _write_chunked(self, cls_: int, cid: int, head: bytes, data: bytes) -> None:
        total = len(data)
        pos = 0
        while pos < total or (total == 0 and pos == 0):
            chunk = data[pos:pos + 64]
            self._cmd(cls_, cid, head + struct.pack(">HH", pos, total) + chunk)
            pos += len(chunk)
            if total == 0:
                break

    def profile_meta(self, slot: int) -> bytes | None:
        return self._read_chunked(0x05, 0x88, bytes([slot]), ">B")

    def profile_name(self, slot: int) -> str | None:
        return decode_meta(self.profile_meta(slot))

    def set_profile_name(self, slot: int, name: str) -> None:
        data = encode_meta(name)
        self.ensure_flash(PAGE_SIZE)
        self._write_chunked(0x05, 0x08, bytes([slot]), data)

    # ----------------------------------------------------------- bindings
    def get_binding(self, slot: int, button: int, layer: int = 0) -> Action:
        resp = self._cmd(0x02, 0x8C, bytes([slot, button, layer]), 10)
        return Action.decode(resp.args[3:10])

    def set_binding(self, slot: int, button: int, layer: int, action: Action) -> None:
        self._cmd(0x02, 0x0C, bytes([slot, button, layer]) + action.encode())

    # -------------------------------------------------------- performance
    def get_dpi_stages(self, slot: int) -> tuple[list[tuple[int, int]], int]:
        a = self._cmd(0x04, 0x86, bytes([slot]), 38).args
        active, count = a[1], a[2]
        stages = []
        for i in range(min(count, 5)):
            _idx, x, y = struct.unpack(">BHH", a[3 + i * 7:3 + i * 7 + 5])
            stages.append((x, y))
        return stages, active

    def set_dpi_stages(self, slot: int, stages: list[tuple[int, int]], active: int) -> None:
        if not 1 <= len(stages) <= 5:
            raise ValueError("between 1 and 5 DPI stages are required")
        active = max(1, min(active, len(stages)))
        body = b"".join(struct.pack(">BHHxx", i + 1, x, y) for i, (x, y) in enumerate(stages))
        body = body.ljust(35, b"\0")
        self._cmd(0x04, 0x06, bytes([slot, active, len(stages)]) + body)
        # Make the active stage's DPI the current one as well.
        x, y = stages[active - 1]
        self._cmd(0x04, 0x05, struct.pack(">BHHxx", slot, x, y))

    def get_dpi(self, slot: int) -> tuple[int, int]:
        a = self._cmd(0x04, 0x85, bytes([slot]), 7).args
        return struct.unpack(">HH", a[1:5])

    def get_polling_interval(self, slot: int) -> int:
        return self._cmd(0x00, 0x8E, bytes([slot]), 2).args[1]

    def set_polling_interval(self, slot: int, interval: int) -> None:
        self._cmd(0x00, 0x0E, bytes([slot, interval]))

    # -------------------------------------------------------------- flash
    def flash_usage(self) -> FlashUsage:
        _unknown, total, free, recycled = struct.unpack(
            ">HIII", self._cmd(0x06, 0x8E, size=14).args[:14])
        return FlashUsage(total, free, recycled)

    def reset_flash(self) -> None:
        magic = bytes.fromhex("000000020000")
        self._cmd(0x06, 0x0A, magic)
        for _ in range(100):
            if self._cmd(0x06, 0x8A, magic, 6).args[:6] == bytes.fromhex("000002020000"):
                return
            time.sleep(0.1)
        raise RazerError("flash reset did not complete")

    # ------------------------------------------------------------- macros
    def macro_count(self) -> int:
        return struct.unpack(">H", self._cmd(0x06, 0x80, size=2).args[:2])[0]

    def macro_ids(self) -> list[int]:
        ids: list[int] = []
        total = None
        while total is None or len(ids) < total:
            # response: start index (echo), total count, up to 32 ids
            a = self._cmd(0x06, 0x8B, struct.pack(">H", len(ids)), 68).args
            total = struct.unpack(">H", a[2:4])[0]
            batch = struct.unpack(">32H", a[4:68])
            ids += list(batch[:min(32, total - len(ids))])
            if total == 0:
                break
        return ids

    def macro_meta(self, macro_id: int) -> bytes | None:
        return self._read_chunked(0x06, 0x8C, struct.pack(">H", macro_id), ">H")

    def macro_size(self, macro_id: int) -> int:
        return struct.unpack(">I", self._cmd(0x06, 0x88, struct.pack(">H", macro_id), 6).args[2:6])[0]

    def macro_content(self, macro_id: int) -> bytes:
        size = self.macro_size(macro_id)
        data = b""
        while len(data) < size:
            n = min(64, size - len(data))
            a = self._cmd(0x06, 0x89, struct.pack(">HIB", macro_id, len(data), n), 7 + 64).args
            data += a[7:7 + n]
        return data

    def read_macro(self, macro_id: int) -> Macro:
        name = decode_meta(self.macro_meta(macro_id)) or f"Macro {macro_id}"
        return Macro.decode(self.macro_content(macro_id), name, macro_id)

    def read_macros(self) -> list[Macro]:
        return [self.read_macro(mid) for mid in self.macro_ids()]

    def delete_macro(self, macro_id: int) -> None:
        self._cmd(0x06, 0x03, struct.pack(">H", macro_id))

    def _store_macro(self, macro_id: int, content: bytes, meta: bytes | None) -> None:
        if not content:
            raise ValueError("macro is empty")
        self._cmd(0x06, 0x08, struct.pack(">HI", macro_id, len(content)))
        pos = 0
        while pos < len(content):
            chunk = content[pos:pos + 64]
            self._cmd(0x06, 0x09, struct.pack(">HIB", macro_id, pos, len(chunk)) + chunk)
            pos += len(chunk)
        if meta:
            self._write_chunked(0x06, 0x0C, struct.pack(">H", macro_id), meta)

    def next_macro_id(self, taken: list[int] | None = None) -> int:
        used = set(self.macro_ids() if taken is None else taken)
        mid = 1
        while mid in used:
            mid += 1
        return mid

    def write_macro(self, macro: Macro, progress: Progress | None = None) -> int:
        """Store a macro on the mouse (replacing any macro with the same id)."""
        content = macro.encode()
        if not content:
            raise ValueError("macro has no events")
        meta = encode_meta(macro.name)
        ids = self.macro_ids()
        if macro.id is None:
            macro.id = self.next_macro_id(ids)
        needed = (_pages(len(content)) + _pages(len(meta))) * PAGE_SIZE
        replacing = macro.id in ids
        if self.flash_usage().free < needed + PAGE_SIZE:
            self.compact_flash(exclude={macro.id}, progress=progress)
            replacing = False
            if self.flash_usage().free < needed + PAGE_SIZE:
                raise FlashFull("not enough onboard memory for this macro")
        if replacing:
            self.delete_macro(macro.id)
        self._store_macro(macro.id, content, meta)
        if self.macro_content(macro.id) != content:
            raise RazerError("macro verification failed")
        return macro.id

    def ensure_flash(self, needed: int) -> None:
        if self.flash_usage().free < needed + PAGE_SIZE:
            self.compact_flash()
            if self.flash_usage().free < needed + PAGE_SIZE:
                raise FlashFull("onboard memory is full")

    def compact_flash(self, exclude: set[int] | None = None,
                      progress: Progress | None = None) -> Path:
        """Garbage-collect the macro flash.

        Deleted macros leave "recycled" pages that can only be reused after a
        full flash format, so: back everything up, format, write it all back.
        """
        exclude = exclude or set()
        report = progress or (lambda msg, frac: None)
        report("Backing up onboard memory…", 0.0)
        ids = self.macro_ids()
        if len(ids) != self.macro_count():
            raise RazerError("macro list is inconsistent; refusing to format memory")
        macros = []
        for mid in ids:
            content = self.macro_content(mid)
            if len(content) != self.macro_size(mid):
                raise RazerError(f"could not back up macro {mid}; refusing to format memory")
            macros.append({"id": mid, "meta": (self.macro_meta(mid) or b"").hex(),
                           "content": content.hex(), "dropped": mid in exclude})
        metas = {}
        for slot in self.profiles():
            meta = self.profile_meta(slot)
            if meta:
                metas[slot] = meta.hex()
        backup = backup_dir() / f"flash-{time.strftime('%Y%m%d-%H%M%S')}.json"
        backup.write_text(json.dumps({"macros": macros, "profile_meta": metas}, indent=1))
        for old in sorted(backup_dir().glob("flash-*.json"))[:-20]:
            old.unlink(missing_ok=True)
        report("Formatting onboard memory…", 0.2)
        self.reset_flash()
        total = max(1, len(macros) + len(metas))
        done = 0
        # Profile names first: the firmware still points at their old pages
        # after a format and recycles those pages on rewrite, so this must
        # happen before any macro could be allocated there.
        for slot, meta in metas.items():
            self._write_chunked(0x05, 0x08, bytes([int(slot)]), bytes.fromhex(meta))
            done += 1
            report("Restoring profile names…", 0.2 + 0.8 * done / total)
        for m in macros:
            if m["dropped"]:
                continue
            self._store_macro(m["id"], bytes.fromhex(m["content"]),
                              bytes.fromhex(m["meta"]) or None)
            done += 1
            report("Restoring macros…", 0.2 + 0.8 * done / total)
        report("Done", 1.0)
        return backup

    # ----------------------------------------------------- whole profiles
    def read_profile(self, slot: int, progress: Progress | None = None,
                     button_ids: list[int] | None = None) -> ProfileData:
        report = progress or (lambda msg, frac: None)
        ids = button_ids or self.buttons()
        data = ProfileData(slot=slot)
        data.name = (self.profile_name(slot) or "") if slot else "Direct"
        total = len(ids) * len(LAYERS)
        for n, (layer, button) in enumerate((l, b) for l in LAYERS for b in ids):
            data.bindings[(button, layer)] = self.get_binding(slot, button, layer)
            if n % 6 == 0:
                report(f"Reading profile {slot}…", n / total)
        data.dpi_stages, data.dpi_active = self.get_dpi_stages(slot)
        data.polling_interval = self.get_polling_interval(slot)
        try:
            data.lift_off = self.lift_off(slot)
        except RazerError:
            data.lift_off = None
        report("Done", 1.0)
        return data

    def write_profile(self, slot: int, data: ProfileData,
                      progress: Progress | None = None,
                      previous: ProfileData | None = None,
                      macro_map: dict[int, int] | None = None) -> None:
        """Write a whole profile. Only changed bindings are sent when
        `previous` is given. `macro_map` remaps macro ids (for imports)."""
        report = progress or (lambda msg, frac: None)
        if slot not in self.profiles():
            self.create_profile(slot)
        items = sorted(data.bindings.items())
        for n, ((button, layer), action) in enumerate(items):
            if macro_map and action.macro_id in macro_map:
                times = action.macro_times
                action = Action.macro(macro_map[action.macro_id], action.kind, times)
            if previous and previous.bindings.get((button, layer), None) is not None \
                    and previous.bindings[(button, layer)].same_as(action):
                continue
            self.set_binding(slot, button, layer, action)
            report(f"Writing profile {slot}…", n / max(1, len(items)))
        if data.dpi_stages:
            self.set_dpi_stages(slot, data.dpi_stages, data.dpi_active)
        if data.polling_interval:
            self.set_polling_interval(slot, data.polling_interval)
        if data.lift_off is not None and data.lift_off in LIFT_OFF and \
                (previous is None or previous.lift_off != data.lift_off):
            try:
                self.set_lift_off(slot, data.lift_off)
            except RazerError:
                pass  # older profile files or mice without lift-off settings
        if data.name and data.name != (previous.name if previous else self.profile_name(slot)):
            self.set_profile_name(slot, data.name)
        report("Done", 1.0)

    def init_profile(self, slot: int, progress: Progress | None = None) -> None:
        """Factory defaults for a new profile: buttons, DPI stages, polling."""
        self.reset_profile_bindings(slot, progress)
        self.set_dpi_stages(slot, [(d, d) for d in DEFAULT_DPI_STAGES], 3)
        self.set_polling_interval(slot, 1)

    def reset_profile_bindings(self, slot: int, progress: Progress | None = None) -> None:
        report = progress or (lambda msg, frac: None)
        # Only buttons with a known factory binding; anything else is left alone.
        known = self.model.by_id
        ids = [b for b in self.buttons() if b in known]
        total = len(ids) * len(LAYERS)
        n = 0
        for layer in LAYERS:
            for button in ids:
                self.set_binding(slot, button, layer, default_action(button, self.model))
                n += 1
                report(f"Resetting profile {slot}…", n / total)
