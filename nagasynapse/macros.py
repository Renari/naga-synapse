"""Macro model and the on-device macro byte format.

Device encoding (one operation after another):

    01 uu        key down (HID usage)
    02 uu        key up
    03 ss / 04   system control state (0 = released)
    05 hh ll     consumer control state (0 = released)
    08 mm        mouse button state bitmask (L=1 R=2 M=4 Back=8 Fwd=16)
    0a dd        wheel (signed ticks, +1 = up)
    11 tt        delay, 1 byte milliseconds
    12 hh ll     delay, 2 byte milliseconds
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .hid_usage import consumer_name, key_name, text_to_keys

OP_KEY_DOWN = 0x01
OP_KEY_UP = 0x02
OP_SYSTEM = 0x03
OP_SYSTEM_B = 0x04
OP_CONSUMER = 0x05
OP_CONSUMER_B = 0x06
OP_MOUSE = 0x08
OP_WHEEL = 0x0A
OP_DELAY_1 = 0x11
OP_DELAY_2 = 0x12

_OP_SIZE = {OP_KEY_DOWN: 1, OP_KEY_UP: 1, OP_SYSTEM: 1, OP_SYSTEM_B: 1,
            OP_CONSUMER: 2, OP_CONSUMER_B: 2, OP_MOUSE: 1, OP_WHEEL: 1,
            OP_DELAY_1: 1, OP_DELAY_2: 2}

MOUSE_BITS = {"left": 0x01, "right": 0x02, "middle": 0x04, "back": 0x08, "forward": 0x10}
MOUSE_BUTTON_NAMES = {"left": "Left", "right": "Right", "middle": "Middle",
                      "back": "Back", "forward": "Forward"}
SYSTEM_NAMES = {1: "Power Down", 2: "Sleep", 4: "Wake"}


@dataclass
class MacroEvent:
    """One step of a macro.

    type: key | mouse | wheel | delay | media | system
    code: HID usage (key), button name (mouse), consumer usage (media),
          system bit (system), ticks (wheel), milliseconds (delay)
    down: press (True) or release (False) for key/mouse/media/system
    """

    type: str
    code: int | str = 0
    down: bool = True

    def describe(self) -> str:
        arrow = "↓" if self.down else "↑"
        if self.type == "key":
            return f"{arrow} {key_name(int(self.code))}"
        if self.type == "mouse":
            return f"{arrow} Mouse {MOUSE_BUTTON_NAMES.get(str(self.code), self.code)}"
        if self.type == "media":
            return f"{arrow} {consumer_name(int(self.code))}"
        if self.type == "system":
            return f"{arrow} System {SYSTEM_NAMES.get(int(self.code), self.code)}"
        if self.type == "wheel":
            ticks = int(self.code)
            return f"Scroll {'up' if ticks > 0 else 'down'} ×{abs(ticks)}"
        if self.type == "delay":
            return f"Delay {int(self.code)} ms"
        return f"{self.type} {self.code}"

    def to_json(self) -> dict:
        obj = {"type": self.type, "code": self.code}
        if self.type in ("key", "mouse", "media", "system"):
            obj["down"] = self.down
        return obj

    @classmethod
    def from_json(cls, obj: dict) -> "MacroEvent":
        return cls(obj["type"], obj.get("code", 0), bool(obj.get("down", True)))


def key(usage: int, down: bool) -> MacroEvent:
    return MacroEvent("key", usage, down)


def delay(ms: int) -> MacroEvent:
    return MacroEvent("delay", int(ms))


@dataclass
class Macro:
    name: str = "New Macro"
    events: list[MacroEvent] = field(default_factory=list)
    id: int | None = None

    # ---------------------------------------------------------- encoding
    def encode(self) -> bytes:
        out = bytearray()
        mouse_state = 0
        for ev in self.events:
            if ev.type == "key":
                out += bytes([OP_KEY_DOWN if ev.down else OP_KEY_UP, int(ev.code) & 0xFF])
            elif ev.type == "mouse":
                bit = MOUSE_BITS[str(ev.code)]
                mouse_state = (mouse_state | bit) if ev.down else (mouse_state & ~bit)
                out += bytes([OP_MOUSE, mouse_state])
            elif ev.type == "wheel":
                ticks = int(ev.code)
                while ticks:
                    step = max(-127, min(127, ticks))
                    out += bytes([OP_WHEEL]) + struct.pack(">b", step)
                    ticks -= step
            elif ev.type == "delay":
                ms = max(0, int(ev.code))
                while ms > 0:
                    step = min(ms, 0xFFFF)
                    if step < 0x100:
                        out += bytes([OP_DELAY_1, step])
                    else:
                        out += bytes([OP_DELAY_2]) + struct.pack(">H", step)
                    ms -= step
            elif ev.type == "media":
                usage = int(ev.code) if ev.down else 0
                out += bytes([OP_CONSUMER]) + struct.pack(">H", usage)
            elif ev.type == "system":
                out += bytes([OP_SYSTEM, int(ev.code) if ev.down else 0])
            else:
                raise ValueError(f"unknown macro event type {ev.type!r}")
        # never leave mouse buttons stuck down
        if mouse_state:
            out += bytes([OP_MOUSE, 0])
        return bytes(out)

    @classmethod
    def decode(cls, data: bytes, name: str = "", macro_id: int | None = None) -> "Macro":
        events: list[MacroEvent] = []
        mouse_state = 0
        media_down = 0
        system_down = 0
        i = 0
        while i < len(data):
            op = data[i]
            size = _OP_SIZE.get(op)
            if size is None or i + 1 + size > len(data):
                break  # unknown / truncated op: stop parsing
            arg = data[i + 1:i + 1 + size]
            i += 1 + size
            if op in (OP_KEY_DOWN, OP_KEY_UP):
                events.append(key(arg[0], op == OP_KEY_DOWN))
            elif op == OP_MOUSE:
                new = arg[0]
                for name_, bit in MOUSE_BITS.items():
                    if (new ^ mouse_state) & bit:
                        events.append(MacroEvent("mouse", name_, bool(new & bit)))
                mouse_state = new
            elif op == OP_WHEEL:
                events.append(MacroEvent("wheel", struct.unpack(">b", arg)[0]))
            elif op == OP_DELAY_1:
                events.append(delay(arg[0]))
            elif op == OP_DELAY_2:
                events.append(delay(struct.unpack(">H", arg)[0]))
            elif op in (OP_CONSUMER, OP_CONSUMER_B):
                usage = struct.unpack(">H", arg)[0]
                if usage:
                    events.append(MacroEvent("media", usage, True))
                    media_down = usage
                elif media_down:
                    events.append(MacroEvent("media", media_down, False))
                    media_down = 0
            elif op in (OP_SYSTEM, OP_SYSTEM_B):
                if arg[0]:
                    events.append(MacroEvent("system", arg[0], True))
                    system_down = arg[0]
                elif system_down:
                    events.append(MacroEvent("system", system_down, False))
                    system_down = 0
        return cls(name=name, events=events, id=macro_id)

    # ------------------------------------------------------------ helpers
    def to_json(self) -> dict:
        return {"name": self.name, "id": self.id,
                "events": [e.to_json() for e in self.events]}

    @classmethod
    def from_json(cls, obj: dict) -> "Macro":
        return cls(name=obj.get("name", "Macro"),
                   events=[MacroEvent.from_json(e) for e in obj.get("events", [])],
                   id=obj.get("id"))

    def duration_ms(self) -> int:
        return sum(int(e.code) for e in self.events if e.type == "delay")

    def stuck_keys(self) -> list[str]:
        """Keys/buttons pressed but never released (would stay held)."""
        last: dict[tuple[str, str], MacroEvent] = {}
        for e in self.events:
            if e.type in ("key", "mouse", "media", "system"):
                last[(e.type, str(e.code))] = e
        return [e.describe()[2:] for e in last.values() if e.down]


def text_events(text: str, key_delay: int = 10) -> list[MacroEvent]:
    """Events that type `text` (US layout)."""
    events: list[MacroEvent] = []
    for usage, shift in text_to_keys(text):
        if shift:
            events.append(key(0xE1, True))
        events.append(key(usage, True))
        if key_delay:
            events.append(delay(key_delay))
        events.append(key(usage, False))
        if shift:
            events.append(key(0xE1, False))
        if key_delay:
            events.append(delay(key_delay))
    return events


def parse_steps(spec: str) -> list[MacroEvent]:
    """Parse a compact macro description used by the CLI.

    Comma separated steps:
        a / ctrl+c        tap a key or combo
        +shift / -shift   press / release a key
        click:left        click a mouse button  (+mouse:left / -mouse:left)
        wheel:3 / wheel:-2
        delay:50 / 50ms
        text:Hello World
        media:volup       tap a media key
    """
    from .hid_usage import CONSUMER_TOKENS, parse_combo, MODIFIER_BITS

    events: list[MacroEvent] = []
    mod_usage = {bit: usage for usage, bit in MODIFIER_BITS.items()}
    for raw_step in _split_steps(spec):
        step = raw_step.strip()
        if not step:
            continue
        low = step.lower()
        if low.startswith("text:"):
            events += text_events(step[5:])
        elif low.startswith("delay:") or (low.endswith("ms") and low[:-2].isdigit()):
            ms = int(low[6:] if low.startswith("delay:") else low[:-2])
            events.append(delay(ms))
        elif low.startswith("wheel:"):
            events.append(MacroEvent("wheel", int(low[6:])))
        elif low.startswith(("click:", "+mouse:", "-mouse:")):
            button = low.split(":", 1)[1]
            if button not in MOUSE_BITS:
                raise ValueError(f"unknown mouse button '{button}'")
            if low.startswith("click:"):
                events += [MacroEvent("mouse", button, True), delay(20),
                           MacroEvent("mouse", button, False)]
            else:
                events.append(MacroEvent("mouse", button, low[0] == "+"))
        elif low.startswith("media:"):
            name = low[6:]
            usage = CONSUMER_TOKENS.get(name)
            if usage is None:
                usage = int(name, 0)
            events += [MacroEvent("media", usage, True), delay(20),
                       MacroEvent("media", usage, False)]
        elif low[0] in "+-" and len(low) > 1:
            mods, usage = parse_combo(low[1:])
            events.append(key(usage, low[0] == "+"))
        else:
            mods, usage = parse_combo(low)
            mod_keys = [mod_usage[bit] for bit in sorted(mod_usage) if mods & bit]
            for m in mod_keys:
                events.append(key(m, True))
            events.append(key(usage, True))
            events.append(delay(20))
            events.append(key(usage, False))
            for m in reversed(mod_keys):
                events.append(key(m, False))
    return events


def _split_steps(spec: str) -> list[str]:
    # split on commas, but keep commas that are part of "text:" steps escaped as \,
    steps, current, escape = [], "", False
    for ch in spec:
        if escape:
            current += ch
            escape = False
        elif ch == "\\":
            escape = True
        elif ch == ",":
            steps.append(current)
            current = ""
        else:
            current += ch
    steps.append(current)
    return steps
