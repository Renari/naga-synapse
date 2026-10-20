"""HID usage tables: keyboard keys, consumer (media) keys and conversions.

The device speaks USB HID usage ids. When recording on Linux we get evdev
key codes (Qt's nativeScanCode is the XKB keycode = evdev code + 8).
"""

from __future__ import annotations

# (hid usage, evdev keycode, display name, short token used by the CLI)
_KEYS = [
    (0x04, 30, "A", "a"), (0x05, 48, "B", "b"), (0x06, 46, "C", "c"),
    (0x07, 32, "D", "d"), (0x08, 18, "E", "e"), (0x09, 33, "F", "f"),
    (0x0A, 34, "G", "g"), (0x0B, 35, "H", "h"), (0x0C, 23, "I", "i"),
    (0x0D, 36, "J", "j"), (0x0E, 37, "K", "k"), (0x0F, 38, "L", "l"),
    (0x10, 50, "M", "m"), (0x11, 49, "N", "n"), (0x12, 24, "O", "o"),
    (0x13, 25, "P", "p"), (0x14, 16, "Q", "q"), (0x15, 19, "R", "r"),
    (0x16, 31, "S", "s"), (0x17, 20, "T", "t"), (0x18, 22, "U", "u"),
    (0x19, 47, "V", "v"), (0x1A, 17, "W", "w"), (0x1B, 45, "X", "x"),
    (0x1C, 21, "Y", "y"), (0x1D, 44, "Z", "z"),
    (0x1E, 2, "1", "1"), (0x1F, 3, "2", "2"), (0x20, 4, "3", "3"),
    (0x21, 5, "4", "4"), (0x22, 6, "5", "5"), (0x23, 7, "6", "6"),
    (0x24, 8, "7", "7"), (0x25, 9, "8", "8"), (0x26, 10, "9", "9"),
    (0x27, 11, "0", "0"),
    (0x28, 28, "Enter", "enter"), (0x29, 1, "Esc", "esc"),
    (0x2A, 14, "Backspace", "backspace"), (0x2B, 15, "Tab", "tab"),
    (0x2C, 57, "Space", "space"), (0x2D, 12, "-", "minus"),
    (0x2E, 13, "=", "equal"), (0x2F, 26, "[", "lbracket"),
    (0x30, 27, "]", "rbracket"), (0x31, 43, "\\", "backslash"),
    (0x32, None, "# (ISO)", "nonus_hash"), (0x33, 39, ";", "semicolon"),
    (0x34, 40, "'", "apostrophe"), (0x35, 41, "`", "grave"),
    (0x36, 51, ",", "comma"), (0x37, 52, ".", "period"),
    (0x38, 53, "/", "slash"), (0x39, 58, "Caps Lock", "capslock"),
    (0x3A, 59, "F1", "f1"), (0x3B, 60, "F2", "f2"), (0x3C, 61, "F3", "f3"),
    (0x3D, 62, "F4", "f4"), (0x3E, 63, "F5", "f5"), (0x3F, 64, "F6", "f6"),
    (0x40, 65, "F7", "f7"), (0x41, 66, "F8", "f8"), (0x42, 67, "F9", "f9"),
    (0x43, 68, "F10", "f10"), (0x44, 87, "F11", "f11"), (0x45, 88, "F12", "f12"),
    (0x46, 99, "Print Screen", "printscreen"), (0x47, 70, "Scroll Lock", "scrolllock"),
    (0x48, 119, "Pause", "pause"), (0x49, 110, "Insert", "insert"),
    (0x4A, 102, "Home", "home"), (0x4B, 104, "Page Up", "pageup"),
    (0x4C, 111, "Delete", "delete"), (0x4D, 107, "End", "end"),
    (0x4E, 109, "Page Down", "pagedown"), (0x4F, 106, "Right", "right"),
    (0x50, 105, "Left", "left"), (0x51, 108, "Down", "down"),
    (0x52, 103, "Up", "up"), (0x53, 69, "Num Lock", "numlock"),
    (0x54, 98, "Num /", "kp_slash"), (0x55, 55, "Num *", "kp_asterisk"),
    (0x56, 74, "Num -", "kp_minus"), (0x57, 78, "Num +", "kp_plus"),
    (0x58, 96, "Num Enter", "kp_enter"), (0x59, 79, "Num 1", "kp_1"),
    (0x5A, 80, "Num 2", "kp_2"), (0x5B, 81, "Num 3", "kp_3"),
    (0x5C, 75, "Num 4", "kp_4"), (0x5D, 76, "Num 5", "kp_5"),
    (0x5E, 77, "Num 6", "kp_6"), (0x5F, 71, "Num 7", "kp_7"),
    (0x60, 72, "Num 8", "kp_8"), (0x61, 73, "Num 9", "kp_9"),
    (0x62, 82, "Num 0", "kp_0"), (0x63, 83, "Num .", "kp_period"),
    (0x64, 86, "\\ (ISO)", "nonus_backslash"), (0x65, 127, "Menu", "menu"),
    (0x66, 116, "Power", "power"), (0x67, 117, "Num =", "kp_equal"),
    (0x68, 183, "F13", "f13"), (0x69, 184, "F14", "f14"), (0x6A, 185, "F15", "f15"),
    (0x6B, 186, "F16", "f16"), (0x6C, 187, "F17", "f17"), (0x6D, 188, "F18", "f18"),
    (0x6E, 189, "F19", "f19"), (0x6F, 190, "F20", "f20"), (0x70, 191, "F21", "f21"),
    (0x71, 192, "F22", "f22"), (0x72, 193, "F23", "f23"), (0x73, 194, "F24", "f24"),
    (0x75, 138, "Help", "help"), (0x78, 128, "Stop", "stop"),
    (0x79, 129, "Again", "again"), (0x7A, 131, "Undo", "undo"),
    (0x7B, 137, "Cut", "cut"), (0x7C, 133, "Copy", "copy"),
    (0x7D, 135, "Paste", "paste"), (0x7E, 136, "Find", "find"),
    (0x7F, 113, "Mute", "mute"), (0x80, 115, "Volume Up", "volumeup"),
    (0x81, 114, "Volume Down", "volumedown"), (0x85, 121, "Num ,", "kp_comma"),
    (0x87, 89, "Ro", "ro"), (0x88, 93, "Katakana/Hiragana", "katakanahiragana"),
    (0x89, 124, "Yen", "yen"), (0x8A, 92, "Henkan", "henkan"),
    (0x8B, 94, "Muhenkan", "muhenkan"), (0x90, 122, "Hangeul", "hangeul"),
    (0x91, 123, "Hanja", "hanja"),
    (0xE0, 29, "Left Ctrl", "lctrl"), (0xE1, 42, "Left Shift", "lshift"),
    (0xE2, 56, "Left Alt", "lalt"), (0xE3, 125, "Left Super", "lsuper"),
    (0xE4, 97, "Right Ctrl", "rctrl"), (0xE5, 54, "Right Shift", "rshift"),
    (0xE6, 100, "Right Alt", "ralt"), (0xE7, 126, "Right Super", "rsuper"),
]

