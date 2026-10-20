"""Interactive drawing of the mouse with button callouts.

The supported models share this outline; they differ in the two small
buttons behind the wheel (layout.MODEL.centre_buttons)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QLinearGradient,
                           QPainter, QPainterPath, QPen, QRadialGradient, QTransform)
from PySide6.QtWidgets import QSizePolicy, QWidget

from .. import layout
from ..layout import BUTTONS_BY_ID, SIDE_PLATES
from . import theme

W, H = 1120.0, 600.0
CX = 772.0  # centre line of the top view
SPLIT_Y = 268.0  # where the left/right click buttons end


def _body_path() -> QPainterPath:
    """Top view outline: front at the top, thumb groove on the left."""
    p = QPainterPath()
    p.moveTo(CX, 64)
    p.cubicTo(CX + 62, 62, CX + 112, 76, CX + 124, 136)
    p.cubicTo(CX + 132, 182, CX + 126, 232, CX + 126, 274)
    p.cubicTo(CX + 125, 330, CX + 144, 398, CX + 136, 462)
    p.cubicTo(CX + 128, 524, CX + 78, 554, CX, 554)
    p.cubicTo(CX - 84, 554, CX - 136, 526, CX - 143, 462)
    p.cubicTo(CX - 149, 400, CX - 132, 330, CX - 121, 284)
    p.cubicTo(CX - 112, 238, CX - 129, 184, CX - 122, 136)
    p.cubicTo(CX - 112, 76, CX - 62, 62, CX, 64)
    p.closeSubpath()
    return p


def _thumb_edge() -> QPainterPath:
    """The left flank where the side plate sits, just outside the body."""
    p = QPainterPath()
    p.moveTo(CX - 150, 456)
    p.cubicTo(CX - 156, 400, CX - 139, 330, CX - 128, 286)
    return p


BODY = _body_path()
THUMB_EDGE = _thumb_edge()
CHANNEL = QRectF(CX - 20, 90, 40, 180)
WHEEL = QRectF(CX - 16, 104, 32, 84)
# The two small buttons behind the wheel: front and rear.
FRONT_BTN = QRectF(CX - 12, 200, 24, 17)
REAR_BTN = QRectF(CX - 12, 228, 24, 17)
LOGO = QPointF(CX + 4, 400)
BOTTOM_BTN = QPointF(CX + 4, 492)


def _clip(rect: QRectF) -> QPainterPath:
    r = QPainterPath()
    r.addRect(rect)
    return BODY.intersected(r)


LEFT_BTN = _clip(QRectF(0, 0, CX - 20, SPLIT_Y))
RIGHT_BTN = _clip(QRectF(CX + 20, 0, 400, SPLIT_Y))


@dataclass
class Callout:
    button: int
    card: QRectF
    anchor: QPointF


CARD_W, CARD_H = 176.0, 66.0
LEFT_X, RIGHT_X = CX - 172 - CARD_W, CX + 166


def _callouts() -> list[Callout]:
    rows = [58, 130, 202, 274, 346]
    front, rear = layout.MODEL.centre_buttons
    return [
        Callout(0x01, QRectF(LEFT_X, rows[0], CARD_W, CARD_H), QPointF(CX - 64, 176)),
        Callout(0x09, QRectF(LEFT_X, rows[1], CARD_W, CARD_H), QPointF(CX, 108)),
        Callout(0x34, QRectF(LEFT_X, rows[2], CARD_W, CARD_H), QPointF(CX - 16, 148)),
        Callout(0x0A, QRectF(LEFT_X, rows[3], CARD_W, CARD_H), QPointF(CX, 184)),
        Callout(0x0E, QRectF(LEFT_X, 458, CARD_W, CARD_H), BOTTOM_BTN),
        Callout(0x02, QRectF(RIGHT_X, rows[0], CARD_W, CARD_H), QPointF(CX + 64, 176)),
        Callout(0x03, QRectF(RIGHT_X, rows[1], CARD_W, CARD_H), QPointF(CX + 6, 138)),
        Callout(0x35, QRectF(RIGHT_X, rows[2], CARD_W, CARD_H), QPointF(CX + 16, 148)),
        Callout(front, QRectF(RIGHT_X, rows[3], CARD_W, CARD_H), FRONT_BTN.center()),
        Callout(rear, QRectF(RIGHT_X, rows[4], CARD_W, CARD_H), REAR_BTN.center()),
    ]

# Side plate area, to the left of the mouse (seen from the left side, so the
# front of the mouse is on the left).
PLATE_X = 8.0
PLATE_PAD = 22.0


def plate_tiles(plate: str) -> list[tuple[int, QRectF]]:
    tiles = []
    ox = PLATE_X + PLATE_PAD
    if plate == "side12":
        tw, th, gap = 112.0, 84.0, 10.0
        oy = 124.0
        for i in range(12):
            r, c = divmod(i, 3)
            tiles.append((0x40 + i, QRectF(ox + c * (tw + gap), oy + r * (th + gap), tw, th)))
    elif plate == "side6":
        tw, th, gap = 112.0, 116.0, 10.0
        oy = 186.0
        for i in range(6):
            r, c = divmod(i, 3)
            tiles.append((0x50 + i, QRectF(ox + c * (tw + gap), oy + r * (th + gap), tw, th)))
    else:
        tw, th, gap = 173.0, 140.0, 10.0
        oy = 216.0
        tiles.append((0x05, QRectF(ox, oy, tw, th)))
        tiles.append((0x04, QRectF(ox + tw + gap, oy, tw, th)))
    return tiles


def plate_rect(plate: str) -> QRectF:
    tiles = [r for _, r in plate_tiles(plate)]
    rect = tiles[0]
    for r in tiles[1:]:
        rect = rect.united(r)
    return rect.adjusted(-PLATE_PAD, -46, PLATE_PAD, PLATE_PAD)


class MouseCanvas(QWidget):
    buttonSelected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(760, 400)
        self.plate = "side12"
        self.hypershift = False
        self.selected: int | None = None
        self.hover: int | None = None
        self.describe: Callable[[int], tuple[str, bool]] = lambda b: ("", False)

    def sizeHint(self) -> QSize:
        return QSize(int(W), int(H))

    # ----------------------------------------------------------- geometry
    def _transform(self) -> QTransform:
        scale = min(self.width() / W, self.height() / H)
        dx = (self.width() - W * scale) / 2
        dy = (self.height() - H * scale) / 2
        t = QTransform()
        t.translate(dx, dy)
        t.scale(scale, scale)
        return t

    def _hit(self, pos) -> int | None:
        inv, ok = self._transform().inverted()
        if not ok:
            return None
        p = inv.map(QPointF(pos))
        for button, rect in plate_tiles(self.plate):
            if rect.contains(p):
                return button
        for c in _callouts():
            if c.card.contains(p):
                return c.button
        if WHEEL.contains(p):
            return 0x03
        front, rear = layout.MODEL.centre_buttons
        if FRONT_BTN.adjusted(-3, -3, 3, 3).contains(p):
            return front
        if REAR_BTN.adjusted(-3, -3, 3, 3).contains(p):
            return rear
        if (p - BOTTOM_BTN).manhattanLength() < 24:
            return 0x0E
        if LEFT_BTN.contains(p):
            return 0x01
        if RIGHT_BTN.contains(p):
            return 0x02
        return None

    def mouseMoveEvent(self, ev):
        hit = self._hit(ev.position())
        if hit != self.hover:
            self.hover = hit
            self.setCursor(Qt.CursorShape.PointingHandCursor if hit is not None
                           else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, ev):
        self.hover = None
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            hit = self._hit(ev.position())
            if hit is not None:
                self.selected = hit
                self.buttonSelected.emit(hit)
                self.update()

    # ----------------------------------------------------------- painting
    @property
    def accent(self) -> QColor:
        return QColor(theme.HYPERSHIFT if self.hypershift else theme.ACCENT)

    def _state_color(self, button: int) -> QColor | None:
        if button == self.selected:
            return self.accent
        if button == self.hover:
            return QColor("#7a7a7a")
        return None

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setTransform(self._transform())
        self._paint_top(p)
        self._paint_plate(p)
        p.end()

    def _paint_top(self, p: QPainter) -> None:
        p.setFont(self._font(8.5, QFont.Weight.Bold))
        p.setPen(QColor(theme.TEXT_DIM))
        p.drawText(QRectF(CX - 120, 18, 240, 24), Qt.AlignmentFlag.AlignCenter, "TOP VIEW")

        # soft glow under the mouse
        glow = QRadialGradient(QPointF(CX, 320), 300)
        glow.setColorAt(0, QColor(68, 214, 44, 26) if not self.hypershift else QColor(245, 166, 35, 26))
        glow.setColorAt(1, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(CX, 320), 300, 300)

        body_grad = QLinearGradient(QPointF(CX - 150, 0), QPointF(CX + 150, 0))
        body_grad.setColorAt(0, QColor("#121212"))
        body_grad.setColorAt(0.55, QColor("#242424"))
        body_grad.setColorAt(1, QColor("#111111"))
        p.setBrush(QBrush(body_grad))
        p.setPen(QPen(QColor("#3a3a3a"), 1.5))
        p.drawPath(BODY)
        # palm hump highlight
        hump = QRadialGradient(QPointF(CX + 10, 380), 150)
        hump.setColorAt(0, QColor(255, 255, 255, 16))
        hump.setColorAt(1, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(hump))
        p.drawPath(BODY)

        for path, button in ((LEFT_BTN, 0x01), (RIGHT_BTN, 0x02)):
            color = self._state_color(button)
            fill = QColor("#1c1c1c")
            if color is not None:
                fill = QColor(color)
                fill.setAlpha(55 if button == self.selected else 30)
            p.setBrush(fill)
            p.setPen(QPen(color if color is not None else QColor("#333"), 1.4))
            p.drawPath(path)

        # centre channel
        p.setBrush(QColor("#0b0b0b"))
        p.setPen(QPen(QColor("#2a2a2a"), 1))
        p.drawRoundedRect(CHANNEL, 12, 12)

        # wheel
        wheel_sel = self._state_color(0x03) or (
            self._state_color(0x09) or self._state_color(0x0A) or
            self._state_color(0x34) or self._state_color(0x35))
        grad = QLinearGradient(WHEEL.topLeft(), WHEEL.topRight())
        grad.setColorAt(0, QColor("#202020"))
        grad.setColorAt(0.5, QColor("#3c3c3c"))
        grad.setColorAt(1, QColor("#202020"))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(wheel_sel or QColor("#4a4a4a"), 1.6))
        p.drawRoundedRect(WHEEL, 10, 10)
        p.setPen(QPen(QColor("#151515"), 1.2))
        y = WHEEL.top() + 8
        while y < WHEEL.bottom() - 6:
            p.drawLine(QPointF(WHEEL.left() + 5, y), QPointF(WHEEL.right() - 5, y))
            y += 6
        # wheel light strip
        strip = QColor(self.accent)
        strip.setAlpha(140)
        p.setPen(QPen(strip, 2))
        p.drawLine(QPointF(CX, WHEEL.top() + 4), QPointF(CX, WHEEL.bottom() - 4))

        front, rear = layout.MODEL.centre_buttons
        for rect, button in ((FRONT_BTN, front), (REAR_BTN, rear)):
            color = self._state_color(button)
            p.setBrush(QColor("#262626") if color is None else color.darker(160))
            p.setPen(QPen(color or QColor("#4a4a4a"), 1.4))
            p.drawRoundedRect(rect, 5, 5)

        # end of the click buttons
        p.save()
        p.setClipPath(BODY)
        p.setPen(QPen(QColor("#2c2c2c"), 1.2))
        p.drawLine(QPointF(CX - 200, SPLIT_Y), QPointF(CX - 20, SPLIT_Y))
        p.drawLine(QPointF(CX + 20, SPLIT_Y), QPointF(CX + 200, SPLIT_Y))
        p.restore()

        # logo
        logo = QColor(self.accent)
        logo.setAlpha(170)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(logo)
        p.drawEllipse(LOGO, 14, 14)
        p.setBrush(QColor("#1d1d1d"))
        p.drawEllipse(LOGO, 9, 9)

        # bottom (underside) button, dashed
        color = self._state_color(0x0E)
        pen = QPen(color or QColor("#5a5a5a"), 1.5, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(BOTTOM_BTN, 15, 15)
        p.setFont(self._font(7))
        p.setPen(QColor("#6a6a6a"))
        p.drawText(QRectF(BOTTOM_BTN.x() - 50, BOTTOM_BTN.y() + 18, 100, 16),
                   Qt.AlignmentFlag.AlignCenter, "underside")

        # side plate location on the left flank
        selected = BUTTONS_BY_ID.get(self.selected) if self.selected is not None else None
        hint = self.accent if selected and selected.group.startswith("side") else QColor("#3a3a3a")
        p.setPen(QPen(hint, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(THUMB_EDGE)

        for c in _callouts():
            self._paint_callout(p, c)

    def _paint_callout(self, p: QPainter, c: Callout) -> None:
        text, changed = self.describe(c.button)
        state = self._state_color(c.button)
        card = c.card
        left_side = card.left() < CX
        edge = QPointF(card.right() if left_side else card.left(), card.center().y())
        line_color = QColor(state) if state is not None else QColor("#333333")
        p.setPen(QPen(line_color, 1.2))
        elbow = QPointF(edge.x() + (14 if left_side else -14), edge.y())
        p.drawLine(edge, elbow)
        p.drawLine(elbow, c.anchor)
        p.setBrush(line_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(c.anchor, 3, 3)
        self._paint_card(p, card, BUTTONS_BY_ID[c.button].name, text, changed, state,
                         align_right=False)

    def _paint_card(self, p: QPainter, rect: QRectF, title: str, text: str,
                    changed: bool, state: QColor | None, align_right: bool = False,
                    big_title: bool = False) -> None:
        fill = QColor("#191919")
        if state is not None:
            fill = QColor(state)
            fill.setAlpha(40 if state == self.accent else 18)
        border = state if state is not None else QColor("#2e2e2e")
        p.setBrush(fill)
        p.setPen(QPen(border, 1.4 if state is not None else 1))
        p.drawRoundedRect(rect, 7, 7)
        inner = rect.adjusted(12, 7, -10, -6)
        if big_title:
            p.setFont(self._font(20, QFont.Weight.Bold))
            p.setPen(self.accent if changed else QColor("#9a9a9a"))
            p.drawText(QRectF(inner.left(), inner.top() - 2, inner.width(), 34),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, title)
            text_rect = QRectF(inner.left(), inner.top() + 34, inner.width(),
                               inner.height() - 34)
        else:
            p.setFont(self._font(8, QFont.Weight.Bold))
            p.setPen(QColor(theme.TEXT_DIM))
            p.drawText(QRectF(inner.left(), inner.top(), inner.width(), 14),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       title.upper())
            text_rect = QRectF(inner.left(), inner.top() + 15, inner.width(),
                               inner.height() - 15)
        if changed:
            p.setBrush(self.accent)
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(rect.right() - 10, rect.top() + 10), 3.2, 3.2)
        font = self._font(10, QFont.Weight.DemiBold)
        p.setFont(font)
        p.setPen(QColor(theme.TEXT))
        fm = QFontMetricsF(font)
        lines = self._wrap(text, fm, text_rect.width(),
                           max(1, int(text_rect.height() // fm.lineSpacing())))
        y = text_rect.top()
        for line in lines:
            p.drawText(QRectF(text_rect.left(), y, text_rect.width(), fm.lineSpacing()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, line)
            y += fm.lineSpacing()

    @staticmethod
    def _wrap(text: str, fm: QFontMetricsF, width: float, max_lines: int) -> list[str]:
        words = text.split(" ")
        lines: list[str] = []
        current = ""
        for w in words:
            trial = f"{current} {w}".strip()
            if fm.horizontalAdvance(trial) <= width or not current:
                current = trial
            else:
                lines.append(current)
                current = w
        if current:
            lines.append(current)
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = fm.elidedText(lines[-1] + " …", Qt.TextElideMode.ElideRight, width)
        return [fm.elidedText(l, Qt.TextElideMode.ElideRight, width) for l in lines]

    def _paint_plate(self, p: QPainter) -> None:
        rect = plate_rect(self.plate)
        p.setFont(self._font(8.5, QFont.Weight.Bold))
        p.setPen(QColor(theme.TEXT_DIM))
        p.drawText(QRectF(rect.left(), 18, rect.width(), 24), Qt.AlignmentFlag.AlignCenter,
                   f"SIDE PLATE · {SIDE_PLATES[self.plate].upper()}")
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0, QColor("#171717"))
        grad.setColorAt(1, QColor("#0f0f0f"))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor("#2f2f2f"), 1.2))
        p.drawRoundedRect(rect, 22, 22)
        p.setFont(self._font(7.5, QFont.Weight.Bold))
        p.setPen(QColor("#5a5a5a"))
        p.drawText(QRectF(rect.left() + PLATE_PAD, rect.top() + 12, 160, 20),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "◀ FRONT")
        p.drawText(QRectF(rect.right() - PLATE_PAD - 160, rect.top() + 12, 160, 20),
                   Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "BACK ▶")
        for button, tile in plate_tiles(self.plate):
            b = BUTTONS_BY_ID[button]
            text, changed = self.describe(button)
            label = b.short if self.plate != "side2" else b.name.replace("Side Button ", "")
            self._paint_card(p, tile, label, text, changed, self._state_color(button),
                             big_title=True)

    @staticmethod
    def _font(size: float, weight=QFont.Weight.Normal) -> QFont:
        f = QFont()
        f.setPointSizeF(size)
        f.setWeight(weight)
        return f
