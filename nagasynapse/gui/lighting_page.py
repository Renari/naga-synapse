"""LIGHTING tab (via the openrazer kernel driver)."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QComboBox, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QSlider, QVBoxLayout, QWidget)

from ..lighting import EFFECTS, ZONES, Lighting, LightingError
from .controller import Controller
from .widgets import dim, section


class ColorButton(QPushButton):
    def __init__(self, color: str):
        super().__init__()
        self.setFixedSize(46, 30)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_color(QColor(color))
        self.clicked.connect(self._pick)

    def set_color(self, color: QColor):
        self.color = color
        self.setStyleSheet(f"background: {color.name()}; border: 1px solid #555; "
                           "border-radius: 6px;")

    def _pick(self):
        color = QColorDialog.getColor(self.color, self, "Choose color")
        if color.isValid():
            self.set_color(color)

    def rgb(self) -> tuple[int, int, int]:
        return self.color.red(), self.color.green(), self.color.blue()


class ZonePanel(QFrame):
    def __init__(self, page: "LightingPage", zone: str):
        super().__init__()
        self.page = page
        self.zone = zone
        self.setObjectName("Panel")
        s = page.settings
        key = f"lighting/{zone}/"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        lay.addWidget(section(ZONES[zone][0]))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.addWidget(QLabel("Effect"), 0, 0)
        self.effect = QComboBox()
        for e in page.lighting.effects(zone):
            self.effect.addItem(EFFECTS[e], e)
        self.effect.setCurrentIndex(max(0, self.effect.findData(s.value(key + "effect",
                                                                         "spectrum"))))
        grid.addWidget(self.effect, 0, 1)
        self.colors_label = QLabel("Colors")
        grid.addWidget(self.colors_label, 1, 0)
        colors = QHBoxLayout()
        self.color1 = ColorButton(s.value(key + "color1", "#44d62c"))
        self.color2 = ColorButton(s.value(key + "color2", "#00a0ff"))
        self.mode = QComboBox()
        self.mode.addItem("One color", 1)
        self.mode.addItem("Two colors", 2)
        self.mode.addItem("Random", 0)
        self.mode.setCurrentIndex(max(0, self.mode.findData(int(s.value(key + "mode", 1)))))
        colors.addWidget(self.color1)
        colors.addWidget(self.color2)
        colors.addWidget(self.mode)
        colors.addStretch(1)
        grid.addLayout(colors, 1, 1)
        self.speed_label = QLabel("Speed")
        grid.addWidget(self.speed_label, 2, 0)
        self.speed = QComboBox()
        grid.addWidget(self.speed, 2, 1)
        grid.addWidget(QLabel("Brightness"), 3, 0)
        row = QHBoxLayout()
        self.brightness = QSlider(Qt.Orientation.Horizontal)
        self.brightness.setRange(0, 100)
        current = page.lighting.brightness(zone)
        self.brightness.setValue(round((current if current is not None else 255) * 100 / 255))
        self.bright_label = QLabel()
        self.bright_label.setMinimumWidth(48)
        row.addWidget(self.brightness, 1)
        row.addWidget(self.bright_label)
        grid.addLayout(row, 3, 1)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setObjectName("Primary")
        bottom.addWidget(self.apply_btn)
        lay.addLayout(bottom)

        self.effect.currentIndexChanged.connect(self._update)
        self.mode.currentIndexChanged.connect(self._update)
        self.brightness.valueChanged.connect(
            lambda v: self.bright_label.setText(f"{v}%"))
        self.brightness.sliderReleased.connect(self._apply_brightness)
        self.apply_btn.clicked.connect(self.apply)
        self.bright_label.setText(f"{self.brightness.value()}%")
        self._update()

    def _update(self):
        effect = self.effect.currentData()
        self.mode.setVisible(effect == "breath")
        two = effect == "breath" and self.mode.currentData() == 2
        random = effect == "breath" and self.mode.currentData() == 0
        self.color1.setVisible(effect in ("static", "breath", "reactive") and not random)
        self.color2.setVisible(two)
        self.speed.clear()
        if effect == "reactive":
            for i, name in enumerate(["Fast", "Medium", "Slow", "Very slow"], 1):
                self.speed.addItem(name, i)
        elif effect == "wave":
            self.speed.addItem("Forward", 1)
            self.speed.addItem("Backward", 2)
        self.speed_label.setText("Direction" if effect == "wave" else "Speed")
        self.speed_label.setVisible(self.speed.count() > 0)
        self.speed.setVisible(self.speed.count() > 0)
        self.colors_label.setVisible(effect in ("static", "breath", "reactive"))

    def apply(self):
        effect = self.effect.currentData()
        colors = [self.color1.rgb()]
        if effect == "breath":
            mode = self.mode.currentData()
            colors = [] if mode == 0 else [self.color1.rgb(), self.color2.rgb()][:mode]
        speed = self.speed.currentData() or 2
        try:
            self.page.lighting.set_effect(self.zone, effect, colors, speed=speed,
                                          direction=speed)
            self._apply_brightness()
        except LightingError as exc:
            self.page.ctl.error.emit(str(exc))
            return
        key = f"lighting/{self.zone}/"
        s = self.page.settings
        s.setValue(key + "effect", effect)
        s.setValue(key + "color1", self.color1.color.name())
        s.setValue(key + "color2", self.color2.color.name())
        s.setValue(key + "mode", self.mode.currentData())
        self.page.ctl.status.emit(f"{ZONES[self.zone][0]} lighting applied")

    def _apply_brightness(self):
        try:
            self.page.lighting.set_brightness(self.zone, round(self.brightness.value() * 255 / 100))
        except LightingError as exc:
            self.page.ctl.error.emit(str(exc))


class LightingPage(QWidget):
    def __init__(self, ctl: Controller, settings: QSettings):
        super().__init__()
        self.ctl = ctl
        self.settings = settings
        self.lighting: Lighting | None = None
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(28, 22, 28, 22)
        self.root.setSpacing(18)
        self.body = QWidget()
        self.root.addWidget(self.body)
        self.root.addStretch(1)
        ctl.connectionChanged.connect(lambda ok, _m: ok and self.rebuild())

    def rebuild(self):
        self.root.removeWidget(self.body)
        self.body.deleteLater()
        self.body = QWidget()
        self.root.insertWidget(0, self.body)
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(18)
        lay.addWidget(section("Lighting"))
        self.lighting = Lighting.for_hidraw(self.ctl.dev.hid.path) if self.ctl.dev else None
        if self.lighting is None:
            lay.addWidget(dim("Lighting control uses the openrazer kernel driver, which is not "
                              "loaded for this mouse. Install openrazer-driver-dkms to enable "
                              "this tab."))
            return
        if not self.lighting.writable():
            lay.addWidget(dim("Your user cannot change the lighting yet. Add yourself to the "
                              "'openrazer' group (sudo gpasswd -a $USER openrazer) and log in "
                              "again."))
            return
        lay.addWidget(dim("Lighting is applied immediately and kept by the mouse. If the "
                          "openrazer daemon is running it may restore its own lighting when "
                          "it restarts."))
        row = QHBoxLayout()
        row.setSpacing(18)
        for zone in self.lighting.zones():
            row.addWidget(ZonePanel(self, zone), 1)
        lay.addLayout(row)
