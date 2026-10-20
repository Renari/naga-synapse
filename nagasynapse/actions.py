"""Button actions ("button functions") as stored in the mouse.

Each binding is 7 bytes: function class, data length, up to 5 data bytes.
The factory defaults leave the length byte at 1 regardless of the payload,
so decoding derives the payload size from the class instead of trusting it.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

from .hid_usage import combo_text, consumer_name, parse_combo, CONSUMER_TOKENS


class Kind(IntEnum):
    DISABLED = 0x00
    MOUSE = 0x01
    KEYBOARD = 0x02
    MACRO_TIMES = 0x03
    MACRO_HOLD = 0x04
    MACRO_TOGGLE = 0x05
    DPI = 0x06
    PROFILE = 0x07
    SYSTEM = 0x09
    CONSUMER = 0x0A
    DOUBLE_CLICK = 0x0B
    HYPERSHIFT = 0x0C
    KEYBOARD_TURBO = 0x0D
    MOUSE_TURBO = 0x0E
    MACRO_SEQUENCE = 0x0F
    SCROLL_MODE = 0x12


MACRO_KINDS = (Kind.MACRO_TIMES, Kind.MACRO_HOLD, Kind.MACRO_TOGGLE, Kind.MACRO_SEQUENCE)


class MouseFn(IntEnum):
    LEFT = 0x01
    RIGHT = 0x02
    MIDDLE = 0x03
    BACK = 0x04
    FORWARD = 0x05
    WHEEL_UP = 0x09
    WHEEL_DOWN = 0x0A
    WHEEL_LEFT = 0x68
    WHEEL_RIGHT = 0x69


MOUSE_FN_NAMES = {
    MouseFn.LEFT: "Left Click",
    MouseFn.RIGHT: "Right Click",
    MouseFn.MIDDLE: "Middle Click",
    MouseFn.BACK: "Mouse Button 4 (Back)",
    MouseFn.FORWARD: "Mouse Button 5 (Forward)",
    MouseFn.WHEEL_UP: "Scroll Up",
    MouseFn.WHEEL_DOWN: "Scroll Down",
    MouseFn.WHEEL_LEFT: "Scroll Left",
    MouseFn.WHEEL_RIGHT: "Scroll Right",
}
MOUSE_FN_TOKENS = {
    "left": MouseFn.LEFT, "right": MouseFn.RIGHT, "middle": MouseFn.MIDDLE,
    "back": MouseFn.BACK, "forward": MouseFn.FORWARD, "button4": MouseFn.BACK,
    "button5": MouseFn.FORWARD, "wheelup": MouseFn.WHEEL_UP,
    "wheeldown": MouseFn.WHEEL_DOWN, "wheelleft": MouseFn.WHEEL_LEFT,
    "wheelright": MouseFn.WHEEL_RIGHT, "scrollup": MouseFn.WHEEL_UP,
    "scrolldown": MouseFn.WHEEL_DOWN, "scrollleft": MouseFn.WHEEL_LEFT,
    "scrollright": MouseFn.WHEEL_RIGHT,
}


class DpiOp(IntEnum):
    NEXT = 0x01
    PREV = 0x02
    STAGE = 0x03
    CLUTCH = 0x05
    CYCLE_UP = 0x06
    CYCLE_DOWN = 0x07


DPI_OP_NAMES = {
    DpiOp.CYCLE_UP: "Cycle Sensitivity Stages Up",
    DpiOp.CYCLE_DOWN: "Cycle Sensitivity Stages Down",
    DpiOp.NEXT: "Sensitivity Stage Up",
    DpiOp.PREV: "Sensitivity Stage Down",
    DpiOp.STAGE: "Set Sensitivity Stage",
    DpiOp.CLUTCH: "Sensitivity Clutch",
}


class ProfileOp(IntEnum):
    NEXT = 0x01
    PREV = 0x02
    SET = 0x03
    CYCLE_UP = 0x04
    CYCLE_DOWN = 0x05


PROFILE_OP_NAMES = {
    ProfileOp.CYCLE_UP: "Cycle Profiles Up",
    ProfileOp.CYCLE_DOWN: "Cycle Profiles Down",
    ProfileOp.NEXT: "Next Profile",
    ProfileOp.PREV: "Previous Profile",
    ProfileOp.SET: "Switch to Profile",
}


class SystemFn(IntEnum):
    POWER_DOWN = 0x01
    SLEEP = 0x02
    WAKE = 0x04


SYSTEM_FN_NAMES = {SystemFn.POWER_DOWN: "System Power Down",
                   SystemFn.SLEEP: "System Sleep",
                   SystemFn.WAKE: "System Wake"}

MACRO_MODE_NAMES = {
    Kind.MACRO_TIMES: "Play {times}x",
    Kind.MACRO_HOLD: "Repeat while held",
    Kind.MACRO_TOGGLE: "Toggle repeat",
    Kind.MACRO_SEQUENCE: "Sequence",
}

PROFILE_COLORS = {1: "White", 2: "Red", 3: "Green", 4: "Blue", 5: "Cyan"}


def _payload_size(kind: int, data: bytes, length_byte: int) -> int:
    fixed = {
        Kind.DISABLED: 0, Kind.MOUSE: 1, Kind.DOUBLE_CLICK: 1, Kind.MOUSE_TURBO: 3,
        Kind.KEYBOARD: 2, Kind.KEYBOARD_TURBO: 4, Kind.MACRO_TIMES: 3,
        Kind.MACRO_HOLD: 2, Kind.MACRO_TOGGLE: 2, Kind.MACRO_SEQUENCE: 2,
        Kind.SYSTEM: 1, Kind.CONSUMER: 2, Kind.HYPERSHIFT: 1, Kind.SCROLL_MODE: 1,
    }
    if kind in fixed:
        return fixed[kind]
    if kind == Kind.DPI:
        return {DpiOp.STAGE: 2, DpiOp.CLUTCH: 5}.get(data[0] if data else 0, 1)
    if kind == Kind.PROFILE:
        return 2 if data and data[0] == ProfileOp.SET else 1
    return min(max(length_byte, 0), 5)


@dataclass(frozen=True)
class Action:
    kind: int
    data: bytes = b""

    # ---------------------------------------------------------------- codec
    def encode(self) -> bytes:
        return bytes([self.kind, len(self.data)]) + self.data.ljust(5, b"\0")

    @classmethod
    def decode(cls, raw: bytes) -> "Action":
        raw = bytes(raw).ljust(7, b"\0")
        kind = raw[0]
        payload = raw[2:7]
        return cls(kind, payload[:_payload_size(kind, payload, raw[1])])

    def to_json(self) -> dict:
        return {"kind": self.kind, "data": self.data.hex()}

    @classmethod
    def from_json(cls, obj: dict) -> "Action":
        return cls(int(obj["kind"]), bytes.fromhex(obj.get("data", "")))

    # --------------------------------------------------------- constructors
    @classmethod
    def disabled(cls) -> "Action":
        return cls(Kind.DISABLED)

    @classmethod
    def mouse(cls, fn: int, *, double_click: bool = False,
              turbo_ms: int | None = None) -> "Action":
        if turbo_ms:
            return cls(Kind.MOUSE_TURBO, struct.pack(">BH", fn, turbo_ms))
        return cls(Kind.DOUBLE_CLICK if double_click else Kind.MOUSE, bytes([fn]))

    @classmethod
    def keyboard(cls, usage: int, modifiers: int = 0, *,
                 turbo_ms: int | None = None) -> "Action":
        if turbo_ms:
            return cls(Kind.KEYBOARD_TURBO, struct.pack(">BBH", modifiers, usage, turbo_ms))
        return cls(Kind.KEYBOARD, bytes([modifiers, usage]))

    @classmethod
    def macro(cls, macro_id: int, mode: int = Kind.MACRO_TIMES, times: int = 1) -> "Action":
        if mode == Kind.MACRO_TIMES:
            return cls(Kind.MACRO_TIMES, struct.pack(">HB", macro_id, max(1, min(times, 255))))
        if mode not in MACRO_KINDS:
            raise ValueError("not a macro mode")
        return cls(mode, struct.pack(">H", macro_id))

    @classmethod
    def dpi(cls, op: int, *, stage: int = 1, dpi_x: int = 800,
            dpi_y: int | None = None) -> "Action":
        if op == DpiOp.STAGE:
            return cls(Kind.DPI, bytes([op, stage]))
        if op == DpiOp.CLUTCH:
            return cls(Kind.DPI, struct.pack(">BHH", op, dpi_x, dpi_y or dpi_x))
        return cls(Kind.DPI, bytes([op]))

    @classmethod
    def profile(cls, op: int, profile: int = 1) -> "Action":
        if op == ProfileOp.SET:
            return cls(Kind.PROFILE, bytes([op, profile]))
        return cls(Kind.PROFILE, bytes([op]))

    @classmethod
    def consumer(cls, usage: int) -> "Action":
        return cls(Kind.CONSUMER, struct.pack(">H", usage))

    @classmethod
    def system(cls, fn: int) -> "Action":
        return cls(Kind.SYSTEM, bytes([fn]))

    @classmethod
    def hypershift(cls) -> "Action":
        return cls(Kind.HYPERSHIFT, b"\x01")

    @classmethod
    def scroll_mode(cls) -> "Action":
        # The Naga V2 Pro factory binding uses 0x04 as the argument.
        return cls(Kind.SCROLL_MODE, b"\x04")

    # ---------------------------------------------------------- accessors
    @property
    def macro_id(self) -> int | None:
        if self.kind in MACRO_KINDS and len(self.data) >= 2:
            return struct.unpack(">H", self.data[:2])[0]
        return None

    @property
    def macro_times(self) -> int:
        return self.data[2] if self.kind == Kind.MACRO_TIMES and len(self.data) >= 3 else 1

    @property
    def turbo_ms(self) -> int | None:
        if self.kind == Kind.MOUSE_TURBO and len(self.data) >= 3:
            return struct.unpack(">H", self.data[1:3])[0]
        if self.kind == Kind.KEYBOARD_TURBO and len(self.data) >= 4:
            return struct.unpack(">H", self.data[2:4])[0]
        return None

    def same_as(self, other: "Action") -> bool:
        return self.kind == other.kind and self.data == other.data

    # ------------------------------------------------------------ display
    def category(self) -> str:
        k = self.kind
        if k in (Kind.MOUSE, Kind.DOUBLE_CLICK, Kind.MOUSE_TURBO):
            return "mouse"
        if k in (Kind.KEYBOARD, Kind.KEYBOARD_TURBO):
            return "keyboard"
        if k in MACRO_KINDS:
            return "macro"
        return {Kind.DISABLED: "disabled", Kind.DPI: "dpi", Kind.PROFILE: "profile",
                Kind.SYSTEM: "system", Kind.CONSUMER: "media",
                Kind.HYPERSHIFT: "hypershift", Kind.SCROLL_MODE: "scroll"}.get(k, "unknown")

    def describe(self, macro_names: dict[int, str] | None = None) -> str:
        k, d = self.kind, self.data
        try:
            if k == Kind.DISABLED:
                return "Disabled"
            if k in (Kind.MOUSE, Kind.DOUBLE_CLICK, Kind.MOUSE_TURBO):
                name = MOUSE_FN_NAMES.get(d[0], f"Mouse 0x{d[0]:02X}")
                if k == Kind.DOUBLE_CLICK:
                    return f"Double Click: {name}"
                if k == Kind.MOUSE_TURBO:
                    return f"{name} (Turbo {self._turbo_rate()}/s)"
                return name
            if k in (Kind.KEYBOARD, Kind.KEYBOARD_TURBO):
                text = combo_text(d[0], d[1])
                if k == Kind.KEYBOARD_TURBO:
                    return f"{text} (Turbo {self._turbo_rate()}/s)"
                return text
            if k in MACRO_KINDS:
                mid = self.macro_id
                name = (macro_names or {}).get(mid, f"Macro #{mid}")
                mode = MACRO_MODE_NAMES[Kind(k)].format(times=self.macro_times)
                return f"Macro: {name} ({mode})"
            if k == Kind.DPI:
                op = d[0]
                if op == DpiOp.STAGE:
                    return f"Sensitivity Stage {d[1]}"
                if op == DpiOp.CLUTCH:
                    x, y = struct.unpack(">HH", d[1:5])
                    return f"Sensitivity Clutch ({x} DPI)" if x == y else \
                        f"Sensitivity Clutch ({x}x{y} DPI)"
                return DPI_OP_NAMES.get(op, f"DPI op 0x{op:02X}")
            if k == Kind.PROFILE:
                op = d[0]
                if op == ProfileOp.SET:
                    return f"Switch to Profile {d[1]} ({PROFILE_COLORS.get(d[1], '?')})"
                return PROFILE_OP_NAMES.get(op, f"Profile op 0x{op:02X}")
            if k == Kind.SYSTEM:
                return SYSTEM_FN_NAMES.get(d[0], f"System 0x{d[0]:02X}")
            if k == Kind.CONSUMER:
                return consumer_name(struct.unpack(">H", d[:2])[0])
            if k == Kind.HYPERSHIFT:
                return "Hypershift (hold)"
            if k == Kind.SCROLL_MODE:
                return "Scroll Wheel Mode Toggle"
        except (IndexError, struct.error):
            pass
        return f"Unknown ({self.encode().hex(' ')})"

    def _turbo_rate(self) -> str:
        ms = self.turbo_ms or 0
        return f"{1000 / ms:.0f}" if ms else "?"


def parse_action(text: str) -> Action:
    """Parse a CLI action description.

    Examples:
        disable                     key:ctrl+c            key:a:turbo=50
        mouse:left                  mouse:left:double     mouse:wheelup:turbo=20
        macro:3                     macro:3:times=5       macro:3:hold
        macro:3:toggle              macro:3:sequence      dpi:cycle
        dpi:up / dpi:down / dpi:stage=2 / dpi:clutch=400
        profile:cycle / profile:next / profile:prev / profile:3
        media:volup                 media:0xcd            system:sleep
        hypershift                  scrollmode            raw:02020004
    """
    parts = text.strip().split(":")
    head = parts[0].lower()
    opts: dict[str, str] = {}
    flags: set[str] = set()
    for p in parts[2:]:
        if "=" in p:
            key, _, value = p.partition("=")
            opts[key.lower()] = value
        else:
            flags.add(p.lower())
    arg = parts[1] if len(parts) > 1 else ""

    def num(value: str) -> int:
        return int(value, 0)

    if head in ("disable", "disabled", "none", "off"):
        return Action.disabled()
    if head == "raw":
        raw = bytes.fromhex(arg)
        return Action(raw[0], raw[1:]) if raw else Action.disabled()
    if head == "key":
        mods, usage = parse_combo(arg)
        turbo = num(opts["turbo"]) if "turbo" in opts else None
        return Action.keyboard(usage, mods, turbo_ms=turbo)
    if head == "mouse":
        fn = MOUSE_FN_TOKENS.get(arg.lower())
        if fn is None:
            raise ValueError(f"unknown mouse function '{arg}'")
        turbo = num(opts["turbo"]) if "turbo" in opts else None
        return Action.mouse(fn, double_click="double" in flags, turbo_ms=turbo)
    if head == "macro":
        mid = num(arg)
        # options may also appear as bare words: macro:3:hold
        words = flags | set(opts)
        if "hold" in words:
            return Action.macro(mid, Kind.MACRO_HOLD)
        if "toggle" in words:
            return Action.macro(mid, Kind.MACRO_TOGGLE)
        if "sequence" in words:
            return Action.macro(mid, Kind.MACRO_SEQUENCE)
        return Action.macro(mid, Kind.MACRO_TIMES, num(opts.get("times", "1")))
    if head == "dpi":
        a = arg.lower()
        if a.startswith("stage="):
            return Action.dpi(DpiOp.STAGE, stage=num(a[6:]))
        if a.startswith("clutch="):
            values = a[7:].split("x")
            x = num(values[0])
            y = num(values[1]) if len(values) > 1 else x
            return Action.dpi(DpiOp.CLUTCH, dpi_x=x, dpi_y=y)
        ops = {"cycle": DpiOp.CYCLE_UP, "cycleup": DpiOp.CYCLE_UP,
               "cycledown": DpiOp.CYCLE_DOWN, "up": DpiOp.NEXT, "down": DpiOp.PREV,
               "next": DpiOp.NEXT, "prev": DpiOp.PREV}
        if a not in ops:
            raise ValueError(f"unknown dpi function '{arg}'")
        return Action.dpi(ops[a])
    if head == "profile":
        a = arg.lower()
        ops = {"cycle": ProfileOp.CYCLE_UP, "cycleup": ProfileOp.CYCLE_UP,
               "cycledown": ProfileOp.CYCLE_DOWN, "next": ProfileOp.NEXT,
               "prev": ProfileOp.PREV}
        if a in ops:
            return Action.profile(ops[a])
        return Action.profile(ProfileOp.SET, num(a))
    if head in ("media", "consumer"):
        a = arg.lower()
        usage = CONSUMER_TOKENS.get(a)
        if usage is None:
            usage = num(a)
        return Action.consumer(usage)
    if head == "system":
        fns = {"power": SystemFn.POWER_DOWN, "poweroff": SystemFn.POWER_DOWN,
               "sleep": SystemFn.SLEEP, "wake": SystemFn.WAKE}
        if arg.lower() not in fns:
            raise ValueError(f"unknown system function '{arg}'")
        return Action.system(fns[arg.lower()])
    if head == "hypershift":
        return Action.hypershift()
    if head in ("scrollmode", "scroll"):
        return Action.scroll_mode()
    raise ValueError(f"unknown action '{text}'")