KEY_NAMES: dict[int, str] = {usage: name for usage, _ev, name, _tok in _KEYS}
KEY_TOKENS: dict[str, int] = {tok: usage for usage, _ev, _name, tok in _KEYS}
EVDEV_TO_HID: dict[int, int] = {ev: usage for usage, ev, _n, _t in _KEYS if ev is not None}
HID_TO_EVDEV: dict[int, int] = {usage: ev for usage, ev, _n, _t in _KEYS if ev is not None}

# Extra CLI aliases
KEY_TOKENS.update({
    "return": 0x28, "escape": 0x29, "bksp": 0x2A, "del": 0x4C, "ins": 0x49,
    "pgup": 0x4B, "pgdn": 0x4E, "-": 0x2D, "=": 0x2E, "[": 0x2F, "]": 0x30,
    ";": 0x33, "'": 0x34, "`": 0x35, ",": 0x36, ".": 0x37, "/": 0x38,
    "ctrl": 0xE0, "shift": 0xE1, "alt": 0xE2, "super": 0xE3, "win": 0xE3,
    "meta": 0xE3, "altgr": 0xE6, "prtsc": 0x46,
})

# Modifier usage -> bit in the keyboard action's modifier byte
MODIFIER_BITS = {0xE0: 0x01, 0xE1: 0x02, 0xE2: 0x04, 0xE3: 0x08,
                 0xE4: 0x10, 0xE5: 0x20, 0xE6: 0x40, 0xE7: 0x80}
MODIFIER_NAMES = [(0x01, "Ctrl"), (0x02, "Shift"), (0x04, "Alt"), (0x08, "Super"),
                  (0x10, "RCtrl"), (0x20, "RShift"), (0x40, "AltGr"), (0x80, "RSuper")]
MODIFIER_TOKENS = {"ctrl": 0x01, "lctrl": 0x01, "control": 0x01, "shift": 0x02,
                   "lshift": 0x02, "alt": 0x04, "lalt": 0x04, "super": 0x08,
                   "lsuper": 0x08, "win": 0x08, "meta": 0x08, "rctrl": 0x10,
                   "rshift": 0x20, "ralt": 0x40, "altgr": 0x40, "rsuper": 0x80}


def is_modifier(usage: int) -> bool:
    return 0xE0 <= usage <= 0xE7


def key_name(usage: int) -> str:
    return KEY_NAMES.get(usage, f"Key 0x{usage:02X}")


