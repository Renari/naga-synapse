"""Physical buttons of the supported mice.

Button ids come from the device itself (command 02:84 lists them). The
factory default bindings below were read back from a freshly reset profile.

Supported models share the side plates but differ on top: the Naga V2 Pro
has a scroll-mode button and one DPI button, the Naga Pro (2020) has two DPI
buttons (up and down). The module-level BUTTONS / BUTTONS_BY_ID / BUTTON_IDS
describe the model of the connected mouse; use_model() switches them.
"""

from __future__ import annotations

from dataclasses import dataclass

from .actions import Action


@dataclass(frozen=True)
class Button:
    id: int
    name: str
    short: str
    group: str          # top | bottom | side2 | side6 | side12
    default: bytes      # raw 7 byte factory binding


def _b(id_, name, short, group, default_hex):
    return Button(id_, name, short, group, bytes.fromhex(default_hex))


_COMMON_TOP = [
    _b(0x01, "Left Click", "Left", "top", "01010100000000"),
    _b(0x02, "Right Click", "Right", "top", "01010200000000"),
    _b(0x03, "Scroll Click", "Wheel", "top", "01010300000000"),
    _b(0x09, "Scroll Up", "Up", "top", "01010900000000"),
    _b(0x0A, "Scroll Down", "Down", "top", "01010a00000000"),
]

_V2_PRO_TOP = [
    *_COMMON_TOP,
    _b(0x34, "Scroll Tilt Left", "Tilt L", "top", "0e016800140000"),
    _b(0x35, "Scroll Tilt Right", "Tilt R", "top", "0e016900140000"),
    _b(0x6D, "Scroll Mode Button", "Mode", "top", "12010400000000"),
    _b(0x60, "DPI Button", "DPI", "top", "06010600000000"),
    _b(0x0E, "Bottom Button", "Bottom", "bottom", "07010400000000"),
]

# Naga Pro (2020) factory tilt repeats wheel up/down, not left/right.
_NAGA_PRO_TOP = [
    *_COMMON_TOP,
    _b(0x34, "Scroll Tilt Left", "Tilt L", "top", "0e010900140000"),
    _b(0x35, "Scroll Tilt Right", "Tilt R", "top", "0e010a00140000"),
    _b(0x0B, "DPI Up Button", "DPI +", "top", "06010100000000"),
    _b(0x0C, "DPI Down Button", "DPI −", "top", "06010200000000"),
    _b(0x0E, "Bottom Button", "Bottom", "bottom", "07010400000000"),
]

_SIDE_PLATE_BUTTONS = [
    # 2-button side plate
    _b(0x05, "Side Button Front", "Front", "side2", "01010500000000"),
    _b(0x04, "Side Button Rear", "Rear", "side2", "01010400000000"),
    # 6-button side plate
    *[_b(0x50 + i, f"Side Button {i + 1}", str(i + 1), "side6",
         f"020100{0x1E + i:02x}000000") for i in range(6)],
    # 12-button side plate
    *[_b(0x40 + i, f"Side Button {i + 1}", str(i + 1), "side12",
         f"020100{usage:02x}000000")
      for i, usage in enumerate([0x1E, 0x1F, 0x20, 0x21, 0x22, 0x23, 0x24, 0x25,
                                 0x26, 0x27, 0x2D, 0x2E])],
]


@dataclass(frozen=True)
class Model:
    key: str
    name: str
    buttons: tuple[Button, ...]
    dpi_max: int
    # The two small buttons behind the wheel, front then rear (for drawing).
    centre_buttons: tuple[int, int]
    aliases: tuple[tuple[str, int], ...] = ()

    @property
    def by_id(self) -> dict[int, Button]:
        return {b.id: b for b in self.buttons}


MODELS: dict[str, Model] = {
    "naga-v2-pro": Model(
        "naga-v2-pro", "Razer Naga V2 Pro", tuple(_V2_PRO_TOP + _SIDE_PLATE_BUTTONS),
        dpi_max=30000, centre_buttons=(0x6D, 0x60),
        aliases=(("scrollmode", 0x6D), ("mode", 0x6D), ("dpi", 0x60)),
    ),
    "naga-pro": Model(
        "naga-pro", "Razer Naga Pro", tuple(_NAGA_PRO_TOP + _SIDE_PLATE_BUTTONS),
        dpi_max=20000, centre_buttons=(0x0B, 0x0C),
        aliases=(("dpi", 0x0B), ("dpiup", 0x0B), ("dpi+", 0x0B),
                 ("dpidown", 0x0C), ("dpi-", 0x0C)),
    ),
}

