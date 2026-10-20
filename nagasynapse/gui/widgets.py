"""Reusable widgets."""

from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QPointF, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QKeyEvent, QPainter, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from ..hid_usage import EVDEV_TO_HID, MODIFIER_BITS, combo_text, is_modifier
from . import theme

# Fallback when the platform gives us no scan code.
_QT_TO_HID = {
    **{getattr(Qt.Key, f"Key_{c}"): 0x04 + i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")},
    **{getattr(Qt.Key, f"Key_{d}"): 0x1E + (int(d) - 1) % 10 for d in "1234567890"},
    **{getattr(Qt.Key, f"Key_F{n}"): (0x3A + n - 1 if n <= 12 else 0x68 + n - 13)
       for n in range(1, 25)},
    Qt.Key.Key_Return: 0x28, Qt.Key.Key_Enter: 0x58, Qt.Key.Key_Escape: 0x29,
    Qt.Key.Key_Backspace: 0x2A, Qt.Key.Key_Tab: 0x2B, Qt.Key.Key_Backtab: 0x2B,
    Qt.Key.Key_Space: 0x2C, Qt.Key.Key_Minus: 0x2D, Qt.Key.Key_Equal: 0x2E,
    Qt.Key.Key_BracketLeft: 0x2F, Qt.Key.Key_BracketRight: 0x30,
    Qt.Key.Key_Backslash: 0x31, Qt.Key.Key_Semicolon: 0x33,
    Qt.Key.Key_Apostrophe: 0x34, Qt.Key.Key_QuoteLeft: 0x35, Qt.Key.Key_Comma: 0x36,
    Qt.Key.Key_Period: 0x37, Qt.Key.Key_Slash: 0x38, Qt.Key.Key_CapsLock: 0x39,
    Qt.Key.Key_Print: 0x46, Qt.Key.Key_ScrollLock: 0x47, Qt.Key.Key_Pause: 0x48,
    Qt.Key.Key_Insert: 0x49, Qt.Key.Key_Home: 0x4A, Qt.Key.Key_PageUp: 0x4B,
    Qt.Key.Key_Delete: 0x4C, Qt.Key.Key_End: 0x4D, Qt.Key.Key_PageDown: 0x4E,
    Qt.Key.Key_Right: 0x4F, Qt.Key.Key_Left: 0x50, Qt.Key.Key_Down: 0x51,
    Qt.Key.Key_Up: 0x52, Qt.Key.Key_NumLock: 0x53, Qt.Key.Key_Menu: 0x65,
    Qt.Key.Key_Control: 0xE0, Qt.Key.Key_Shift: 0xE1, Qt.Key.Key_Alt: 0xE2,
    Qt.Key.Key_Meta: 0xE3, Qt.Key.Key_Super_L: 0xE3, Qt.Key.Key_Super_R: 0xE7,
    Qt.Key.Key_AltGr: 0xE6,
}


def hid_from_key_event(event: QKeyEvent) -> int | None:
    scan = event.nativeScanCode()
    if scan > 8:
        usage = EVDEV_TO_HID.get(scan - 8)
        if usage:
            return usage
    return _QT_TO_HID.get(Qt.Key(event.key()))


def dot_icon(color: str, size: int = 12) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(size / 2, size / 2), size / 2 - 1, size / 2 - 1)
    p.end()
    return QIcon(pix)


def section(text: str) -> QLabel:
    label = QLabel(text.upper())
    label.setObjectName("SectionTitle")
    return label