def modifiers_text(mask: int) -> list[str]:
    return [name for bit, name in MODIFIER_NAMES if mask & bit]


def combo_text(modifiers: int, usage: int) -> str:
    parts = modifiers_text(modifiers)
    if usage:
        parts.append(key_name(usage))
    return " + ".join(parts) if parts else "None"


def parse_combo(text: str) -> tuple[int, int]:
    """'ctrl+shift+a' -> (modifier mask, usage)."""
    modifiers = 0
    usage = 0
    tokens = [t for t in text.lower().replace(" ", "").split("+")]
    for i, tok in enumerate(tokens):
        if not tok and i == len(tokens) - 1 and len(tokens) > 1:
            tok = "+"
        last = i == len(tokens) - 1
        if not last and tok in MODIFIER_TOKENS:
            modifiers |= MODIFIER_TOKENS[tok]
            continue
        if tok.startswith("0x"):
            usage = int(tok, 16)
        elif tok in KEY_TOKENS:
            usage = KEY_TOKENS[tok]
        elif last and tok in MODIFIER_TOKENS:
            # a lone modifier, e.g. "shift"
            usage = {v: k for k, v in MODIFIER_BITS.items()}[MODIFIER_TOKENS[tok]]
        else:
            raise ValueError(f"unknown key '{tok}'")
    return modifiers, usage


# Consumer page (0x0C) usages
CONSUMER_KEYS: list[tuple[int, str]] = [
    (0x00CD, "Play / Pause"),
    (0x00B5, "Next Track"),
    (0x00B6, "Previous Track"),
    (0x00B7, "Stop"),
    (0x00E2, "Mute"),
    (0x00E9, "Volume Up"),
    (0x00EA, "Volume Down"),
    (0x006F, "Brightness Up"),
    (0x0070, "Brightness Down"),
    (0x0183, "Media Player"),
    (0x018A, "Email"),
    (0x0192, "Calculator"),
    (0x0194, "File Browser"),
    (0x0221, "Search"),
    (0x0223, "Browser Home"),
    (0x0224, "Browser Back"),
    (0x0225, "Browser Forward"),
    (0x0226, "Browser Stop"),
    (0x0227, "Browser Refresh"),
    (0x022A, "Browser Bookmarks"),
]
CONSUMER_NAMES = dict(CONSUMER_KEYS)
CONSUMER_TOKENS = {
    "playpause": 0xCD, "play": 0xCD, "next": 0xB5, "prev": 0xB6, "previous": 0xB6,
    "stop": 0xB7, "mute": 0xE2, "volup": 0xE9, "voldown": 0xEA,
    "brightnessup": 0x6F, "brightnessdown": 0x70, "calculator": 0x192,
    "email": 0x18A, "files": 0x194, "search": 0x221, "home": 0x223,
    "back": 0x224, "forward": 0x225, "refresh": 0x227, "bookmarks": 0x22A,
    "mediaplayer": 0x183,
}


def consumer_name(usage: int) -> str:
    return CONSUMER_NAMES.get(usage, f"Media 0x{usage:03X}")


# US layout: character -> (usage, needs shift). Used for "type text" macros.
_US_UNSHIFTED = "abcdefghijklmnopqrstuvwxyz1234567890"
_US_CHARS: dict[str, tuple[int, bool]] = {}
for _i, _c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    _US_CHARS[_c] = (0x04 + _i, False)
    _US_CHARS[_c.upper()] = (0x04 + _i, True)
for _i, _c in enumerate("1234567890"):
    _US_CHARS[_c] = (0x1E + _i, False)
for _i, _c in enumerate("!@#$%^&*()"):
    _US_CHARS[_c] = (0x1E + _i, True)
for _c, _u, _s in [
    ("\n", 0x28, False), ("\t", 0x2B, False), (" ", 0x2C, False),
    ("-", 0x2D, False), ("_", 0x2D, True), ("=", 0x2E, False), ("+", 0x2E, True),
    ("[", 0x2F, False), ("{", 0x2F, True), ("]", 0x30, False), ("}", 0x30, True),
    ("\\", 0x31, False), ("|", 0x31, True), (";", 0x33, False), (":", 0x33, True),
    ("'", 0x34, False), ('"', 0x34, True), ("`", 0x35, False), ("~", 0x35, True),
    (",", 0x36, False), ("<", 0x36, True), (".", 0x37, False), (">", 0x37, True),
    ("/", 0x38, False), ("?", 0x38, True),
]:
    _US_CHARS[_c] = (_u, _s)


def text_to_keys(text: str) -> list[tuple[int, bool]]:
    """Translate text into (usage, shift) pairs using a US layout."""
    out = []
    for ch in text:
        if ch not in _US_CHARS:
            raise ValueError(f"cannot type character {ch!r}")
        out.append(_US_CHARS[ch])
    return out
