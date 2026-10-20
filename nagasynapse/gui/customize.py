"""CUSTOMIZE tab: button assignments."""

from __future__ import annotations

from PySide6.QtCore import QSettings, Signal
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from ..actions import Action, Kind, MouseFn
from ..layout import BUTTONS_BY_ID, default_action
from .assign import AssignPanel
from .controller import Controller
from .mouse_canvas import MouseCanvas
from .widgets import Segmented, TesterStrip

PLATES = ["side2", "side6", "side12"]
PLATE_LABELS = ["2-BUTTON", "6-BUTTON", "12-BUTTON"]


class CustomizePage(QWidget):
    openMacros = Signal(object)  # macro id to edit, or None for a new macro

    def __init__(self, ctl: Controller, settings: QSettings):
        super().__init__()
        self.ctl = ctl
        self.settings = settings
        self.layer = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(10)

        bar = QHBoxLayout()
        self.layer_seg = Segmented(["STANDARD", "HYPERSHIFT"])
        self.layer_seg.buttons[1].setProperty("hypershift", True)
        bar.addWidget(self.layer_seg)
        bar.addSpacing(18)
        bar.addWidget(QLabel("Side plate:"))
        self.plate_seg = Segmented(PLATE_LABELS)
        bar.addWidget(self.plate_seg)
        bar.addSpacing(12)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        bar.addWidget(self.hint, 1)
        self.reset_btn = QPushButton("Restore defaults")
        self.reset_btn.setToolTip("Restore every button of this profile to its factory default")
        bar.addWidget(self.reset_btn)
        root.addLayout(bar)

        body = QHBoxLayout()
        body.setSpacing(14)
        left = QVBoxLayout()
        self.canvas = MouseCanvas()
        self.canvas.describe = self._describe
        left.addWidget(self.canvas, 1)
        self.tester = TesterStrip()
        left.addWidget(self.tester)
        body.addLayout(left, 1)
        self.panel = AssignPanel()
        body.addWidget(self.panel)
        root.addLayout(body, 1)

        # Until the mouse says which plate is attached, show none.
        self.plate_seg.clear()
        self.canvas.plate = None

        self.layer_seg.changed.connect(self._set_layer)
        self.plate_seg.changed.connect(self._set_plate)
        self.canvas.buttonSelected.connect(self._select)
        self.panel.applyRequested.connect(self._apply)
        self.panel.createMacroRequested.connect(lambda: self.openMacros.emit(None))
        self.panel.editMacroRequested.connect(self.openMacros.emit)
        self.reset_btn.clicked.connect(self._reset_all)
        ctl.profileLoaded.connect(self._profile_loaded)
        ctl.bindingChanged.connect(self._binding_changed)
        ctl.macrosChanged.connect(self._macros_changed)
        ctl.profilesChanged.connect(lambda: self.panel.set_profile_names(ctl.names))
        ctl.currentSlotChanged.connect(lambda _s: self.refresh())
        ctl.plateChanged.connect(self._plate_attached)
        ctl.connectionChanged.connect(self._connection_changed)
        self._update_hint()

    # ------------------------------------------------------------ helpers
    @property
    def data(self):
        return self.ctl.profiles.get(self.ctl.current_slot)

    def _describe(self, button: int) -> tuple[str, bool]:
        data = self.data
        if data is None:
            return ("Loading…", False)
        action = data.binding(button, self.layer)
        return (action.describe(self.ctl.macro_names()),
                not action.same_as(default_action(button)))

    def refresh(self) -> None:
        self.canvas.update()
        self._update_hint()
        if self.canvas.selected is not None and self.data is not None:
            self.panel.edit(self.canvas.selected, self.layer,
                            self.data.binding(self.canvas.selected, self.layer))

    def _update_hint(self) -> None:
        data = self.data
        if self.layer == 0:
            self.hint.setText("")
            return
        has_key = data is not None and any(
            a.kind == Kind.HYPERSHIFT for (b, l), a in data.bindings.items() if l == 0)
        if has_key:
            self.hint.setObjectName("Dim")
            self.hint.setText("These assignments apply while a Hypershift button is held.")
        else:
            self.hint.setObjectName("Warning")
            self.hint.setText("No button is set to Hypershift on the standard layer yet — "
                              "assign one to use these.")
        self.hint.style().unpolish(self.hint)
        self.hint.style().polish(self.hint)

    # ------------------------------------------------------------- events
    def _set_layer(self, layer: int) -> None:
        self.layer = layer
        self.canvas.hypershift = bool(layer)
        self.refresh()

    def _set_plate(self, index: int) -> None:
        self.canvas.plate = PLATES[index]
        self.settings.setValue("side_plate", PLATES[index])
        sel = self.canvas.selected
        if sel is not None and BUTTONS_BY_ID[sel].group.startswith("side") and \
                BUTTONS_BY_ID[sel].group != PLATES[index]:
            self.canvas.selected = None
        self.canvas.update()

    def _connection_changed(self, connected: bool, _msg: str) -> None:
        # The connected model decides the drawing and the available actions.
        self.panel.update_categories()
        self.canvas.update()

    def _plate_attached(self, plate: str | None) -> None:
        """The mouse reported its side plate: mark it and show it. With no
        plate attached, nothing is selected or drawn."""
        if not self.ctl.plate_supported:
            # The mouse can't tell: fall back to the plate picked last time.
            saved = self.settings.value("side_plate", "")
            if saved in PLATES and self.canvas.plate is None:
                self.plate_seg.set_index(PLATES.index(saved))
                self._set_plate(PLATES.index(saved))
            return
        for i, button in enumerate(self.plate_seg.buttons):
            attached = PLATES[i] == plate
            button.setText(PLATE_LABELS[i] + (" ●" if attached else ""))
            button.setToolTip("Attached to the mouse" if attached else "")
        if plate in PLATES:
            self.plate_seg.set_index(PLATES.index(plate))
            self._set_plate(PLATES.index(plate))
        else:
            self.plate_seg.clear()
            self.canvas.plate = None
            sel = self.canvas.selected
            if sel is not None and BUTTONS_BY_ID.get(sel) and \
                    BUTTONS_BY_ID[sel].group.startswith("side"):
                self.canvas.selected = None
            self.canvas.update()

    def _select(self, button: int) -> None:
        if self.data is None:
            return
        self.panel.edit(button, self.layer, self.data.binding(button, self.layer))

    def _profile_loaded(self, slot: int) -> None:
        if slot == self.ctl.current_slot:
            self.refresh()

    def _binding_changed(self, slot: int, button: int, layer: int) -> None:
        if slot == self.ctl.current_slot:
            self.refresh()

    def _macros_changed(self) -> None:
        self.panel.set_macros(self.ctl.macro_names())
        self.canvas.update()

    def _apply(self, button: int, layer: int, action: Action) -> None:
        data = self.data
        if data is None:
            return
        if button == 0x01 and layer == 0 and not (
                action.kind == Kind.MOUSE and action.data[:1] == bytes([MouseFn.LEFT])):
            others = [b for (b, l), a in data.bindings.items()
                      if l == 0 and b != 0x01 and a.kind == Kind.MOUSE
                      and a.data[:1] == bytes([MouseFn.LEFT])]
            if not others:
                answer = QMessageBox.warning(
                    self, "Remove left click?",
                    "No other button is assigned to Left Click. If you continue you "
                    "will need another pointing device (or this app's CLI) to undo it.\n\n"
                    "Continue?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:
                    return
        self.ctl.set_binding(self.ctl.current_slot, button, layer, action)

    def _reset_all(self) -> None:
        slot = self.ctl.current_slot
        answer = QMessageBox.question(
            self, "Restore defaults",
            f"Restore every button (standard and Hypershift) of "
            f"{self.ctl.profile_title(slot)} to the factory defaults?")
        if answer == QMessageBox.StandardButton.Yes:
            self.ctl.reset_profile(slot)

    def edit_button(self, button: int, layer: int = 0) -> None:
        self.layer_seg.set_index(layer)
        self._set_layer(layer)
        group = BUTTONS_BY_ID[button].group
        if group in PLATES:
            self.plate_seg.set_index(PLATES.index(group))
            self._set_plate(PLATES.index(group))
        self.canvas.selected = button
        self._select(button)
        self.canvas.update()