def dim(text: str, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Dim")
    label.setWordWrap(wrap)
    return label


def hline() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {theme.BORDER};")
    return line


class Segmented(QWidget):
    """A row of mutually exclusive toggle buttons."""

    changed = Signal(int)

    def __init__(self, labels: list[str], parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: list[QPushButton] = []
        for i, text in enumerate(labels):
            b = QPushButton(text)
            b.setObjectName("Segment")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            radius = "6px"
            if i == 0:
                b.setStyleSheet(f"border-top-left-radius:{radius};border-bottom-left-radius:{radius};")
            if i == len(labels) - 1:
                b.setStyleSheet(b.styleSheet() +
                                f"border-top-right-radius:{radius};border-bottom-right-radius:{radius};")
            self.group.addButton(b, i)
            lay.addWidget(b)
            self.buttons.append(b)
        self.buttons[0].setChecked(True)
        self.group.idClicked.connect(self.changed)

    def index(self) -> int:
        return self.group.checkedId()

    def set_index(self, i: int) -> None:
        self.buttons[i].setChecked(True)


class KeyCaptureEdit(QLineEdit):
    """Click, then press a key or key combination."""

    captured = Signal(int, int)  # modifier mask, usage

    PROMPT = "Click here and press a key…"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("KeyCapture")
        self.setReadOnly(True)
        self.setPlaceholderText(self.PROMPT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._held: list[int] = []
        self._combo_used = False
        self.modifiers = 0
        self.usage = 0

    def set_combo(self, modifiers: int, usage: int) -> None:
        self.modifiers, self.usage = modifiers, usage
        self.setText(combo_text(modifiers, usage) if usage or modifiers else "")

    def event(self, ev):
        # Tab / Backtab normally move focus; capture them instead.
        if ev.type() == QEvent.Type.KeyPress and ev.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.keyPressEvent(ev)
            return True
        if ev.type() == QEvent.Type.ShortcutOverride:
            ev.accept()
            return True
        return super().event(ev)

    def focusInEvent(self, ev):
        super().focusInEvent(ev)
        self._held.clear()
        self.setPlaceholderText("Press a key or combination…")

    def focusOutEvent(self, ev):
        super().focusOutEvent(ev)
        self.setPlaceholderText(self.PROMPT)

    def _mask(self, exclude: int | None = None) -> int:
        mask = 0
        for u in self._held:
            if u != exclude:
                mask |= MODIFIER_BITS.get(u, 0)
        return mask

    def keyPressEvent(self, ev: QKeyEvent):
        if ev.isAutoRepeat():
            return
        usage = hid_from_key_event(ev)
        if usage is None:
            return
        if is_modifier(usage):
            if usage not in self._held:
                self._held.append(usage)
            self._combo_used = False
            self.setText(combo_text(self._mask(), 0) + " + …")
            return
        self._combo_used = True
        self.set_combo(self._mask(), usage)
        self.captured.emit(self.modifiers, self.usage)

    def keyReleaseEvent(self, ev: QKeyEvent):
        if ev.isAutoRepeat():
            return
        usage = hid_from_key_event(ev)
        if usage is None or not is_modifier(usage):
            return
        if not self._combo_used and usage in self._held:
            # A lone modifier (e.g. bind a button to Shift).
            self.set_combo(self._mask(exclude=usage), usage)
            self.captured.emit(self.modifiers, self.usage)
            self._combo_used = True
        if usage in self._held:
            self._held.remove(usage)


class RecordPad(QFrame):
    """Captures keyboard, mouse buttons and wheel while recording."""

    recorded = Signal(str, object, bool, float)  # type, code, down, timestamp

    MOUSE = {Qt.MouseButton.LeftButton: "left", Qt.MouseButton.RightButton: "right",
             Qt.MouseButton.MiddleButton: "middle", Qt.MouseButton.BackButton: "back",
             Qt.MouseButton.ForwardButton: "forward"}

    def __init__(self, parent=None):
        self.recording = False
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(70)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setWordWrap(True)
        lay.addWidget(self.label)
        self.recording = False
        self.set_recording(False)

    def set_recording(self, on: bool) -> None:
        self.recording = on
        if on:
            self.label.setText("● RECORDING — type keys, click or scroll inside this box. "
                               "Press Stop when done.")
            self.setStyleSheet(f"QFrame#Card {{ border: 1px solid {theme.DANGER}; }}")
            self.setFocus()
            self.grabKeyboard()
        else:
            self.releaseKeyboard()
            self.label.setText("Press Record, then type keys, click or scroll inside this box.")
            self.setStyleSheet("")
        self.label.setObjectName("" if on else "Dim")
        self.label.style().unpolish(self.label)
        self.label.style().polish(self.label)

    def event(self, ev):
        if self.recording and ev.type() == QEvent.Type.ShortcutOverride:
            ev.accept()
            return True
        if self.recording and ev.type() == QEvent.Type.KeyPress and \
                ev.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.keyPressEvent(ev)
            return True
        return super().event(ev)

    def keyPressEvent(self, ev: QKeyEvent):
        if not self.recording or ev.isAutoRepeat():
            return
        usage = hid_from_key_event(ev)
        if usage:
            self.recorded.emit("key", usage, True, time.monotonic())

    def keyReleaseEvent(self, ev: QKeyEvent):
        if not self.recording or ev.isAutoRepeat():
            return
        usage = hid_from_key_event(ev)
        if usage:
            self.recorded.emit("key", usage, False, time.monotonic())

    def mousePressEvent(self, ev):
        if self.recording and ev.button() in self.MOUSE:
            self.recorded.emit("mouse", self.MOUSE[ev.button()], True, time.monotonic())

    def mouseReleaseEvent(self, ev):
        if self.recording and ev.button() in self.MOUSE:
            self.recorded.emit("mouse", self.MOUSE[ev.button()], False, time.monotonic())

    def wheelEvent(self, ev):
        if not self.recording:
            return
        steps = ev.angleDelta().y() // 120
        if steps:
            self.recorded.emit("wheel", int(steps), True, time.monotonic())


class TesterStrip(QFrame):
    """Shows what the mouse sends: click it, then press buttons on the mouse."""

    BUTTONS = {Qt.MouseButton.LeftButton: "Left Click", Qt.MouseButton.RightButton: "Right Click",
               Qt.MouseButton.MiddleButton: "Middle Click",
               Qt.MouseButton.BackButton: "Mouse 4 (Back)",
               Qt.MouseButton.ForwardButton: "Mouse 5 (Forward)"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(44)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 4, 12, 4)
        title = QLabel("TEST")
        title.setObjectName("SectionTitle")
        lay.addWidget(title)
        self.events = QLabel()
        self.events.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.events, 1)
        self.log: list[str] = []
        self._show()

    def _show(self):
        if self.log:
            chips = " ".join(
                f"<span style='background:#1f3a19; color:{theme.TEXT};'>&nbsp;{t}&nbsp;</span>"
                for t in self.log[-8:])
            self.events.setText(chips)
        elif self.hasFocus():
            self.events.setText(f"<span style='color:{theme.ACCENT}'>Listening — press "
                                "buttons on the mouse…</span>")
        else:
            self.events.setText(f"<span style='color:{theme.TEXT_DIM}'>Click here, then press "
                                "buttons on the mouse to see what they send.</span>")

    def _add(self, text: str):
        self.log.append(text.replace("<", "&lt;"))
        self.log = self.log[-8:]
        self._show()

    def focusInEvent(self, ev):
        super().focusInEvent(ev)
        self._show()

    def focusOutEvent(self, ev):
        super().focusOutEvent(ev)
        self.log.clear()
        self._show()

    def event(self, ev):
        if self.hasFocus() and ev.type() == QEvent.Type.ShortcutOverride:
            ev.accept()
            return True
        if ev.type() == QEvent.Type.KeyPress and ev.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self.keyPressEvent(ev)
            return True
        return super().event(ev)

    def keyPressEvent(self, ev: QKeyEvent):
        if ev.isAutoRepeat():
            return
        usage = hid_from_key_event(ev)
        if usage is None or is_modifier(usage):
            return
        mods = 0
        m = ev.modifiers()
        for flag, bit in ((Qt.KeyboardModifier.ControlModifier, 0x01),
                          (Qt.KeyboardModifier.ShiftModifier, 0x02),
                          (Qt.KeyboardModifier.AltModifier, 0x04),
                          (Qt.KeyboardModifier.MetaModifier, 0x08)):
            if m & flag:
                mods |= bit
        self._add(combo_text(mods, usage))

    def mousePressEvent(self, ev):
        if not self.hasFocus():
            self.setFocus()
            return
        self._add(self.BUTTONS.get(ev.button(), f"Mouse {ev.button()}"))

    def wheelEvent(self, ev):
        d = ev.angleDelta()
        if d.y():
            self._add("Scroll Up" if d.y() > 0 else "Scroll Down")
        elif d.x():
            self._add("Scroll Left" if d.x() > 0 else "Scroll Right")
