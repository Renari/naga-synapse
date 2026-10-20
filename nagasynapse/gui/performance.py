"""PERFORMANCE tab: sensitivity stages and polling rate."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QRadioButton, QScrollArea, QSlider,
                               QSpinBox, QVBoxLayout, QWidget)

from .. import layout
from ..layout import DPI_MAX, DPI_MIN, MAX_DPI_STAGES, POLLING_RATES
from .controller import Controller
from .widgets import Segmented, dim, section

STEP = 50
DEFAULT_STAGES = [400, 800, 1600, 3200, 6400]
RATES = [125, 500, 1000]
RATE_TO_INTERVAL = {v: k for k, v in POLLING_RATES.items()}


class StageRow:
    def __init__(self, grid: QGridLayout, row: int, group: QButtonGroup, on_change):
        self.radio = QRadioButton(f"Stage {row + 1}")
        group.addButton(self.radio, row)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(DPI_MIN // STEP, DPI_MAX // STEP)
        self.x = QSpinBox()
        self.y = QSpinBox()
        for spin in (self.x, self.y):
            spin.setRange(DPI_MIN, DPI_MAX)
            spin.setSingleStep(STEP)
            spin.setSuffix(" DPI")
            spin.setMinimumWidth(110)
        grid.addWidget(self.radio, row, 0)
        grid.addWidget(self.slider, row, 1)
        grid.addWidget(self.x, row, 2)
        grid.addWidget(self.y, row, 3)
        self.slider.valueChanged.connect(self._slider_moved)
        self.x.valueChanged.connect(self._x_changed)
        self.x.valueChanged.connect(on_change)
        self.y.valueChanged.connect(on_change)
        self.linked = True

    def _slider_moved(self, value: int):
        self.x.setValue(value * STEP)

    def _x_changed(self, value: int):
        self.slider.blockSignals(True)
        self.slider.setValue(value // STEP)
        self.slider.blockSignals(False)
        if self.linked:
            self.y.setValue(value)

    def set_maximum(self, maximum: int):
        self.slider.setRange(DPI_MIN // STEP, maximum // STEP)
        for spin in (self.x, self.y):
            spin.setMaximum(maximum)

    def set_visible(self, visible: bool, xy: bool):
        for w in (self.radio, self.slider, self.x):
            w.setVisible(visible)
        self.y.setVisible(visible and xy)

    def set_value(self, x: int, y: int):
        self.x.setValue(x)
        self.y.setValue(y)

    def value(self) -> tuple[int, int]:
        return self.x.value(), (self.y.value() if not self.linked else self.x.value())


class PerformancePage(QWidget):
    def __init__(self, ctl: Controller):
        super().__init__()
        self.ctl = ctl
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(18)

        # ---- sensitivity
        panel = QFrame()
        panel.setObjectName("Panel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(section("Sensitivity stages"))
        head.addStretch(1)
        head.addWidget(QLabel("Stages:"))
        self.count = QSpinBox()
        self.count.setRange(1, MAX_DPI_STAGES)
        head.addWidget(self.count)
        head.addSpacing(16)
        self.xy = QCheckBox("Separate X / Y sensitivity")
        head.addWidget(self.xy)
        lay.addLayout(head)
        lay.addWidget(dim("The DPI button(s) step through these stages. The selected stage "
                          "is the one the profile starts with."))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        self.active = QButtonGroup(self)
        self.rows = [StageRow(grid, i, self.active, self._dirty) for i in range(MAX_DPI_STAGES)]
        lay.addLayout(grid)
        bottom = QHBoxLayout()
        self.dpi_status = dim("", wrap=False)
        bottom.addWidget(self.dpi_status)
        bottom.addStretch(1)
        self.dpi_revert = QPushButton("Revert")
        self.dpi_save = QPushButton("Save sensitivity")
        self.dpi_save.setObjectName("Primary")
        bottom.addWidget(self.dpi_revert)
        bottom.addWidget(self.dpi_save)
        lay.addLayout(bottom)
        root.addWidget(panel)

        # ---- polling
        panel = QFrame()
        panel.setObjectName("Panel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        lay.addWidget(section("Polling rate"))
        lay.addWidget(dim("How often the mouse reports its position to the computer."))
        row = QHBoxLayout()
        self.rate = Segmented([f"{r} Hz" for r in RATES])
        row.addWidget(self.rate)
        row.addStretch(1)
        lay.addLayout(row)
        root.addWidget(panel)

        # ---- power
        panel = QFrame()
        panel.setObjectName("Panel")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        lay.addWidget(section("Power (all profiles)"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.addWidget(QLabel("Sleep after"), 0, 0)
        self.idle = QSlider(Qt.Orientation.Horizontal)
        self.idle.setRange(1, 15)
        self.idle_label = QLabel()
        self.idle_label.setMinimumWidth(90)
        grid.addWidget(self.idle, 0, 1)
        grid.addWidget(self.idle_label, 0, 2)
        grid.addWidget(QLabel("Low power mode at"), 1, 0)
        self.lowbat = QSlider(Qt.Orientation.Horizontal)
        self.lowbat.setRange(1, 20)
        self.lowbat_label = QLabel()
        grid.addWidget(self.lowbat, 1, 1)
        grid.addWidget(self.lowbat_label, 1, 2)
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)
        row = QHBoxLayout()
        row.addWidget(dim("Applies while the mouse runs on battery.", wrap=False))
        row.addStretch(1)
        self.power_save = QPushButton("Save power settings")
        row.addWidget(self.power_save)
        lay.addLayout(row)
        root.addWidget(panel)
        root.addStretch(1)
        self.idle.valueChanged.connect(
            lambda v: self.idle_label.setText(f"{v} minute{'s' if v != 1 else ''}"))
        self.lowbat.valueChanged.connect(lambda v: self.lowbat_label.setText(f"{v * 5}% battery"))
        self.power_save.clicked.connect(
            lambda: ctl.set_power(self.idle.value() * 60, self.lowbat.value() * 5))
        ctl.connectionChanged.connect(lambda *_: self._refresh_power())

        self.count.valueChanged.connect(self._layout_rows)
        self.xy.toggled.connect(self._layout_rows)
        self.active.idToggled.connect(lambda *_: self._dirty())
        self.dpi_save.clicked.connect(self._save_dpi)
        self.dpi_revert.clicked.connect(self.refresh)
        self.rate.changed.connect(self._save_rate)
        ctl.connectionChanged.connect(lambda ok, _msg: ok and self._set_dpi_max(layout.dpi_max()))
        ctl.profileLoaded.connect(lambda s: s == ctl.current_slot and self.refresh())
        ctl.performanceChanged.connect(lambda s: s == ctl.current_slot and self.refresh())
        ctl.currentSlotChanged.connect(lambda _s: self.refresh())
        self._loading = False
        self.refresh()

    def _layout_rows(self, *_):
        xy = self.xy.isChecked()
        for i, row in enumerate(self.rows):
            row.linked = not xy
            row.set_visible(i < self.count.value(), xy)
            if not xy:
                row.y.setValue(row.x.value())
        if self.active.checkedId() >= self.count.value():
            self.rows[self.count.value() - 1].radio.setChecked(True)
        self._dirty()

    def _dirty(self, *_):
        if not self._loading:
            self.dpi_status.setText("Unsaved changes")

    def refresh(self) -> None:
        data = self.ctl.profiles.get(self.ctl.current_slot)
        self.setEnabled(data is not None)
        if data is None:
            return
        self._loading = True
        stages = data.dpi_stages or [(800, 800)]
        xy = any(x != y for x, y in stages)
        self.xy.setChecked(xy)
        self.count.setValue(len(stages))
        for i, row in enumerate(self.rows):
            row.linked = not xy
            if i < len(stages):
                row.set_value(*stages[i])
            else:
                row.set_value(DEFAULT_STAGES[i], DEFAULT_STAGES[i])
        self.rows[max(0, min(data.dpi_active, len(stages)) - 1)].radio.setChecked(True)
        self._layout_rows()
        rate = POLLING_RATES.get(data.polling_interval, 1000)
        self.rate.set_index(RATES.index(rate) if rate in RATES else 2)
        self.dpi_status.setText(f"Editing {self.ctl.profile_title(self.ctl.current_slot)}")
        self._loading = False

    def _refresh_power(self) -> None:
        power = self.ctl.power
        self.power_save.setEnabled(power is not None)
        idle, low = power or (300, 15)
        self.idle.setValue(max(1, min(15, round(idle / 60))))
        self.lowbat.setValue(max(1, min(20, round(low / 5))))
        self.idle_label.setText(f"{self.idle.value()} minutes")
        self.lowbat_label.setText(f"{self.lowbat.value() * 5}% battery")

    def _save_dpi(self) -> None:
        stages = [row.value() for row in self.rows[:self.count.value()]]
        active = self.active.checkedId() + 1
        self.ctl.set_dpi_stages(self.ctl.current_slot, stages, active)

    def _set_dpi_max(self, maximum: int) -> None:
        for row in self.rows:
            row.set_maximum(maximum)

    def _save_rate(self, index: int) -> None:
        self.ctl.set_polling(self.ctl.current_slot, RATE_TO_INTERVAL[RATES[index]])
