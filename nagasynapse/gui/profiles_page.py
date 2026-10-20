"""PROFILES tab: the five onboard profile slots."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QInputDialog, QLabel, QMenu, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from ..actions import PROFILE_COLORS
from ..layout import PROFILE_COLOR_HEX, PROFILE_SLOTS
from .controller import Controller
from .widgets import dim, section


def ask_name(parent, title: str, default: str) -> str | None:
    name, ok = QInputDialog.getText(parent, title, "Profile name:", text=default)
    name = name.strip()
    return name if ok and name else None


class SlotCard(QFrame):
    def __init__(self, page: "ProfilesPage", slot: int):
        super().__init__()
        self.page = page
        self.slot = slot
        self.setObjectName("Card")
        self.setMinimumHeight(170)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        head = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {PROFILE_COLOR_HEX[slot]}; font-size: 14pt;")
        head.addWidget(dot)
        head.addWidget(section(f"Slot {slot} · {PROFILE_COLORS[slot]}"))
        head.addStretch(1)
        self.badge = QLabel()
        head.addWidget(self.badge)
        lay.addLayout(head)
        self.name = QLabel()
        self.name.setObjectName("PanelTitle")
        lay.addWidget(self.name)
        self.detail = dim("")
        lay.addWidget(self.detail)
        lay.addStretch(1)
        self.buttons = QHBoxLayout()
        lay.addLayout(self.buttons)
        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setObjectName("Primary")
        self.activate_btn = QPushButton("Activate")
        self.more_btn = QPushButton("More ▾")
        self.create_btn = QPushButton("Create profile")
        self.create_btn.setObjectName("Primary")
        self.import_btn = QPushButton("Import…")
        for b in (self.edit_btn, self.activate_btn, self.more_btn, self.create_btn,
                  self.import_btn):
            self.buttons.addWidget(b)
        self.buttons.addStretch(1)
        self.edit_btn.clicked.connect(lambda: page.editRequested.emit(slot))
        self.activate_btn.clicked.connect(lambda: page.ctl.activate_profile(slot))
        self.create_btn.clicked.connect(lambda: page.create(slot))
        self.import_btn.clicked.connect(lambda: page.import_into(slot))
        menu = QMenu(self)
        menu.addAction("Rename…", lambda: page.rename(slot))
        self.copy_menu = menu.addMenu("Duplicate to")
        menu.addAction("Export…", lambda: page.export(slot))
        menu.addAction("Import over this profile…", lambda: page.import_into(slot))
        menu.addSeparator()
        menu.addAction("Restore default buttons", lambda: page.reset(slot))
        menu.addAction("Delete profile", lambda: page.delete(slot))
        self.more_btn.setMenu(menu)

    def refresh(self) -> None:
        ctl = self.page.ctl
        enabled = self.slot in ctl.enabled
        active = enabled and ctl.active == self.slot
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)
        if enabled:
            self.name.setText(ctl.profile_title(self.slot))
            self.badge.setText("ACTIVE" if active else "")
            self.badge.setObjectName("Accent")
            self.badge.style().unpolish(self.badge)
            self.badge.style().polish(self.badge)
            editing = self.slot == ctl.current_slot
            self.detail.setText(("Currently in use on the mouse. " if active else
                                 "Stored on the mouse. ") +
                                ("Being edited." if editing else ""))
        else:
            self.name.setText("Empty slot")
            self.badge.setText("")
            self.detail.setText("Create a profile here, or import one from a file.")
        for w in (self.edit_btn, self.activate_btn, self.more_btn):
            w.setVisible(enabled)
        self.activate_btn.setEnabled(not active)
        for w in (self.create_btn, self.import_btn):
            w.setVisible(not enabled)
        self.copy_menu.clear()
        for other in PROFILE_SLOTS:
            if other != self.slot:
                label = f"Slot {other} ({PROFILE_COLORS[other]})"
                if other in ctl.enabled:
                    label += f" — replaces {ctl.profile_title(other)}"
                self.copy_menu.addAction(label, lambda o=other: self.page.duplicate(self.slot, o))


class ProfilesPage(QWidget):
    editRequested = Signal(int)

    def __init__(self, ctl: Controller):
        super().__init__()
        self.ctl = ctl
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 22, 28, 22)
        root.setSpacing(14)
        head = QHBoxLayout()
        col = QVBoxLayout()
        col.addWidget(section("Onboard profiles"))
        col.addWidget(dim("The mouse stores up to five profiles. They work on any computer, "
                          "no software needed. The bottom button cycles through them by "
                          "default; the LED color shows which one is active."))
        head.addLayout(col, 1)
        self.backup_btn = QPushButton("Back up everything…")
        head.addWidget(self.backup_btn, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(head)
        grid = QGridLayout()
        grid.setSpacing(14)
        self.cards = []
        for i, slot in enumerate(PROFILE_SLOTS):
            card = SlotCard(self, slot)
            grid.addWidget(card, i // 3, i % 3)
            self.cards.append(card)
        root.addLayout(grid)
        root.addStretch(1)
        self.backup_btn.clicked.connect(self.backup)
        ctl.profilesChanged.connect(self.refresh)
        ctl.currentSlotChanged.connect(lambda _s: self.refresh())
        self.refresh()

    def refresh(self) -> None:
        for card in self.cards:
            card.refresh()

    def create(self, slot: int) -> None:
        options = ["Factory defaults"] + [
            f"Copy of {self.ctl.profile_title(s)} (slot {s})" for s in self.ctl.enabled]
        choice, ok = QInputDialog.getItem(self, "Create profile", "Start from:", options, 0,
                                          False)
        if not ok:
            return
        name = ask_name(self, "Create profile", f"Profile {slot}")
        if not name:
            return
        idx = options.index(choice)
        copy_from = self.ctl.enabled[idx - 1] if idx > 0 else None
        self.ctl.create_profile(slot, name, copy_from)

    def rename(self, slot: int) -> None:
        name = ask_name(self, "Rename profile", self.ctl.profile_title(slot))
        if name:
            self.ctl.rename_profile(slot, name)

    def duplicate(self, src: int, dst: int) -> None:
        if dst in self.ctl.enabled and QMessageBox.question(
                self, "Duplicate profile",
                f"Replace {self.ctl.profile_title(dst)} in slot {dst} with a copy of "
                f"{self.ctl.profile_title(src)}?") != QMessageBox.StandardButton.Yes:
            return
        name = ask_name(self, "Duplicate profile", f"{self.ctl.profile_title(src)} copy")
        if not name:
            return
        if dst in self.ctl.enabled:
            def work(dev):
                data = dev.read_profile(src, progress=self.ctl.report_progress)
                data.name = name
                dev.write_profile(dst, data, progress=self.ctl.report_progress)

            def done(_):
                self.ctl.profiles.pop(dst, None)
                self.ctl.names[dst] = name
                self.ctl.refresh_profiles(lambda: self.ctl.set_current_slot(dst))

            self.ctl.run(work, done)
        else:
            self.ctl.create_profile(dst, name, copy_from=src)

    def reset(self, slot: int) -> None:
        if QMessageBox.question(self, "Restore defaults",
                                f"Restore every button of {self.ctl.profile_title(slot)} "
                                "to the factory defaults?") == QMessageBox.StandardButton.Yes:
            self.ctl.reset_profile(slot)

    def delete(self, slot: int) -> None:
        if len(self.ctl.enabled) <= 1:
            QMessageBox.information(self, "Delete profile",
                                    "The mouse needs at least one profile.")
            return
        if QMessageBox.question(self, "Delete profile",
                                f"Delete {self.ctl.profile_title(slot)} from the mouse?") \
                == QMessageBox.StandardButton.Yes:
            self.ctl.delete_profile(slot)

    def export(self, slot: int) -> None:
        safe = "".join(c if c.isalnum() or c in "-_ " else "_"
                       for c in self.ctl.profile_title(slot))
        path, _ = QFileDialog.getSaveFileName(
            self, "Export profile", str(Path.home() / f"{safe}.nagaprofile.json"),
            "Naga profile (*.json)")
        if path:
            self.ctl.export_profile(slot, path)

    def import_into(self, slot: int) -> None:
        if slot in self.ctl.enabled and QMessageBox.question(
                self, "Import profile",
                f"Replace {self.ctl.profile_title(slot)} with the imported profile?") \
                != QMessageBox.StandardButton.Yes:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import profile", str(Path.home()),
                                              "Naga profile (*.json)")
        if path:
            self.ctl.import_profile(slot, path)

    def backup(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Back up profiles and macros",
            str(Path.home() / "naga-v2-pro-backup.json"), "Backup (*.json)")
        if path:
            self.ctl.backup_all(path)
