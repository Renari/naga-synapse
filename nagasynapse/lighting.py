"""Lighting through the openrazer kernel driver's sysfs files.

The Naga V2 Pro thumb grid needs model specific quirks that the openrazer
driver already implements, so lighting is delegated to it instead of being
re-implemented here. Requires openrazer-driver and membership of the
`openrazer` group.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ZONES = {
    "logo": ("Logo", "logo_matrix_effect_", "logo_led_brightness"),
    "thumb": ("Thumb grid (12-button plate)", "matrix_effect_", "matrix_brightness"),
}

EFFECTS = {
    "static": "Static",
    "breath": "Breathing",
    "spectrum": "Spectrum cycling",
    "wave": "Wave",
    "reactive": "Reactive",
    "none": "Off",
}


class LightingError(Exception):
    pass


@dataclass
class Lighting:
    sysfs: Path

    @classmethod
    def for_hidraw(cls, hidraw_path: str) -> "Lighting | None":
        node = Path("/sys/class/hidraw") / Path(hidraw_path).name / "device"
        if not (node / "logo_matrix_effect_static").exists():
            return None
        return cls(node)

    def writable(self) -> bool:
        return os.access(self.sysfs / "logo_matrix_effect_static", os.W_OK)

    def zones(self) -> list[str]:
        return [z for z, (_n, prefix, _b) in ZONES.items()
                if (self.sysfs / f"{prefix}static").exists()]

    def effects(self, zone: str) -> list[str]:
        prefix = ZONES[zone][1]
        return [e for e in EFFECTS if (self.sysfs / f"{prefix}{e}").exists()]

    def _write(self, name: str, data: bytes) -> None:
        try:
            (self.sysfs / name).write_bytes(data)
        except PermissionError as exc:
            raise LightingError("No permission to change lighting. Add yourself to the "
                                "'openrazer' group and log in again.") from exc
        except OSError as exc:
            raise LightingError(f"Lighting change failed: {exc}") from exc

    def brightness(self, zone: str) -> int | None:
        try:
            return int((self.sysfs / ZONES[zone][2]).read_text().strip())
        except (OSError, ValueError):
            return None

    def set_brightness(self, zone: str, value: int) -> None:
        self._write(ZONES[zone][2], str(max(0, min(255, value))).encode())

    def set_effect(self, zone: str, effect: str, colors: list[tuple[int, int, int]] = (),
                   speed: int = 2, direction: int = 1) -> None:
        prefix = ZONES[zone][1]
        if effect == "static":
            data = bytes(colors[0])
        elif effect == "breath":
            data = b"".join(bytes(c) for c in colors[:2]) if colors else b"\x01"
        elif effect == "reactive":
            data = bytes([max(1, min(4, speed)), *colors[0]])
        elif effect == "wave":
            data = str(direction).encode()
        else:  # spectrum / none
            data = b"1"
        self._write(f"{prefix}{effect}", data)