MODEL_BY_PID: dict[int, str] = {
    0x00A7: "naga-v2-pro", 0x00A8: "naga-v2-pro",
    0x008F: "naga-pro", 0x0090: "naga-pro",
}

MODEL: Model = MODELS["naga-v2-pro"]
# Mutated in place by use_model(), so `from .layout import BUTTONS` stays valid.
# Only switch models on the thread that reads these (the GUI thread); code on
# other threads should use NagaDevice.model instead.
BUTTONS: list[Button] = list(MODEL.buttons)
BUTTONS_BY_ID: dict[int, Button] = {b.id: b for b in BUTTONS}
BUTTON_IDS: list[int] = [b.id for b in BUTTONS]


def use_model(key: str) -> Model:
    """Switch the module-level button tables to another model."""
    global MODEL
    MODEL = MODELS[key]
    BUTTONS[:] = MODEL.buttons
    BUTTONS_BY_ID.clear()
    BUTTONS_BY_ID.update({b.id: b for b in BUTTONS})
    BUTTON_IDS[:] = [b.id for b in BUTTONS]
    return MODEL


def model_for_pid(pid: int) -> Model:
    return MODELS[MODEL_BY_PID.get(pid, "naga-v2-pro")]


def dpi_max() -> int:
    return MODEL.dpi_max

SIDE_PLATES = {
    "side2": "2-Button",
    "side6": "6-Button",
    "side12": "12-Button",
}

# Side-plate query (00:b9) value -> plate group.
PLATE_BY_VALUE = {0x01: "side2", 0x04: "side6", 0x03: "side12"}

GROUP_NAMES = {
    "top": "Top",
    "bottom": "Bottom",
    **SIDE_PLATES,
}

PROFILE_SLOTS = (1, 2, 3, 4, 5)
PROFILE_COLOR_HEX = {1: "#e8e8e8", 2: "#ff3b3b", 3: "#44d62c", 4: "#3b82ff", 5: "#22e3e3"}

POLLING_RATES = {1: 1000, 2: 500, 8: 125}

DPI_MIN = 100
DPI_MAX = 30000  # highest of any supported model; see dpi_max() for the current one
MAX_DPI_STAGES = 5

# Lift-off distance (0b:8b / 0b:0b) values. 0 means the firmware default.
LIFT_OFF = {
    0x0000: "Default",
    0x0100: "1 mm",
    0x0101: "2 mm",
    0x0102: "3 mm",
    0x0200: "Asymmetric 1–2 mm",
    0x0201: "Asymmetric 1–3 mm",
    0x0202: "Asymmetric 2–3 mm",
}


def default_action(button_id: int, model: Model | None = None) -> Action:
    """Factory binding of a button, for the current model or the given one."""
    button = (model.by_id if model else BUTTONS_BY_ID).get(button_id)
    return Action.decode(button.default) if button else Action.disabled()


def button_label(button_id: int) -> str:
    button = BUTTONS_BY_ID.get(button_id)
    if not button:
        return f"Button 0x{button_id:02X}"
    if button.group.startswith("side"):
        return f"{button.name} ({SIDE_PLATES[button.group]} plate)"
    return button.name


def find_button(token: str) -> int:
    """Resolve a CLI button reference: hex id, name, or plate:number."""
    t = token.strip().lower()
    if t.startswith("0x"):
        return int(t, 16)
    aliases = {
        "left": 0x01, "right": 0x02, "middle": 0x03, "wheel": 0x03,
        "scrollup": 0x09, "wheelup": 0x09, "scrolldown": 0x0A, "wheeldown": 0x0A,
        "tiltleft": 0x34, "tiltright": 0x35, "bottom": 0x0E, "profile": 0x0E,
        "front": 0x05, "rear": 0x04, "side2:1": 0x05, "side2:2": 0x04,
        **dict(MODEL.aliases),
    }
    if t in aliases:
        return aliases[t]
    for prefix, base, count in (("side12:", 0x40, 12), ("side6:", 0x50, 6),
                                ("12:", 0x40, 12), ("6:", 0x50, 6)):
        if t.startswith(prefix):
            n = int(t[len(prefix):])
            if not 1 <= n <= count:
                raise ValueError(f"{prefix} buttons are numbered 1-{count}")
            return base + n - 1
    if t.isdigit():
        n = int(t)
        if 1 <= n <= 12:
            return 0x40 + n - 1
    raise ValueError(f"unknown button '{token}'")
