"""Side panel used to choose what a button does."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QPushButton, QRadioButton, QScrollArea,
                               QSlider, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from ..actions import (Action, DpiOp, Kind, MOUSE_FN_NAMES, PROFILE_COLORS, ProfileOp,
                       SystemFn)
from ..hid_usage import CONSUMER_KEYS, KEY_NAMES, MODIFIER_NAMES
from .. import layout
from ..layout import DPI_MAX, DPI_MIN, button_label, default_action
from .widgets import KeyCaptureEdit, dim, hline, section

CATEGORIES = [
    ("default", "Default"),
    ("keyboard", "Keyboard Function"),
    ("mouse", "Mouse Function"),
    ("macro", "Macro"),
    ("dpi", "Sensitivity (DPI)"),
    ("profile", "Switch Profile"),
    ("media", "Multimedia"),
    ("hypershift", "Hypershift"),
    ("scroll", "Scroll Mode Toggle"),
    ("system", "System Function"),
    ("disabled", "Disable"),
]


def _radio_group(parent_layout, options, parent) -> QButtonGroup:
    group = QButtonGroup(parent)
    for value, text in options:
        rb = QRadioButton(text)
        group.addButton(rb, int(value))
        parent_layout.addWidget(rb)
    group.buttons()[0].setChecked(True)
    return group


class _Page(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(10)

    def load(self, action: Action) -> None:
        pass

    def action(self) -> Action | None:
        raise NotImplementedError

    def finish(self):
        self.lay.addStretch(1)


class TurboRow(QWidget):
    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.check = QCheckBox("Turbo (repeat while held)")
        lay.addWidget(self.check)
        row = QHBoxLayout()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 50)
        self.slider.setValue(10)
        self.label = QLabel()
        self.label.setMinimumWidth(80)
        row.addWidget(self.slider, 1)
        row.addWidget(self.label)
        lay.addLayout(row)
        self.slider.valueChanged.connect(self._update)
        self.check.toggled.connect(self._update)
        self._update()

    def _update(self):
        on = self.check.isChecked()
        self.slider.setEnabled(on)
        self.label.setText(f"{self.slider.value()} /sec")
        self.label.setEnabled(on)

    def interval(self) -> int | None:
        return round(1000 / self.slider.value()) if self.check.isChecked() else None

    def set_interval(self, ms: int | None):
        self.check.setChecked(bool(ms))
        if ms:
            self.slider.setValue(max(1, min(50, round(1000 / ms))))
        self._update()


class KeyboardPage(_Page):
    def __init__(self):
        super().__init__()
        self.lay.addWidget(section("Key"))
        self.capture = KeyCaptureEdit()
        self.lay.addWidget(self.capture)
        self.lay.addWidget(dim("Or pick from the list (for keys your desktop intercepts):"))
        self.combo = QComboBox()
        self.combo.setMaxVisibleItems(18)
        self.combo.addItem("—", 0)
        for usage, name in sorted(KEY_NAMES.items()):
            self.combo.addItem(name, usage)
        self.lay.addWidget(self.combo)
        self.lay.addWidget(section("Modifiers"))
        grid = QGridLayout()
        self.mods: dict[int, QCheckBox] = {}
        for i, (bit, name) in enumerate(MODIFIER_NAMES):
            cb = QCheckBox(name)
            self.mods[bit] = cb
            grid.addWidget(cb, i // 4, i % 4)
            cb.toggled.connect(self._sync_text)
        self.lay.addLayout(grid)
        self.turbo = TurboRow()
        self.lay.addWidget(self.turbo)
        self.finish()
        self.capture.captured.connect(self._captured)
        self.combo.activated.connect(self._picked)

    def _captured(self, mods: int, usage: int):
        for bit, cb in self.mods.items():
            cb.blockSignals(True)
            cb.setChecked(bool(mods & bit))
            cb.blockSignals(False)
        self.combo.setCurrentIndex(max(0, self.combo.findData(usage)))
        self.changed.emit()

    def _picked(self, _i):
        self.capture.set_combo(self._mask(), self.combo.currentData() or 0)
        self.changed.emit()

    def _mask(self) -> int:
        return sum(bit for bit, cb in self.mods.items() if cb.isChecked())

    def _sync_text(self):
        self.capture.set_combo(self._mask(), self.capture.usage)
        self.changed.emit()

    def load(self, action: Action):
        if action.kind in (Kind.KEYBOARD, Kind.KEYBOARD_TURBO):
            mods, usage = action.data[0], action.data[1]
            self.capture.set_combo(mods, usage)
            self._captured(mods, usage)
            self.turbo.set_interval(action.turbo_ms)
        else:
            self.capture.set_combo(0, 0)
            self._captured(0, 0)
            self.turbo.set_interval(None)

    def action(self) -> Action | None:
        usage = self.capture.usage
        if not usage:
            return None
        return Action.keyboard(usage, self._mask(), turbo_ms=self.turbo.interval())


class MousePage(_Page):
    def __init__(self):
        super().__init__()
        self.lay.addWidget(section("Mouse button"))
        self.combo = QComboBox()
        for fn, name in MOUSE_FN_NAMES.items():
            self.combo.addItem(name, int(fn))
        self.lay.addWidget(self.combo)
        self.lay.addWidget(section("Behaviour"))
        self.mode = _radio_group(self.lay, [(0, "Normal"), (1, "Double click"),
                                            (2, "Turbo (repeat while held)")], self)
        row = QHBoxLayout()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 50)
        self.slider.setValue(10)
        self.rate = QLabel()
        self.rate.setMinimumWidth(80)
        row.addWidget(self.slider, 1)
        row.addWidget(self.rate)
        self.lay.addLayout(row)
        self.finish()
        self.slider.valueChanged.connect(self._update)
        self.mode.idToggled.connect(lambda *_: self._update())
        self._update()

    def _update(self):
        turbo = self.mode.checkedId() == 2
        self.slider.setEnabled(turbo)
        self.rate.setEnabled(turbo)
        self.rate.setText(f"{self.slider.value()} /sec")

    def load(self, action: Action):
        if action.kind in (Kind.MOUSE, Kind.DOUBLE_CLICK, Kind.MOUSE_TURBO):
            idx = self.combo.findData(action.data[0])
            self.combo.setCurrentIndex(max(0, idx))
            mode = {Kind.MOUSE: 0, Kind.DOUBLE_CLICK: 1, Kind.MOUSE_TURBO: 2}[Kind(action.kind)]
            self.mode.button(mode).setChecked(True)
            if action.turbo_ms:
                self.slider.setValue(max(1, min(50, round(1000 / action.turbo_ms))))
        else:
            self.combo.setCurrentIndex(0)
            self.mode.button(0).setChecked(True)
        self._update()

    def action(self) -> Action:
        fn = self.combo.currentData()
        mode = self.mode.checkedId()
        if mode == 2:
            return Action.mouse(fn, turbo_ms=round(1000 / self.slider.value()))
        return Action.mouse(fn, double_click=mode == 1)


class MacroPage(_Page):
    createRequested = Signal()
    editRequested = Signal(int)

    def __init__(self):
        super().__init__()
        self.lay.addWidget(section("Macro"))
        self.combo = QComboBox()
        self.lay.addWidget(self.combo)
        self.empty = dim("There are no macros on the mouse yet.")
        self.lay.addWidget(self.empty)
        row = QHBoxLayout()
        self.new_btn = QPushButton("New macro…")
        self.edit_btn = QPushButton("Edit macro…")
        row.addWidget(self.new_btn)
        row.addWidget(self.edit_btn)
        row.addStretch(1)
        self.lay.addLayout(row)
        self.lay.addWidget(section("Playback"))
        self.mode = QButtonGroup(self)
        options = [(int(Kind.MACRO_TIMES), "Play"), (int(Kind.MACRO_HOLD), "Repeat while held"),
                   (int(Kind.MACRO_TOGGLE), "Toggle: press to start, press again to stop"),
                   (int(Kind.MACRO_SEQUENCE), "Sequence: each press plays the next keystroke")]
        for value, text in options:
            rb = QRadioButton(text)
            self.mode.addButton(rb, value)
            if value == Kind.MACRO_TIMES:
                times_row = QHBoxLayout()
                times_row.addWidget(rb)
                self.times = QSpinBox()
                self.times.setRange(1, 255)
                self.times.setSuffix(" time(s)")
                times_row.addWidget(self.times)
                times_row.addStretch(1)
                self.lay.addLayout(times_row)
            else:
                self.lay.addWidget(rb)
        self.mode.button(int(Kind.MACRO_TIMES)).setChecked(True)
        self.finish()
        self.new_btn.clicked.connect(self.createRequested)
        self.edit_btn.clicked.connect(
            lambda: self.combo.currentData() is not None and
            self.editRequested.emit(self.combo.currentData()))

    def set_macros(self, names: dict[int, str]):
        current = self.combo.currentData()
        self.combo.clear()
        for mid, name in sorted(names.items(), key=lambda kv: kv[1].lower()):
            self.combo.addItem(name, mid)
        has = bool(names)
        self.combo.setVisible(has)
        self.empty.setVisible(not has)
        self.edit_btn.setEnabled(has)
        if current is not None and self.combo.findData(current) >= 0:
            self.combo.setCurrentIndex(self.combo.findData(current))

    def select_macro(self, macro_id: int):
        idx = self.combo.findData(macro_id)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)

    def load(self, action: Action):
        if action.macro_id is not None:
            self.select_macro(action.macro_id)
            self.mode.button(int(action.kind)).setChecked(True)
            self.times.setValue(action.macro_times)

    def action(self) -> Action | None:
        mid = self.combo.currentData()
        if mid is None:
            return None
        return Action.macro(mid, self.mode.checkedId(), self.times.value())


class DpiPage(_Page):
    def __init__(self):
        super().__init__()
        self.lay.addWidget(section("Sensitivity function"))
        self.group = QButtonGroup(self)
        self.stage = QSpinBox()
        self.stage.setRange(1, 5)
        self.stage.setPrefix("Stage ")
        self.clutch = QSpinBox()
        self.clutch.setRange(DPI_MIN, DPI_MAX)
        self.clutch.setSingleStep(50)
        self.clutch.setValue(400)
        self.clutch.setSuffix(" DPI")
        for op, text, extra in [
            (DpiOp.CYCLE_UP, "Cycle up through stages", None),
            (DpiOp.CYCLE_DOWN, "Cycle down through stages", None),
            (DpiOp.NEXT, "Stage up", None),
            (DpiOp.PREV, "Stage down", None),
            (DpiOp.STAGE, "Set stage", self.stage),
            (DpiOp.CLUTCH, "Sensitivity clutch (while held)", self.clutch),
        ]:
            rb = QRadioButton(text)
            self.group.addButton(rb, int(op))
            if extra is None:
                self.lay.addWidget(rb)
            else:
                row = QHBoxLayout()
                row.addWidget(rb)
                row.addWidget(extra)
                row.addStretch(1)
                self.lay.addLayout(row)
        self.group.button(int(DpiOp.CYCLE_UP)).setChecked(True)
        self.finish()

    def load(self, action: Action):
        self.clutch.setMaximum(layout.dpi_max())
        if action.kind == Kind.DPI and action.data:
            op = action.data[0]
            if self.group.button(op):
                self.group.button(op).setChecked(True)
            if op == DpiOp.STAGE:
                self.stage.setValue(action.data[1])
            if op == DpiOp.CLUTCH:
                self.clutch.setValue(int.from_bytes(action.data[1:3], "big"))

    def action(self) -> Action:
        op = self.group.checkedId()
        return Action.dpi(op, stage=self.stage.value(), dpi_x=self.clutch.value())


class ProfilePage(_Page):
    def __init__(self):
        super().__init__()
        self.lay.addWidget(section("Profile function"))
        self.group = QButtonGroup(self)
        self.target = QComboBox()
        for slot, color in PROFILE_COLORS.items():
            self.target.addItem(f"Profile {slot} ({color})", slot)
        for op, text, extra in [
            (ProfileOp.CYCLE_UP, "Cycle up through profiles", None),
            (ProfileOp.CYCLE_DOWN, "Cycle down through profiles", None),
            (ProfileOp.NEXT, "Next profile", None),
            (ProfileOp.PREV, "Previous profile", None),
            (ProfileOp.SET, "Switch to", self.target),
        ]:
            rb = QRadioButton(text)
            self.group.addButton(rb, int(op))
            if extra is None:
                self.lay.addWidget(rb)
            else:
                row = QHBoxLayout()
                row.addWidget(rb)
                row.addWidget(extra, 1)
                self.lay.addLayout(row)
        self.group.button(int(ProfileOp.CYCLE_UP)).setChecked(True)
        self.finish()

    def set_names(self, names: dict[int, str]):
        for i in range(self.target.count()):
            slot = self.target.itemData(i)
            title = names.get(slot) or f"Profile {slot}"
            self.target.setItemText(i, f"{slot} · {title} ({PROFILE_COLORS[slot]})")

    def load(self, action: Action):
        if action.kind == Kind.PROFILE and action.data:
            op = action.data[0]
            if self.group.button(op):
                self.group.button(op).setChecked(True)
            if op == ProfileOp.SET:
                self.target.setCurrentIndex(max(0, self.target.findData(action.data[1])))

    def action(self) -> Action:
        return Action.profile(self.group.checkedId(), self.target.currentData())


class MediaPage(_Page):
    def __init__(self):
        super().__init__()
        self.lay.addWidget(section("Multimedia key"))
        self.list = QListWidget()
        self.list.setMinimumHeight(200)
        for usage, name in CONSUMER_KEYS:
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, usage)
            self.list.addItem(item)
        self.lay.addWidget(self.list)
        row = QHBoxLayout()
        row.addWidget(dim("Custom usage (hex):", wrap=False))
        self.custom = QLineEdit()
        self.custom.setPlaceholderText("e.g. 0x0CD")
        row.addWidget(self.custom)
        self.lay.addLayout(row)
        self.list.setCurrentRow(0)
        self.finish()
        self.list.currentRowChanged.connect(lambda *_: self.custom.clear())

    def load(self, action: Action):
        if action.kind == Kind.CONSUMER:
            usage = int.from_bytes(action.data[:2], "big")
            for i in range(self.list.count()):
                if self.list.item(i).data(Qt.ItemDataRole.UserRole) == usage:
                    self.list.setCurrentRow(i)
                    return
            self.custom.setText(f"0x{usage:03X}")

    def action(self) -> Action | None:
        text = self.custom.text().strip()
        if text:
            try:
                return Action.consumer(int(text, 16))
            except ValueError:
                return None
        item = self.list.currentItem()
        return Action.consumer(item.data(Qt.ItemDataRole.UserRole)) if item else None


class SystemPage(_Page):
    def __init__(self):
        super().__init__()
        self.lay.addWidget(section("System function"))
        self.group = _radio_group(self.lay, [(SystemFn.SLEEP, "Sleep"),
                                             (SystemFn.POWER_DOWN, "Power down"),
                                             (SystemFn.WAKE, "Wake up")], self)
        self.finish()

    def load(self, action: Action):
        if action.kind == Kind.SYSTEM and self.group.button(action.data[0]):
            self.group.button(action.data[0]).setChecked(True)

    def action(self) -> Action:
        return Action.system(self.group.checkedId())


class InfoPage(_Page):
    def __init__(self, text: str, factory):
        super().__init__()
        self.text = dim(text)
        self.lay.addWidget(self.text)
        self.factory = factory
        self.finish()

    def action(self) -> Action:
        return self.factory()


class AssignPanel(QFrame):
    """Edits the binding of one button on one layer."""

    applyRequested = Signal(int, int, object)   # button, layer, Action
    createMacroRequested = Signal()
    editMacroRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Panel")
        self.setFixedWidth(400)
        self.button: int | None = None
        self.layer = 0
        self.current: Action | None = None
        self.macro_names: dict[int, str] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 16, 16, 16)
        outer.setSpacing(10)
        self.title = QLabel("Select a button")
        self.title.setObjectName("PanelTitle")
        self.title.setWordWrap(True)
        outer.addWidget(self.title)
        self.layer_label = QLabel()
        outer.addWidget(self.layer_label)
        self.current_label = dim("Click any button on the mouse to change what it does.")
        outer.addWidget(self.current_label)

        self.body = QWidget()
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 6, 0, 0)
        body.setSpacing(12)
        chips = QGridLayout()
        chips.setSpacing(6)
        self.cats = QButtonGroup(self)
        self.cats.setExclusive(True)
        for i, (key, text) in enumerate(CATEGORIES):
            chip = QPushButton(text)
            chip.setObjectName("Chip")
            chip.setCheckable(True)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            self.cats.addButton(chip, i)
            chips.addWidget(chip, i // 2, i % 2)
        self._chip_grid = chips
        body.addLayout(chips)
        body.addWidget(hline())

        self.stack = QStackedWidget()
        self.pages: dict[str, _Page] = {}
        self.default_page = InfoPage("", lambda: default_action(self.button or 1))
        self.macro_page = MacroPage()
        self.profile_page = ProfilePage()
        pages = {
            "default": self.default_page,
            "keyboard": KeyboardPage(),
            "mouse": MousePage(),
            "macro": self.macro_page,
            "dpi": DpiPage(),
            "profile": self.profile_page,
            "media": MediaPage(),
            "hypershift": InfoPage(
                "Hold this button to temporarily switch every other button to its "
                "Hypershift assignment (edit those with the HYPERSHIFT toggle above "
                "the mouse).", Action.hypershift),
            "scroll": InfoPage("Switches the HyperScroll wheel between tactile and "
                               "free-spin scrolling.", Action.scroll_mode),
            "system": SystemPage(),
            "disabled": InfoPage("The button does nothing when pressed.", Action.disabled),
        }
        for key, page in pages.items():
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            self.stack.addWidget(scroll)
            self.pages[key] = page
        body.addWidget(self.stack, 1)
        outer.addWidget(self.body, 1)

        self.warning = QLabel()
        self.warning.setObjectName("Warning")
        self.warning.setWordWrap(True)
        self.warning.hide()
        outer.addWidget(self.warning)

        buttons = QHBoxLayout()
        self.revert_btn = QPushButton("Revert")
        self.save_btn = QPushButton("Save")
        self.save_btn.setObjectName("Primary")
        buttons.addWidget(self.revert_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.save_btn)
        outer.addLayout(buttons)

        self.cats.idClicked.connect(self.stack.setCurrentIndex)
        self.save_btn.clicked.connect(self._save)
        self.revert_btn.clicked.connect(lambda: self.current and self._load_action(self.current))
        self.macro_page.createRequested.connect(self.createMacroRequested)
        self.macro_page.editRequested.connect(self.editMacroRequested)
        self.body.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.revert_btn.setEnabled(False)

    def clear_selection(self) -> None:
        """Back to the empty "Select a button" state."""
        self.button, self.current = None, None
        self.title.setText("Select a button")
        self.layer_label.setText("")
        self.current_label.setText("Click any button on the mouse to change what it does.")
        self.body.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.revert_btn.setEnabled(False)

    def set_macros(self, names: dict[int, str]):
        self.macro_names = names
        self.macro_page.set_macros(names)

    def set_profile_names(self, names: dict[int, str]):
        self.profile_page.set_names(names)

    def update_categories(self) -> None:
        """Hide actions the connected mouse can't use: the scroll-mode toggle
        needs a HyperScroll wheel (the Naga V2 Pro's scroll-mode button)."""
        has_scroll_mode = 0x6D in layout.BUTTONS_BY_ID
        shown = 0
        for i, (key, _text) in enumerate(CATEGORIES):
            chip = self.cats.button(i)
            visible = key != "scroll" or has_scroll_mode
            chip.setVisible(visible)
            self._chip_grid.removeWidget(chip)
            if visible:
                self._chip_grid.addWidget(chip, shown // 2, shown % 2)
                shown += 1

    def edit(self, button: int, layer: int, action: Action):
        self.update_categories()
        self.button, self.layer, self.current = button, layer, action
        self.title.setText(button_label(button))
        self.layer_label.setText("HYPERSHIFT LAYER" if layer else "STANDARD LAYER")
        self.layer_label.setObjectName("Warning" if layer else "Accent")
        self.layer_label.style().unpolish(self.layer_label)
        self.layer_label.style().polish(self.layer_label)
        self.body.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.revert_btn.setEnabled(True)
        self.default_page.text.setText(
            f"Factory default: <b>{default_action(button).describe()}</b>")
        self._load_action(action)

    def _load_action(self, action: Action):
        self.current_label.setText(f"Currently: <b>{action.describe(self.macro_names)}</b>")
        category = action.category()
        if action.same_as(default_action(self.button)) and category not in ("keyboard", "mouse"):
            category = "default"
        keys = [k for k, _ in CATEGORIES]
        if category not in keys:
            category = "disabled"
        for page in self.pages.values():
            page.load(action)
        self.cats.button(keys.index(category)).setChecked(True)
        self.stack.setCurrentIndex(keys.index(category))
        self.warning.hide()

    def _save(self):
        key = CATEGORIES[self.cats.checkedId()][0]
        action = self.pages[key].action()
        if action is None:
            self.warning.setText("Finish choosing the assignment first.")
            self.warning.show()
            return
        self.warning.hide()
        self.applyRequested.emit(self.button, self.layer, action)
