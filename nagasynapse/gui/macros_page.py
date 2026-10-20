"""MACROS tab: record, edit and store onboard macros."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu,
                               QMessageBox, QProgressBar, QPushButton, QSpinBox,
                               QVBoxLayout, QWidget)

from ..hid_usage import CONSUMER_KEYS, KEY_NAMES, MODIFIER_BITS
from ..layout import button_label
from ..macros import MOUSE_BUTTON_NAMES, Macro, MacroEvent, delay, key, text_events
from .controller import Controller
from .widgets import KeyCaptureEdit, RecordPad, dim, section

TAP_DELAY = 20


class KeyDialog(QDialog):
    def __init__(self, parent, title: str, allow_modifiers: bool):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        lay.addWidget(dim("Click the box and press the key" +
                          (" or combination." if allow_modifiers else ".")))
        self.capture = KeyCaptureEdit()
        lay.addWidget(self.capture)
        lay.addWidget(dim("Or choose it from the list:"))
        self.combo = QComboBox()
        self.combo.setMaxVisibleItems(18)
        self.combo.addItem("—", 0)
        for usage, name in sorted(KEY_NAMES.items()):
            self.combo.addItem(name, usage)
        lay.addWidget(self.combo)
        self.allow_modifiers = allow_modifiers
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.combo.activated.connect(
            lambda _i: self.capture.set_combo(0, self.combo.currentData() or 0))
        self.capture.captured.connect(
            lambda _m, u: self.combo.setCurrentIndex(max(0, self.combo.findData(u))))
        self.capture.setFocus()

    def result_combo(self) -> tuple[int, int]:
        mods = self.capture.modifiers if self.allow_modifiers else 0
        return mods, self.capture.usage


class MacrosPage(QWidget):
    def __init__(self, ctl: Controller):
        super().__init__()
        self.ctl = ctl
        self.macro: Macro | None = None
        self.saved_json: dict | None = None
        self._last_ts: float | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(14)

        # ------------------------------------------------ left: macro list
        left = QFrame()
        left.setObjectName("Panel")
        left.setFixedWidth(310)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(14, 14, 14, 14)
        ll.addWidget(section("Macros on the mouse"))
        self.list = QListWidget()
        ll.addWidget(self.list, 1)
        row = QHBoxLayout()
        self.new_btn = QPushButton("New")
        self.new_btn.setObjectName("Primary")
        self.dup_btn = QPushButton("Duplicate")
        self.del_btn = QPushButton("Delete")
        self.del_btn.setObjectName("Danger")
        for b in (self.new_btn, self.dup_btn, self.del_btn):
            row.addWidget(b)
        ll.addLayout(row)
        row = QHBoxLayout()
        self.import_btn = QPushButton("Import…")
        self.export_btn = QPushButton("Export…")
        row.addWidget(self.import_btn)
        row.addWidget(self.export_btn)
        ll.addLayout(row)
        ll.addSpacing(8)
        ll.addWidget(section("Onboard memory"))
        self.mem_bar = QProgressBar()
        self.mem_bar.setTextVisible(False)
        self.mem_bar.setFixedHeight(8)
        ll.addWidget(self.mem_bar)
        mem_row = QHBoxLayout()
        self.mem_label = dim("", wrap=True)
        mem_row.addWidget(self.mem_label, 1)
        self.compact_btn = QPushButton("Compact")
        self.compact_btn.setToolTip("Reclaim space left behind by deleted or edited macros")
        mem_row.addWidget(self.compact_btn)
        ll.addLayout(mem_row)
        root.addWidget(left)

        # ------------------------------------------------ right: editor
        right = QFrame()
        right.setObjectName("Panel")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(18, 16, 18, 16)
        rl.setSpacing(10)
        head = QHBoxLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("Macro name")
        self.name.setMaxLength(48)
        self.name.setStyleSheet("font-size: 13pt; font-weight: 700;")
        head.addWidget(self.name, 1)
        self.id_label = dim("", wrap=False)
        head.addWidget(self.id_label)
        rl.addLayout(head)

        rec = QHBoxLayout()
        self.record_btn = QPushButton("●  Record")
        self.record_btn.setObjectName("Record")
        self.record_btn.setCheckable(True)
        self.record_btn.setMinimumWidth(120)
        rec.addWidget(self.record_btn)
        rec.addSpacing(10)
        rec.addWidget(QLabel("Delays:"))
        self.delay_mode = QComboBox()
        self.delay_mode.addItems(["Record actual delays", "Fixed delay", "No delays"])
        rec.addWidget(self.delay_mode)
        self.fixed_delay = QSpinBox()
        self.fixed_delay.setRange(1, 65535)
        self.fixed_delay.setValue(50)
        self.fixed_delay.setSuffix(" ms")
        rec.addWidget(self.fixed_delay)
        rec.addStretch(1)
        rl.addLayout(rec)
        self.pad = RecordPad()
        rl.addWidget(self.pad)

        tools = QHBoxLayout()
        self.insert_btn = QPushButton("Insert ▾")
        self.insert_btn.setMenu(self._insert_menu())
        self.edit_btn = QPushButton("Edit")
        self.up_btn = QPushButton("▲")
        self.down_btn = QPushButton("▼")
        self.remove_btn = QPushButton("Remove")
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setObjectName("Danger")
        for b in (self.insert_btn, self.edit_btn, self.up_btn, self.down_btn,
                  self.remove_btn):
            tools.addWidget(b)
        tools.addStretch(1)
        tools.addWidget(self.clear_btn)
        rl.addLayout(tools)

        self.steps = QListWidget()
        self.steps.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.steps.setAlternatingRowColors(True)
        rl.addWidget(self.steps, 1)

        self.summary = dim("")
        rl.addWidget(self.summary)
        self.warning = QLabel()
        self.warning.setObjectName("Warning")
        self.warning.setWordWrap(True)
        rl.addWidget(self.warning)
        self.usage_label = dim("")
        rl.addWidget(self.usage_label)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        self.revert_btn = QPushButton("Revert")
        self.save_btn = QPushButton("Save to mouse")
        self.save_btn.setObjectName("Primary")
        bottom.addWidget(self.revert_btn)
        bottom.addWidget(self.save_btn)
        rl.addLayout(bottom)
        root.addWidget(right, 1)
        self.editor = right

        # ------------------------------------------------ wiring
        self.list.currentItemChanged.connect(self._list_selected)
        self.new_btn.clicked.connect(self.new_macro)
        self.dup_btn.clicked.connect(self._duplicate)
        self.del_btn.clicked.connect(self._delete)
        self.import_btn.clicked.connect(self._import)
        self.export_btn.clicked.connect(self._export)
        self.compact_btn.clicked.connect(self._compact)
        self.record_btn.toggled.connect(self._toggle_record)
        self.pad.recorded.connect(self._recorded)
        self.delay_mode.currentIndexChanged.connect(
            lambda i: self.fixed_delay.setVisible(i == 1))
        self.fixed_delay.setVisible(False)
        self.edit_btn.clicked.connect(self._edit_step)
        self.steps.itemDoubleClicked.connect(lambda _i: self._edit_step())
        self.up_btn.clicked.connect(lambda: self._move(-1))
        self.down_btn.clicked.connect(lambda: self._move(1))
        self.remove_btn.clicked.connect(self._remove)
        self.clear_btn.clicked.connect(self._clear)
        self.save_btn.clicked.connect(self._save)
        self.revert_btn.clicked.connect(self._revert)
        self.name.textEdited.connect(lambda _t: self._changed(rebuild=False))
        ctl.macrosChanged.connect(self.refresh_list)
        ctl.flashChanged.connect(self._update_memory)
        ctl.profileLoaded.connect(lambda _s: self._update_summary())
        self.refresh_list()
        self._set_editor_enabled(False)

    # ---------------------------------------------------------------- list
    def refresh_list(self) -> None:
        current = self.macro.id if self.macro else None
        self.list.blockSignals(True)
        self.list.clear()
        for mid, m in sorted(self.ctl.macros.items(), key=lambda kv: kv[1].name.lower()):
            item = QListWidgetItem(m.name)
            item.setToolTip(f"{len(m.events)} steps · {m.duration_ms() / 1000:.2f} s")
            item.setData(Qt.ItemDataRole.UserRole, mid)
            self.list.addItem(item)
            if mid == current:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        if not self.ctl.macros and self.macro is None:
            self.list.addItem(QListWidgetItem("No macros yet — press New"))
            self.list.item(0).setFlags(Qt.ItemFlag.NoItemFlags)
        has_sel = self.macro is not None and self.macro.id is not None
        self.dup_btn.setEnabled(has_sel)
        self.del_btn.setEnabled(has_sel)
        self._update_memory()

    def _update_memory(self) -> None:
        f = self.ctl.flash
        if not f:
            self.mem_label.setText("")
            return
        self.mem_bar.setRange(0, f.total)
        self.mem_bar.setValue(f.used + f.recycled)
        text = f"{f.used / 1024:.1f} KiB used of {f.total / 1024:.0f} KiB"
        if f.recycled:
            text += f" · {f.recycled / 1024:.1f} KiB reclaimable"
        self.mem_label.setText(text)
        self.compact_btn.setEnabled(f.recycled > 0)

    def _dirty(self) -> bool:
        if self.macro is None:
            return False
        if self.saved_json is None:
            return bool(self.macro.events)
        return self.macro.to_json() != self.saved_json

    def _confirm_discard(self) -> bool:
        if not self._dirty():
            return True
        answer = QMessageBox.question(
            self, "Unsaved macro", "Discard the changes to this macro?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        return answer == QMessageBox.StandardButton.Discard

    def _list_selected(self, item, previous) -> None:
        if item is None or item.data(Qt.ItemDataRole.UserRole) is None:
            return
        mid = item.data(Qt.ItemDataRole.UserRole)
        if self.macro is not None and mid == self.macro.id:
            return
        if not self._confirm_discard():
            self.list.blockSignals(True)
            self.list.setCurrentItem(previous)
            self.list.blockSignals(False)
            return
        self.open_macro(mid)

    def open_macro(self, macro_id: int) -> None:
        macro = self.ctl.macros.get(macro_id)
        if macro is None:
            return
        self._load(copy.deepcopy(macro))
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == macro_id:
                self.list.blockSignals(True)
                self.list.setCurrentRow(i)
                self.list.blockSignals(False)

    def new_macro(self) -> None:
        if not self._confirm_discard():
            return
        n = len(self.ctl.macros) + 1
        names = {m.name for m in self.ctl.macros.values()}
        while f"Macro {n}" in names:
            n += 1
        self._load(Macro(name=f"Macro {n}"), saved=False)
        self.list.clearSelection()
        self.name.setFocus()
        self.name.selectAll()

    def _load(self, macro: Macro, saved: bool = True) -> None:
        self.record_btn.setChecked(False)
        self.macro = macro
        self.saved_json = macro.to_json() if saved else None
        self.name.setText(macro.name)
        self.id_label.setText(f"ID {macro.id}" if macro.id is not None else "not saved yet")
        self._set_editor_enabled(True)
        self._rebuild_steps()
        self.refresh_list()

    def _set_editor_enabled(self, on: bool) -> None:
        for w in self.editor.findChildren(QWidget):
            w.setEnabled(on)
        if not on:
            self.summary.setText("Select a macro on the left or press New.")
            self.summary.setEnabled(True)

    # --------------------------------------------------------------- steps
    def _rebuild_steps(self, select: list[int] | None = None) -> None:
        self.steps.clear()
        if self.macro is None:
            return
        for i, ev in enumerate(self.macro.events):
            item = QListWidgetItem(f"{i + 1:>3}.   {ev.describe()}")
            if ev.type == "delay":
                item.setForeground(Qt.GlobalColor.gray)
            self.steps.addItem(item)
        for row in select or []:
            if 0 <= row < self.steps.count():
                self.steps.item(row).setSelected(True)
                self.steps.setCurrentRow(row)
        if select is None and self.steps.count():
            self.steps.scrollToBottom()
        self._update_summary()

    def _update_summary(self) -> None:
        if self.macro is None:
            return
        m = self.macro
        try:
            size = len(m.encode())
        except (ValueError, KeyError):
            size = 0
        self.summary.setText(f"{len(m.events)} steps · {m.duration_ms() / 1000:.2f} s · "
                             f"{size} bytes")
        stuck = m.stuck_keys()
        self.warning.setText("Still held down when the macro ends: " + ", ".join(stuck)
                             if stuck else "")
        self.warning.setVisible(bool(stuck))
        if m.id is not None:
            uses = self.ctl.macro_usage(m.id)
            if uses:
                parts = [f"{self.ctl.profile_title(s)} › {button_label(b)}"
                         f"{' (Hypershift)' if l else ''}" for s, b, l in uses]
                self.usage_label.setText("Assigned to: " + "; ".join(parts))
            else:
                self.usage_label.setText("Not assigned to any button yet — assign it on "
                                         "the CUSTOMIZE tab.")
        else:
            self.usage_label.setText("")

    def _changed(self, rebuild: bool = True, select: list[int] | None = None) -> None:
        if self.macro is None:
            return
        self.macro.name = self.name.text().strip() or "Macro"
        if rebuild:
            self._rebuild_steps(select)
        else:
            self._update_summary()

    def _insert_at(self) -> int:
        rows = sorted(i.row() for i in self.steps.selectedIndexes())
        return rows[-1] + 1 if rows else len(self.macro.events)

    def _insert(self, events: list[MacroEvent]) -> None:
        if self.macro is None:
            return
        pos = self._insert_at()
        self.macro.events[pos:pos] = events
        self._changed(select=list(range(pos, pos + len(events))))

    def _insert_menu(self) -> QMenu:
        menu = QMenu(self)

        def add(text, fn, parent=menu):
            act = QAction(text, parent)
            act.triggered.connect(fn)
            parent.addAction(act)

        add("Key press…", lambda: self._insert_key("tap"))
        add("Key down…", lambda: self._insert_key("down"))
        add("Key up…", lambda: self._insert_key("up"))
        add("Type text…", self._insert_text)
        menu.addSeparator()
        for title, mode in (("Mouse click", "tap"), ("Mouse button down", "down"),
                            ("Mouse button up", "up")):
            sub = menu.addMenu(title)
            for code, name in MOUSE_BUTTON_NAMES.items():
                add(name, lambda _=False, c=code, m=mode: self._insert_mouse(c, m), sub)
        add("Scroll up", lambda: self._insert([MacroEvent("wheel", 1)]))
        add("Scroll down", lambda: self._insert([MacroEvent("wheel", -1)]))
        menu.addSeparator()
        add("Delay…", self._insert_delay)
        sub = menu.addMenu("Multimedia key")
        for usage, name in CONSUMER_KEYS:
            add(name, lambda _=False, u=usage: self._insert(
                [MacroEvent("media", u, True), delay(TAP_DELAY), MacroEvent("media", u, False)]),
                sub)
        return menu

    def _insert_key(self, mode: str) -> None:
        dlg = KeyDialog(self, {"tap": "Key press", "down": "Key down", "up": "Key up"}[mode],
                        allow_modifiers=mode == "tap")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        mods, usage = dlg.result_combo()
        if not usage:
            return
        if mode == "down":
            self._insert([key(usage, True)])
        elif mode == "up":
            self._insert([key(usage, False)])
        else:
            mod_keys = [u for u, bit in MODIFIER_BITS.items() if mods & bit]
            events = [key(u, True) for u in mod_keys]
            events += [key(usage, True), delay(TAP_DELAY), key(usage, False)]
            events += [key(u, False) for u in reversed(mod_keys)]
            self._insert(events)

    def _insert_text(self) -> None:
        text, ok = QInputDialog.getMultiLineText(
            self, "Type text", "Text to type (US keyboard layout):")
        if ok and text:
            try:
                self._insert(text_events(text, key_delay=10))
            except ValueError as exc:
                QMessageBox.warning(self, "Type text", str(exc))

    def _insert_mouse(self, code: str, mode: str) -> None:
        if mode == "tap":
            self._insert([MacroEvent("mouse", code, True), delay(TAP_DELAY),
                          MacroEvent("mouse", code, False)])
        else:
            self._insert([MacroEvent("mouse", code, mode == "down")])

    def _insert_delay(self) -> None:
        ms, ok = QInputDialog.getInt(self, "Delay", "Delay (milliseconds):", 50, 1, 600000)
        if ok:
            self._insert([delay(ms)])

    def _edit_step(self) -> None:
        if self.macro is None:
            return
        row = self.steps.currentRow()
        if row < 0:
            return
        ev = self.macro.events[row]
        if ev.type == "delay":
            ms, ok = QInputDialog.getInt(self, "Delay", "Delay (milliseconds):",
                                         int(ev.code), 0, 600000)
            if ok:
                ev.code = ms
        elif ev.type == "key":
            dlg = KeyDialog(self, "Change key", allow_modifiers=False)
            dlg.capture.set_combo(0, int(ev.code))
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_combo()[1]:
                ev.code = dlg.result_combo()[1]
        elif ev.type == "mouse":
            names = list(MOUSE_BUTTON_NAMES.values())
            codes = list(MOUSE_BUTTON_NAMES)
            choice, ok = QInputDialog.getItem(self, "Mouse button", "Button:", names,
                                              codes.index(ev.code), False)
            if ok:
                ev.code = codes[names.index(choice)]
        elif ev.type == "wheel":
            ticks, ok = QInputDialog.getInt(self, "Scroll", "Ticks (+ up, − down):",
                                            int(ev.code), -127, 127)
            if ok and ticks:
                ev.code = ticks
        elif ev.type == "media":
            names = [n for _u, n in CONSUMER_KEYS]
            usages = [u for u, _n in CONSUMER_KEYS]
            current = usages.index(ev.code) if ev.code in usages else 0
            choice, ok = QInputDialog.getItem(self, "Multimedia key", "Key:", names,
                                              current, False)
            if ok:
                ev.code = usages[names.index(choice)]
        self._changed(select=[row])

    def _move(self, direction: int) -> None:
        if self.macro is None:
            return
        rows = sorted({i.row() for i in self.steps.selectedIndexes()})
        if not rows:
            return
        events = self.macro.events
        if direction < 0 and rows[0] == 0 or direction > 0 and rows[-1] == len(events) - 1:
            return
        order = rows if direction < 0 else list(reversed(rows))
        for r in order:
            events[r], events[r + direction] = events[r + direction], events[r]
        self._changed(select=[r + direction for r in rows])

    def _remove(self) -> None:
        if self.macro is None:
            return
        rows = sorted({i.row() for i in self.steps.selectedIndexes()}, reverse=True)
        for r in rows:
            del self.macro.events[r]
        self._changed(select=[min(rows[-1], len(self.macro.events) - 1)] if rows else None)

    def _clear(self) -> None:
        if self.macro and self.macro.events and QMessageBox.question(
                self, "Clear macro", "Remove every step from this macro?") == \
                QMessageBox.StandardButton.Yes:
            self.macro.events.clear()
            self._changed()

    # ------------------------------------------------------------ recording
    def _toggle_record(self, on: bool) -> None:
        if on and self.macro is None:
            self.new_macro()
        self.pad.set_recording(on)
        self.record_btn.setText("■  Stop" if on else "●  Record")
        self._last_ts = None

    def _recorded(self, type_: str, code, down: bool, ts: float) -> None:
        if self.macro is None:
            return
        events = []
        if self._last_ts is not None:
            mode = self.delay_mode.currentIndex()
            if mode == 0:
                ms = round((ts - self._last_ts) * 1000)
                if ms > 0:
                    events.append(delay(ms))
            elif mode == 1:
                events.append(delay(self.fixed_delay.value()))
        self._last_ts = ts
        if type_ == "wheel":
            events.append(MacroEvent("wheel", int(code)))
        else:
            events.append(MacroEvent(type_, code, down))
        self.macro.events.extend(events)
        self._changed()

    # ---------------------------------------------------------------- save
    def _save(self) -> None:
        if self.macro is None:
            return
        self.record_btn.setChecked(False)
        self.macro.name = self.name.text().strip() or "Macro"
        if not self.macro.events:
            QMessageBox.warning(self, "Save macro", "The macro has no steps yet.")
            return
        macro = copy.deepcopy(self.macro)

        def saved(mid: int):
            self.macro.id = mid
            self._load(copy.deepcopy(self.ctl.macros[mid]))

        self.ctl.save_macro(macro, then=saved)

    def _revert(self) -> None:
        if self.macro is None:
            return
        if self.macro.id is not None and self.macro.id in self.ctl.macros:
            self._load(copy.deepcopy(self.ctl.macros[self.macro.id]))
        else:
            self.macro.events.clear()
            self._changed()

    def _duplicate(self) -> None:
        if self.macro is None or not self._confirm_discard():
            return
        dup = copy.deepcopy(self.macro)
        dup.id = None
        dup.name = f"{self.macro.name} copy"
        self._load(dup, saved=False)
        self.list.clearSelection()

    def _delete(self) -> None:
        if self.macro is None or self.macro.id is None:
            return
        uses = self.ctl.macro_usage(self.macro.id)
        msg = f"Delete “{self.macro.name}” from the mouse?"
        msg += ("\n\nButtons assigned to it will be restored to their defaults."
                if uses or len(self.ctl.profiles) < len(self.ctl.enabled) else "")
        if QMessageBox.question(self, "Delete macro", msg) != QMessageBox.StandardButton.Yes:
            return
        mid = self.macro.id
        self.macro = None
        self.saved_json = None
        self.steps.clear()
        self.name.clear()
        self.id_label.setText("")
        self._set_editor_enabled(False)
        self.ctl.delete_macro(mid)

    def _import(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Import macro", str(Path.home()),
                                              "Macro (*.json)")
        if not path:
            return
        try:
            obj = json.loads(Path(path).read_text())
            macro = Macro.from_json(obj)
            macro.encode()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            QMessageBox.warning(self, "Import macro", f"Could not read {path}:\n{exc}")
            return
        macro.id = None
        self._load(macro, saved=False)
        self.list.clearSelection()

    def _export(self) -> None:
        if self.macro is None:
            return
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in self.macro.name)
        path, _ = QFileDialog.getSaveFileName(self, "Export macro",
                                              str(Path.home() / f"{safe}.json"),
                                              "Macro (*.json)")
        if path:
            obj = {"format": "nagasynapse-macro", "version": 1, **self.macro.to_json()}
            Path(path).write_text(json.dumps(obj, indent=2))

    def _compact(self) -> None:
        if QMessageBox.question(
                self, "Compact memory",
                "Reclaim space left by deleted or edited macros?\n\nAll macros are backed "
                "up, the macro memory is formatted and everything is written back. "
                "Do not unplug the mouse while this runs.") == QMessageBox.StandardButton.Yes:
            self.ctl.compact_flash()

    def has_unsaved_changes(self) -> bool:
        return self._dirty()
