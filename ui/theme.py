"""Theme tokens and application-wide Qt styles."""
from __future__ import annotations

from PySide6.QtGui import QColor


def hex_rgb(color: str) -> tuple[int, int, int]:
    value = (color or "").lstrip("#")
    if len(value) != 6:
        return 128, 128, 128
    try:
        return int(value[:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError:
        return 128, 128, 128


def rgba(color: str, alpha: int = 255) -> str:
    r, g, b = hex_rgb(color)
    return f"rgba({r}, {g}, {b}, {max(0, min(255, int(alpha)))})"


def qcolor(color: str) -> QColor:
    return QColor(*hex_rgb(color))


def stylesheet(colors: dict[str, str], font_family: str) -> str:
    c = colors
    return f"""
        QWidget {{ font-family: '{font_family}'; font-size: 13px; color: {c['fg']}; }}
        QFrame#sidebar {{
            background-color: {rgba(c['sidebar'], 248)};
            border: 1px solid {rgba(c['border'], 220)}; border-radius: 20px;
        }}
        QLabel#brand {{ color: {c['accent']}; background: transparent; font-size: 32px; font-weight: 800; }}
        QLabel#sidebarSubtitle {{ color: {c['muted']}; font-size: 11px; }}
        QLabel#sidebarFoot {{ color: {c['muted']}; font-size: 10px; }}
        QFrame#playerBar {{
            background-color: {rgba(c['card'], 238)}; border: 1px solid {c['border']}; border-radius: 15px;
        }}
        QLabel#playerTitle {{ color: {c['fg']}; font-size: 12px; }}
        QLabel#playerTime {{ color: {c['muted']}; font-size: 11px; }}
        QPushButton#navBtn {{
            background: transparent; color: {c['muted']}; border: 1px solid transparent;
            border-radius: 11px; padding: 12px 15px; text-align: left; font-size: 14px;
        }}
        QPushButton#navBtn:hover {{ background: {rgba(c['hover'], 220)}; color: {c['fg']}; }}
        QPushButton#navBtn:checked {{
            background: {rgba(c['accent'], 30)}; color: {c['accent']};
            border-color: {rgba(c['accent'], 74)}; font-weight: 700;
        }}
        QPushButton#navBtn:focus {{ border-color: {c['accent']}; }}
        QWidget#page {{ background: transparent; }}
        QFrame#surface {{
            background-color: {rgba(c['card'], 238)}; border: 1px solid {c['border']};
            border-radius: 16px;
        }}
        QLabel#eyebrow {{ color: {c['accent']}; font-size: 10px; font-weight: 800; letter-spacing: 1px; }}
        QLabel#pageTitle {{ color: {c['fg']}; font-size: 25px; font-weight: 800; }}
        QLabel#pageSubtitle {{ color: {c['muted']}; font-size: 12px; }}
        QLabel#settingsSection {{ color: {c['accent']}; font-size: 11px; font-weight: 800; padding-top: 8px; }}
        QLineEdit, QComboBox {{
            background-color: {rgba(c['card'], 248)}; color: {c['fg']};
            border: 1px solid {c['border']}; border-radius: 10px;
            padding: 9px 12px; font-size: 13px; selection-background-color: {c['accent']};
        }}
        QLineEdit:hover, QComboBox:hover {{ border-color: {rgba(c['accent'], 145)}; }}
        QLineEdit:focus, QComboBox:focus {{ border: 1px solid {c['accent']}; }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox QAbstractItemView {{
            background: {c['card']}; color: {c['fg']}; selection-background-color: {c['accent']};
            selection-color: {c['accent_fg']}; border: 1px solid {c['border']}; padding: 5px;
        }}
        QTreeWidget, QListWidget {{
            background-color: {rgba(c['card'], 180)}; color: {c['fg']};
            border: 1px solid {c['border']}; border-radius: 15px; font-size: 13px;
        }}
        QTreeWidget::item, QListWidget::item {{ padding: 4px 6px; border-radius: 9px; }}
        QTreeWidget::item:selected, QListWidget::item:selected {{
            background: {rgba(c['accent'], 38)}; color: {c['fg']};
        }}
        QTreeWidget::item:hover, QListWidget::item:hover {{ background: {rgba(c['hover'], 210)}; }}
        QPushButton {{
            background-color: {rgba(c['card'], 246)}; color: {c['fg']};
            border: 1px solid {c['border']}; border-radius: 10px;
            padding: 9px 15px; font-size: 13px;
        }}
        QPushButton:hover {{ background: {c['hover']}; border-color: {rgba(c['accent'], 125)}; }}
        QPushButton:pressed {{ background: {rgba(c['accent'], 48)}; }}
        QPushButton:disabled {{ color: {c['muted']}; background: {c['bg']}; }}
        QPushButton.primary {{ background: {c['accent']}; color: {c['accent_fg']}; border: 1px solid {c['accent']}; font-weight: 700; }}
        QPushButton.primary:hover {{ background: {rgba(c['accent'], 220)}; }}
        QPushButton.secondary {{ background: {rgba(c['accent'], 24)}; border-color: {rgba(c['accent'], 76)}; color: {c['accent']}; }}
        QPushButton.secondary:hover {{ background: {rgba(c['accent'], 45)}; }}
        QPushButton.danger {{ color: {c['danger']}; }}
        QPushButton.danger:hover {{ background: {rgba(c['danger'], 30)}; border-color: {c['danger']}; }}
        QCheckBox {{ color: {c['fg']}; font-size: 13px; spacing: 8px; }}
        QSlider::groove:horizontal {{ height: 6px; background: {c['border']}; border-radius: 3px; }}
        QSlider::handle:horizontal {{ width: 16px; margin: -6px 0; background: {c['accent']}; border-radius: 8px; }}
        QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 3px; }}
        QScrollBar:vertical {{ width: 10px; background: transparent; margin: 3px; }}
        QScrollBar::handle:vertical {{ background: {rgba(c['muted'], 110)}; border-radius: 5px; min-height: 28px; }}
        QScrollBar::handle:vertical:hover {{ background: {rgba(c['accent'], 180)}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar:horizontal {{ height: 10px; background: transparent; margin: 3px; }}
        QScrollBar::handle:horizontal {{ background: {rgba(c['muted'], 110)}; border-radius: 5px; min-width: 28px; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QPushButton#playBtn {{ background: {c['accent']}; color: {c['accent_fg']}; border: none; border-radius: 15px; }}
    """
