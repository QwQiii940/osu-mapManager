"""Reusable controls, list delegates and layout helpers."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QLabel, QLayout, QSizePolicy, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from .theme import hex_rgb


def qcolor(color: str) -> QColor:
    return QColor(*hex_rgb(color))


class FlowLayout(QLayout):
    """Wrap filter controls onto additional rows when the window narrows."""

    def __init__(self, parent=None, margin=0, hspacing=8, vspacing=8):
        super().__init__(parent)
        self._items = []
        self._hspacing = hspacing
        self._vspacing = vspacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        x = rect.x() + m.left()
        y = rect.y() + m.top()
        right = rect.right() - m.right()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > right and line_height:
                x = rect.x() + m.left()
                y += line_height + self._vspacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._hspacing
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + m.bottom()


class SurfaceCard(QFrame):
    """Standard padded surface used by all pages."""

    def __init__(self, parent=None, margins=(20, 18, 20, 18), spacing=12):
        super().__init__(parent)
        self.setObjectName("surface")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.content = QVBoxLayout(self)
        self.content.setContentsMargins(*margins)
        self.content.setSpacing(spacing)


class PageHeading(QWidget):
    """Consistent eyebrow, title and optional subtitle for a page."""

    def __init__(self, title: str, subtitle: str = "", eyebrow: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)
        if eyebrow:
            eyebrow_label = QLabel(eyebrow)
            eyebrow_label.setObjectName("eyebrow")
            layout.addWidget(eyebrow_label)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("pageTitle")
        layout.addWidget(self.title_label)
        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setObjectName("pageSubtitle")
            layout.addWidget(self.subtitle_label)


class SquareCheckBox(QCheckBox):
    """Large high-contrast checkbox with a hand-drawn checked state."""

    def __init__(self, colors: dict[str, str], parent=None):
        super().__init__(parent)
        self._colors = colors
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumSize(44, 44)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setTristate(False)
        self.setAccessibleName("选择歌曲")
        self.setToolTip("点击方框即可选择此歌曲")

    def hitButton(self, pos: QPoint) -> bool:
        # Keep the whole cell clickable; the painted square is only the visual indicator.
        return self.rect().contains(pos)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = 24
        x = (self.width() - size) / 2
        y = (self.height() - size) / 2
        checked = self.isChecked()
        hovered = self.underMouse()
        border = QPen(qcolor(self._colors["accent"] if checked or hovered else self._colors["muted"]), 2)
        p.setPen(border)
        p.setBrush(qcolor(self._colors["accent"] if checked else self._colors["card"]))
        p.drawRoundedRect(QRect(int(x), int(y), size, size), 6, 6)
        if checked:
            tick = QPen(qcolor(self._colors["accent_fg"]), 3)
            tick.setCapStyle(Qt.PenCapStyle.RoundCap)
            tick.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(tick)
            p.drawLine(int(x + 5), int(y + 12), int(x + 10), int(y + 17))
            p.drawLine(int(x + 10), int(y + 17), int(x + 20), int(y + 6))
        if self.hasFocus():
            p.setPen(qcolor(self._colors["accent"]))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRect(1, 1, self.width() - 3, self.height() - 3), 8, 8)
        p.end()


class CollectionCardDelegate(QStyledItemDelegate):
    """Paint selectable collection cards while retaining QListWidget item state."""

    def __init__(self, colors: dict[str, str], parent=None):
        super().__init__(parent)
        self.colors = colors

    def sizeHint(self, option, index):
        return QSize(216, 174)

    def paint(self, painter, option, index):
        p = painter
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = option.rect.adjusted(5, 5, -5, -5)
        check_state = index.data(Qt.ItemDataRole.CheckStateRole)
        checked = check_state == Qt.CheckState.Checked or check_state == Qt.CheckState.Checked.value
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        fill = qcolor(self.colors["card"])
        fill.setAlpha(210 if checked else 224)
        if checked:
            tint = qcolor(self.colors["accent"])
            tint.setAlpha(38)
            p.setPen(qcolor(self.colors["accent"]))
            p.setBrush(fill)
            p.drawRoundedRect(r, 16, 16)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(tint)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 15, 15)
        else:
            p.setPen(qcolor(self.colors["accent"] if selected else self.colors["border"]))
            p.setBrush(fill)
            p.drawRoundedRect(r, 16, 16)
            if hovered:
                p.setPen(qcolor(self.colors["accent"]))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r, 16, 16)

        box = QRect(r.right() - 36, r.top() + 12, 24, 24)
        p.setPen(qcolor(self.colors["accent"] if checked else self.colors["muted"]))
        p.setBrush(qcolor(self.colors["accent"] if checked else self.colors["card"]))
        p.drawRoundedRect(box, 6, 6)
        if checked:
            p.setPen(qcolor(self.colors["accent_fg"]))
            p.drawLine(box.left() + 5, box.top() + 12, box.left() + 10, box.top() + 17)
            p.drawLine(box.left() + 10, box.top() + 17, box.left() + 19, box.top() + 7)

        fx, fy = r.left() + 18, r.top() + 39
        folder = QPainterPath()
        folder.moveTo(fx + 1, fy + 7)
        folder.lineTo(fx + 12, fy + 7)
        folder.lineTo(fx + 17, fy + 12)
        folder.lineTo(fx + 37, fy + 12)
        folder.quadTo(fx + 41, fy + 12, fx + 41, fy + 16)
        folder.lineTo(fx + 41, fy + 35)
        folder.quadTo(fx + 41, fy + 39, fx + 37, fy + 39)
        folder.lineTo(fx + 4, fy + 39)
        folder.quadTo(fx, fy + 39, fx, fy + 35)
        folder.lineTo(fx, fy + 11)
        folder.quadTo(fx, fy + 7, fx + 1, fy + 7)
        folder.closeSubpath()
        p.setPen(qcolor(self.colors["accent"]))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(folder)

        title = str(index.data(Qt.ItemDataRole.DisplayRole) or "(未命名)")
        count = int(index.data(Qt.ItemDataRole.UserRole + 1) or 0)
        title_rect = QRect(r.left() + 16, r.top() + 99, r.width() - 32, 24)
        p.setPen(qcolor(self.colors["fg"]))
        font = p.font()
        font.setBold(True)
        font.setPointSize(10)
        p.setFont(font)
        p.drawText(title_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   p.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, title_rect.width()))
        font.setBold(False)
        font.setPointSize(9)
        p.setFont(font)
        p.setPen(qcolor(self.colors["muted"]))
        p.drawText(QRect(r.left() + 16, r.top() + 127, r.width() - 32, 18),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{count} 张谱面")
        p.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            # The card itself is a larger, forgiving target than the small checkbox glyph.
            raw_state = index.data(Qt.ItemDataRole.CheckStateRole)
            state = raw_state if isinstance(raw_state, Qt.CheckState) else Qt.CheckState(int(raw_state or 0))
            next_state = Qt.CheckState.Unchecked if state == Qt.CheckState.Checked else Qt.CheckState.Checked
            return model.setData(index, next_state, Qt.ItemDataRole.CheckStateRole)
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Space:
            raw_state = index.data(Qt.ItemDataRole.CheckStateRole) or Qt.CheckState.Unchecked
            state = raw_state if isinstance(raw_state, Qt.CheckState) else Qt.CheckState(int(raw_state))
            next_state = Qt.CheckState.Unchecked if state == Qt.CheckState.Checked else Qt.CheckState.Checked
            return model.setData(index, next_state, Qt.ItemDataRole.CheckStateRole)
        return False
