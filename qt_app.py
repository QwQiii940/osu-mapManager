"""osu! 谱面管理 — PySide6 (Qt) 版主界面。

复用原有核心逻辑（manager / osudb / aliases / config / common / diffcalc），
仅重写 UI 层，以支持真透明背景、圆角、阴影等更现代的观感。
"""
from __future__ import annotations

import math
import os
import threading
from collections import OrderedDict

from PySide6.QtCore import Qt, QSize, QPoint, QRect, Signal, QThread, QTimer
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPixmap, QIcon
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QComboBox,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem, QStackedWidget,
    QHBoxLayout, QVBoxLayout, QGridLayout, QFormLayout, QScrollArea, QFileDialog,
    QMessageBox, QColorDialog, QSlider, QCheckBox, QProgressDialog, QMenu,
    QAbstractItemView, QStyle, QSizePolicy, QDialog, QDialogButtonBox, QHeaderView,
    QListView, QLayout,
)

import config
import diffcalc
from manager import OsuManager, Song, Beatmap, FilterCriteria
from common import (
    PAGE_SIZE, COLLECTION_PAGE_SIZE, CLASSIFY_MODES, MODE_FILTERS, MODE_MAP,
    DIFF_RANGES, _categories, _filter_songs_impl, _parse_float, _fmt_filter,
    _apply_advanced_filter, _filter_by_mode, _parse_thresholds,
)

_FONT_FAMILY = "Microsoft YaHei UI"


class FlowLayout(QLayout):
    """自动换行的流式布局：子项在宽度不足时换到下一行，避免重叠。"""

    def __init__(self, parent=None, margin=0, hspacing=6, vspacing=6):
        super().__init__(parent)
        self._items: list = []
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
            if x + hint.width() > right and line_height > 0:
                x = rect.x() + m.left()
                y += line_height + self._vspacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._hspacing
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + m.bottom()


def _hex_rgb(color: str) -> tuple[int, int, int]:
    c = (color or "").lstrip("#")
    if len(c) != 6:
        return (128, 128, 128)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _rgba(color: str, alpha: int = 255) -> str:
    r, g, b = _hex_rgb(color)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _qcolor(color: str) -> QColor:
    r, g, b = _hex_rgb(color)
    return QColor(r, g, b)


class Worker(QThread):
    """后台线程：执行耗时任务，通过信号回传进度与结果。"""
    progress = Signal(int, int)
    done = Signal(object)
    error = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            result = self.fn(self._cb)
            self.done.emit(result)
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))

    def _cb(self, done, total):
        self.progress.emit(done, total)


class MainWindow(QWidget):
    """主窗口：侧边栏导航 + 堆叠页面。"""

    def __init__(self, osu_dir: str):
        super().__init__()
        self.mgr = OsuManager(osu_dir)
        self.mgr.load()
        self.theme_name = config.load_theme()
        self.colors = config.get_theme_colors(self.theme_name)
        self.current_page = "home"
        self.viewing_collection: int | None = None

        # 歌曲/收藏夹浏览状态
        self._view_states: dict = {}
        self._songs: list[Song] = []
        self._collections_page = 0
        self._selected_collections: set[int] = set()
        self._thumb_cache = OrderedDict()
        self._player = None          # QMediaPlayer 惰性创建
        self._current_audio = None
        self._current_song = None
        self._seeking = False

        # 背景图
        self._bg_qimage: QImage | None = None
        self._bg_opacity = 0.0
        self._reload_bg()

        self.setWindowTitle("osu! 谱面管理")
        self.resize(1240, 800)
        self.setMinimumSize(900, 600)

        self._build_ui()
        self.show_page("home")

    # ------------------------------------------------------------------ 背景
    def _reload_bg(self):
        path = config.load_bg_image()
        if path and os.path.isfile(path):
            img = QImage(path)
            if not img.isNull():
                self._bg_qimage = img
                self._bg_opacity = max(0.0, min(1.0, config.load_bg_opacity() / 100.0))
                return
        self._bg_qimage = None
        self._bg_opacity = 0.0

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), _qcolor(self.colors["bg"]))
        if self._bg_qimage is not None:
            scaled = self._bg_qimage.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            p.setOpacity(self._bg_opacity)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.drawImage(x, y, scaled)
        p.end()

    # ------------------------------------------------------------------ 布局
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        content = QHBoxLayout()
        content.setSpacing(10)

        # 侧边栏
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(210)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(16, 22, 16, 18)
        side.setSpacing(6)

        brand = QLabel("osu!")
        brand.setObjectName("brand")
        brand.setStyleSheet(f"color: {self.colors['accent']}; font-size: 30px; font-weight: 800;")
        side.addWidget(brand)

        subtitle = QLabel("谱面管理 · Beatmap Manager")
        subtitle.setStyleSheet(f"color: {self.colors['muted']}; font-size: 11px;")
        side.addWidget(subtitle)
        side.addSpacing(16)

        self.nav_buttons: dict[str, QPushButton] = {}
        for key, label in [("home", "首页"), ("collections", "收藏夹"),
                           ("songs", "全部歌曲"), ("settings", "设置")]:
            b = QPushButton(label)
            b.setObjectName("navBtn")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.show_page(k))
            side.addWidget(b)
            self.nav_buttons[key] = b

        side.addStretch(1)
        foot = QLabel("数据均在本地处理")
        foot.setStyleSheet(f"color: {self.colors['muted']}; font-size: 10px;")
        side.addWidget(foot)

        # 页面堆叠
        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {}
        for key in ("home", "collections", "songs", "settings"):
            page = QWidget()
            page.setObjectName("page")
            lay = QVBoxLayout(page)
            lay.setContentsMargins(4, 4, 4, 4)
            page._layout = lay  # 供各页面构建时使用
            self.pages[key] = page
            self.stack.addWidget(page)

        content.addWidget(self.sidebar)
        content.addWidget(self.stack, 1)
        root.addLayout(content, 1)
        root.addWidget(self._build_player_bar())

        self._apply_styles()

    def _build_player_bar(self) -> QWidget:
        """底部播放控制条：播放/暂停、停止、进度条与时间显示。"""
        c = self.colors
        bar = QFrame()
        bar.setObjectName("playerBar")
        bar.setStyleSheet(
            f"QFrame#playerBar {{ background-color: {_rgba(c['card'], 235)}; border-radius: 12px; }}"
        )
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(10)

        self._btn_play = QPushButton("播放")
        self._btn_play.setFixedSize(76, 34)
        self._btn_play.setStyleSheet("QPushButton { font-size: 13px; }")
        self._btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_play.clicked.connect(self._toggle_pause)
        lay.addWidget(self._btn_play)

        self._btn_stop = QPushButton("停止")
        self._btn_stop.setFixedSize(76, 34)
        self._btn_stop.setStyleSheet("QPushButton { font-size: 13px; }")
        self._btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_stop.clicked.connect(self._stop_audio)
        lay.addWidget(self._btn_stop)

        self._now_title = QLabel("未播放")
        self._now_title.setStyleSheet(f"color: {c['muted']}; font-size: 12px;")
        self._now_title.setFixedWidth(220)
        self._now_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._now_title)

        self._time_cur = QLabel("0:00")
        self._time_cur.setStyleSheet(f"color: {c['fg']}; font-size: 11px;")
        lay.addWidget(self._time_cur)

        self._seek = QSlider(Qt.Orientation.Horizontal)
        self._seek.setRange(0, 0)
        self._seek.setEnabled(False)
        self._seek.sliderPressed.connect(self._on_seek_press)
        self._seek.sliderReleased.connect(self._on_seek_release)
        lay.addWidget(self._seek, 1)

        self._time_total = QLabel("0:00")
        self._time_total.setStyleSheet(f"color: {c['fg']}; font-size: 11px;")
        lay.addWidget(self._time_total)

        return bar

    def _apply_styles(self):
        c = self.colors
        self.setStyleSheet(f"""
            QFrame#sidebar {{
                background-color: {_rgba(c['sidebar'], 225)};
                border-radius: 16px;
            }}
            QLabel#brand {{ background: transparent; }}
            QPushButton#navBtn {{
                background: transparent; color: {c['fg']};
                border: none; border-radius: 11px;
                padding: 11px 16px; text-align: left; font-size: 14px;
            }}
            QPushButton#navBtn:hover {{ background: {_rgba(c['hover'], 200)}; }}
            QPushButton#navBtn:checked {{ background: {c['accent']}; color: {c['accent_fg']}; font-weight: 700; }}
            QWidget#page {{ background: transparent; }}
            QFrame.card {{
                background-color: {_rgba(c['card'], 235)};
                border-radius: 14px;
            }}
            QLabel.title {{ color: {c['fg']}; font-size: 20px; font-weight: 700; }}
            QLabel.sub {{ color: {c['muted']}; font-size: 12px; }}
            QLineEdit, QComboBox {{
                background-color: {c['card']}; color: {c['fg']};
                border: 1px solid {c['border']}; border-radius: 8px;
                padding: 7px 10px; font-size: 13px;
            }}
            QComboBox::drop-down {{ border: none; width: 22px; }}
            QComboBox QAbstractItemView {{
                background-color: {c['card']}; color: {c['fg']};
                selection-background-color: {c['accent']}; selection-color: {c['accent_fg']};
                border: 1px solid {c['border']};
            }}
            QTreeWidget, QListWidget {{
                background-color: {_rgba(c['card'], 230)};
                color: {c['fg']}; border: none; border-radius: 12px;
                font-size: 13px;
            }}
            QTreeWidget::item, QListWidget::item {{ padding: 6px; }}
            QTreeWidget::item:selected, QListWidget::item:selected {{
                background: {c['accent']}; color: {c['accent_fg']};
            }}
            QPushButton {{
                background-color: {c['card']}; color: {c['fg']};
                border: 1px solid {c['border']}; border-radius: 9px;
                padding: 8px 16px; font-size: 13px;
            }}
            QPushButton:hover {{ background-color: {c['hover']}; }}
            QPushButton.primary {{ background-color: {c['accent']}; color: {c['accent_fg']}; border: none; font-weight: 600; }}
            QPushButton.primary:hover {{ background-color: {c['accent']}; }}
            QPushButton.danger {{ color: #d9534f; }}
            QPushButton.danger:hover {{ background-color: #3a2a2e; }}
            QCheckBox {{ color: {c['fg']}; font-size: 13px; }}
            QSlider::groove:horizontal {{ height: 6px; background: {c['card']}; border-radius: 3px; }}
            QSlider::handle:horizontal {{ width: 16px; margin: -6px 0; background: {c['accent']}; border-radius: 8px; }}
            QSlider::sub-page:horizontal {{ background: {c['accent']}; border-radius: 3px; }}
            QPushButton#playBtn {{
                background-color: {c['accent']}; color: {c['accent_fg']};
                border: none; border-radius: 15px; padding: 0; font-size: 14px;
            }}
            QPushButton#playBtn:hover {{ background-color: {c['accent']}; }}
        """)

    def _make_card(self, parent_layout, stretch=0):
        card = QFrame()
        card.setObjectName("card")
        card.setProperty("class", "card")
        card.setStyleSheet("QFrame.card { background-color: %s; border-radius: 14px; }" % _rgba(self.colors["card"], 235))
        lay = QVBoxLayout(card)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)
        parent_layout.addWidget(card, stretch)
        return card, lay

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

    # ------------------------------------------------------------------ 导航
    def show_page(self, name: str):
        self.current_page = name
        for key, b in self.nav_buttons.items():
            b.setChecked(key == name)
        self._build_page(name)
        self.stack.setCurrentWidget(self.pages[name])

    def _build_page(self, name: str):
        lay = self.pages[name]._layout
        self._clear_layout(lay)
        if name == "home":
            self._build_home(lay)
        elif name == "collections":
            self._build_collections(lay)
        elif name == "songs":
            self._build_song_browser(lay, self.mgr.get_songs(), "全部歌曲", show_remove=False)
        elif name == "settings":
            self._build_settings(lay)

    # ------------------------------------------------------------------ 首页
    def _build_home(self, lay):
        songs = self.mgr.get_songs()
        title = QLabel("欢迎使用 osu! 谱面管理")
        title.setProperty("class", "title")
        title.setStyleSheet(f"color: {self.colors['fg']}; font-size: 26px; font-weight: 800;")
        lay.addWidget(title)
        sub = QLabel("整理你的谱面与收藏夹，支持筛选、批量操作与自动分类。")
        sub.setStyleSheet(f"color: {self.colors['muted']}; font-size: 13px;")
        lay.addWidget(sub)
        lay.addSpacing(10)

        stats = [("谱面集", len(songs)), ("难度", len(self.mgr.beatmaps)), ("收藏夹", len(self.mgr.collections))]
        grid = QHBoxLayout()
        grid.setSpacing(12)
        for t, v in stats:
            card = QFrame()
            card.setStyleSheet(f"QFrame {{ background-color: {_rgba(self.colors['card'], 235)}; border-radius: 16px; }}")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(22, 18, 22, 18)
            num = QLabel(str(v))
            num.setStyleSheet(f"color: {self.colors['accent']}; font-size: 30px; font-weight: 800;")
            lbl = QLabel(t)
            lbl.setStyleSheet(f"color: {self.colors['muted']}; font-size: 12px;")
            cl.addWidget(num)
            cl.addWidget(lbl)
            grid.addWidget(card, 1)
        lay.addLayout(grid)
        lay.addSpacing(14)

        dcard = QFrame()
        dcard.setStyleSheet(f"QFrame {{ background-color: {_rgba(self.colors['card'], 235)}; border-radius: 14px; }}")
        dl = QVBoxLayout(dcard)
        dl.setContentsMargins(20, 16, 20, 16)
        dl.addWidget(QLabel(f"当前 osu! 目录：{self.mgr.osu_dir}"))
        dl.itemAt(0).widget().setStyleSheet(f"color: {self.colors['fg']}; font-size: 12px;")
        lay.addWidget(dcard)
        lay.addSpacing(16)

        row = QHBoxLayout()
        row.setSpacing(10)
        for label, page in [("浏览全部歌曲", "songs"), ("管理收藏夹", "collections"), ("打开设置", "settings")]:
            b = QPushButton(label)
            b.setProperty("class", "primary")
            b.setStyleSheet(f"QPushButton {{ background: {self.colors['accent']}; color: {self.colors['accent_fg']}; border: none; border-radius: 10px; padding: 10px 20px; font-weight: 600; }}")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, p=page: self.show_page(p))
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        lay.addStretch(1)

    # ------------------------------------------------------------------ 收藏夹
    def _build_collections(self, lay):
        head = QHBoxLayout()
        t = QLabel("收藏夹")
        t.setStyleSheet(f"color: {self.colors['fg']}; font-size: 22px; font-weight: 700;")
        head.addWidget(t)
        head.addStretch(1)

        search = QLineEdit()
        search.setPlaceholderText("搜索收藏夹…")
        search.setFixedWidth(200)
        head.addWidget(search)

        btn_new = QPushButton("新建收藏夹")
        btn_new.setProperty("class", "primary")
        btn_new.setStyleSheet(f"QPushButton {{ background: {self.colors['accent']}; color: {self.colors['accent_fg']}; border: none; border-radius: 9px; padding: 8px 16px; font-weight: 600; }}")
        btn_new.clicked.connect(self._new_collection)
        head.addWidget(btn_new)

        btn_auto = QPushButton("自动分类…")
        btn_auto.clicked.connect(self._auto_categorize)
        head.addWidget(btn_auto)

        btn_reorg = QPushButton("重新整理…")
        btn_reorg.clicked.connect(self._reorganize_collections)
        head.addWidget(btn_reorg)
        lay.addLayout(head)

        # 工具栏
        bar = QHBoxLayout()
        self._batch_label = QLabel("已选 0 个")
        self._batch_label.setStyleSheet(f"color: {self.colors['muted']}; font-size: 12px;")
        bar.addWidget(self._batch_label)
        self._merge_btn = QPushButton("合并所选")
        self._merge_btn.clicked.connect(self._merge_selected)
        self._delete_btn = QPushButton("删除所选")
        self._delete_btn.setProperty("class", "danger")
        self._delete_btn.setStyleSheet(f"QPushButton {{ color: #d9534f; }}")
        self._delete_btn.clicked.connect(self._delete_selected)
        self._export_btn = QPushButton("导出所选")
        self._export_btn.clicked.connect(self._export_selected)
        bar.addWidget(self._merge_btn)
        bar.addWidget(self._delete_btn)
        bar.addWidget(self._export_btn)
        btn_dedupe = QPushButton("合并同名收藏夹")
        btn_dedupe.clicked.connect(self._dedupe_collections)
        bar.addStretch(1)
        bar.addWidget(QLabel("排序"))
        self._sort_combo = QComboBox()
        self._sort_combo.addItems(["默认顺序", "按名称", "按数量"])
        self._sort_combo.currentIndexChanged.connect(lambda _: self._refresh_collections())
        bar.addWidget(self._sort_combo)
        bar.addWidget(btn_dedupe)
        lay.addLayout(bar)

        self.col_list = QListWidget()
        self.col_list.setViewMode(QListView.ViewMode.IconMode)
        self.col_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.col_list.setMovement(QListView.Movement.Static)
        self.col_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.col_list.setIconSize(QSize(64, 64))
        self.col_list.setGridSize(QSize(150, 130))
        self.col_list.setWordWrap(True)
        self.col_list.itemDoubleClicked.connect(lambda it: self._open_collection(it.data(Qt.ItemDataRole.UserRole)))
        self.col_list.itemSelectionChanged.connect(self._update_batch_buttons)
        lay.addWidget(self.col_list, 1)

        pager = QHBoxLayout()
        self._prev_btn = QPushButton("‹ 上一页")
        self._next_btn = QPushButton("下一页 ›")
        self._pager_label = QLabel("")
        self._pager_label.setStyleSheet(f"color: {self.colors['muted']};")
        self._prev_btn.clicked.connect(lambda: self._collections_turn(-1))
        self._next_btn.clicked.connect(lambda: self._collections_turn(1))
        pager.addWidget(self._prev_btn)
        pager.addWidget(self._next_btn)
        pager.addWidget(self._pager_label)
        pager.addStretch(1)
        lay.addLayout(pager)

        self._collections_query = ""
        search.textChanged.connect(self._on_collections_search)
        self._refresh_collections()

    def _folder_icon(self):
        return self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)

    def _on_collections_search(self, text):
        self._collections_query = text.strip().lower()
        self._collections_page = 0
        self._refresh_collections()

    def _refresh_collections(self):
        items = [(i, c) for i, c in enumerate(self.mgr.collections)
                 if not self._collections_query or self._collections_query in (c.name or "").lower()]
        sort_mode = getattr(self, "_sort_combo", None)
        if sort_mode is not None:
            sort_mode = sort_mode.currentText()
            if sort_mode == "按名称":
                items = sorted(items, key=lambda t: (t[1].name or "").lower())
            elif sort_mode == "按数量":
                items = sorted(items, key=lambda t: len(t[1].beatmap_hashes), reverse=True)
        total = len(items)
        pages = max(1, math.ceil(total / COLLECTION_PAGE_SIZE))
        if self._collections_page >= pages:
            self._collections_page = pages - 1
        start = self._collections_page * COLLECTION_PAGE_SIZE
        page = items[start:start + COLLECTION_PAGE_SIZE]

        self.col_list.clear()
        for gidx, c in page:
            it = QListWidgetItem(self._folder_icon(), c.name or "(未命名)")
            it.setData(Qt.ItemDataRole.UserRole, gidx)
            it.setToolTip(f"{c.name}\n{c.__class__ and len(c.beatmap_hashes)} 张谱面")
            self.col_list.addItem(it)

        self._pager_label.setText(f"第 {self._collections_page + 1} / {pages} 页 · 共 {total} 个")
        self._prev_btn.setEnabled(self._collections_page > 0)
        self._next_btn.setEnabled(self._collections_page < pages - 1)
        self._update_batch_buttons()

    def _collections_turn(self, delta):
        self._collections_page += delta
        if self._collections_page < 0:
            self._collections_page = 0
        self._refresh_collections()

    def _selected_indices(self) -> list[int]:
        return sorted({self.col_list.item(i).data(Qt.ItemDataRole.UserRole)
                       for i in range(self.col_list.count()) if self.col_list.item(i).isSelected()})

    def _update_batch_buttons(self):
        n = len(self._selected_indices())
        self._batch_label.setText(f"已选 {n} 个")
        self._merge_btn.setEnabled(n >= 2)
        self._delete_btn.setEnabled(n >= 1)
        self._export_btn.setEnabled(n >= 1)

    def _export_selected(self):
        idxs = self._selected_indices()
        if not idxs:
            QMessageBox.information(self, "提示", "请先勾选要导出的收藏夹。")
            return
        target = QFileDialog.getExistingDirectory(self, "选择 .osz 导出目录")
        if not target:
            return
        ok_total, fail_total = 0, 0
        for idx in idxs:
            ok, failed = self.mgr.export_collection(idx, target)
            ok_total += ok
            fail_total += len(failed)
        msg = f"已导出 {ok_total} 个 .osz。"
        if fail_total:
            msg += f"\n失败 {fail_total} 个"
        QMessageBox.information(self, "结果", msg)

    def _new_collection(self):
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "新建收藏夹", "收藏夹名称：")
        if ok and name.strip():
            self.mgr.add_collection(name.strip())
            self._refresh_collections()

    def _prompt_rename(self, index: int) -> bool:
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "重命名", "新名称：", text=self.mgr.collections[index].name)
        if ok and name.strip():
            self.mgr.rename_collection(index, name.strip())
            return True
        return False

    def _open_collection(self, index: int):
        self.viewing_collection = index
        songs = self.mgr.songs_in_collection(index)
        name = self.mgr.collections[index].name or "(未命名)"
        lay = self.pages["songs"]._layout
        self._clear_layout(lay)
        self._build_song_browser(lay, songs, name, show_remove=True)
        self.stack.setCurrentWidget(self.pages["songs"])
        self.nav_buttons["collections"].setChecked(True)
        self.current_page = "collections"

    def _back_to_collections(self):
        self.viewing_collection = None
        self.show_page("collections")

    def _confirm_delete(self, title: str, message: str) -> bool:
        """删除确认；若在设置中关闭「删除前弹出确认」则直接放行。"""
        if not config.load_confirm_delete():
            return True
        return QMessageBox.question(self, title, message) == QMessageBox.StandardButton.Yes

    def _delete_collection(self, index: int):
        if not self._confirm_delete("删除收藏夹", f"确定删除收藏夹「{self.mgr.collections[index].name}」？\n（仅删除收藏夹，不删除谱面文件）"):
            return
        self.mgr.delete_collection(index)
        self.viewing_collection = None
        self._refresh_collections()

    def _merge_selected(self):
        idxs = self._selected_indices()
        if len(idxs) < 2:
            return
        names = [self.mgr.collections[i].name for i in idxs]
        if QMessageBox.question(self, "合并收藏夹", f"将把 {len(idxs)} 个收藏夹合并到「{names[0]}」，其余删除。继续？") != QMessageBox.StandardButton.Yes:
            return
        target = self.mgr.merge_collections(idxs)
        self._refresh_collections()
        QMessageBox.information(self, "完成", f"已合并到「{target}」。")

    def _delete_selected(self):
        idxs = self._selected_indices()
        if not idxs:
            return
        if not self._confirm_delete("删除收藏夹", f"确定删除选中的 {len(idxs)} 个收藏夹？\n（仅删除收藏夹，不删除谱面文件）"):
            return
        self.mgr.delete_collections(idxs)
        self._refresh_collections()

    def _dedupe_collections(self):
        if QMessageBox.question(self, "合并同名收藏夹", "将合并名称相同的收藏夹（谱面去重）。继续？") != QMessageBox.StandardButton.Yes:
            return
        merged = self.mgr.dedupe_collections()
        self._refresh_collections()
        QMessageBox.information(self, "完成", f"已合并 {merged} 个同名收藏夹。" if merged else "没有发现同名收藏夹。")

    def _auto_categorize(self):
        dlg = _AutoCategorizeDialog(self, self.mgr)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh_collections()

    def _reorganize_collections(self):
        dlg = _ReorganizeDialog(self, self.mgr)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.viewing_collection = None
            self._refresh_collections()

    def _export_collection(self, index: int):
        target = QFileDialog.getExistingDirectory(self, "选择 .osz 导出目录")
        if not target:
            return
        ok, failed = self.mgr.export_collection(index, target)
        msg = f"已导出 {ok} 个 .osz。"
        if failed:
            msg += f"\n失败 {len(failed)} 个"
        QMessageBox.information(self, "结果", msg)

    # ------------------------------------------------------------------ 歌曲浏览
    def _view_state(self, show_remove: bool) -> dict:
        key = "collection" if show_remove else "songs"
        st = self._view_states.setdefault(key, {
            "mode": "全部", "category": None, "search": "", "page": 0,
            "letter": "", "artist": "", "len_min": None, "len_max": None,
            "star_min": None, "star_max": None, "game_mode": "全部",
        })
        return st

    def _filtered_songs(self, songs: list[Song], st: dict) -> list[Song]:
        out = _filter_songs_impl(songs, st["mode"], st["category"], st["search"])
        out = _apply_advanced_filter(
            out, st["letter"], st["artist"], st["len_min"], st["len_max"],
            st["star_min"], st["star_max"],
        )
        return _filter_by_mode(out, st["game_mode"])

    def _build_song_browser(self, lay, songs: list[Song], title: str, show_remove: bool):
        self._songs = songs
        self._show_remove = show_remove
        st = self._view_state(show_remove)

        head = QHBoxLayout()
        if show_remove:
            back = QPushButton("← 返回")
            back.clicked.connect(self._back_to_collections)
            head.addWidget(back)
        t = QLabel(title)
        t.setStyleSheet(f"color: {self.colors['fg']}; font-size: 22px; font-weight: 700;")
        head.addWidget(t)
        if show_remove and self.viewing_collection is not None:
            ci = self.viewing_collection
            b_rename = QPushButton("重命名")
            b_rename.clicked.connect(lambda: (self._prompt_rename(ci) and self._open_collection(ci)))
            b_export = QPushButton("导出 .osz")
            b_export.clicked.connect(lambda: self._export_collection(ci))
            b_del = QPushButton("删除收藏夹")
            b_del.setProperty("class", "danger")
            b_del.setStyleSheet("QPushButton { color: #d9534f; }")
            b_del.clicked.connect(lambda: self._delete_collection(ci))
            head.addWidget(b_rename)
            head.addWidget(b_export)
            head.addWidget(b_del)
        head.addStretch(1)

        search = QLineEdit(st["search"])
        search.setPlaceholderText("搜索 标题/艺术家/创作者…")
        search.setFixedWidth(240)
        head.addWidget(search)

        combo = QComboBox()
        combo.addItems(CLASSIFY_MODES)
        combo.setCurrentText(st["mode"])
        head.addWidget(combo)
        lay.addLayout(head)

        # 筛选栏（流式布局，窗口缩小时自动换行，避免重叠）
        fbar = FlowLayout()

        def group(*widgets):
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(4)
            for x in widgets:
                h.addWidget(x)
            return w

        self._e_letter = QLineEdit(st["letter"])
        self._e_letter.setFixedWidth(46)
        self._e_artist = QLineEdit(st["artist"])
        self._e_artist.setFixedWidth(120)
        self._e_len_min = QLineEdit(_fmt_filter(st["len_min"]))
        self._e_len_min.setFixedWidth(52)
        self._e_len_max = QLineEdit(_fmt_filter(st["len_max"]))
        self._e_len_max.setFixedWidth(52)
        self._e_star_min = QLineEdit(_fmt_filter(st["star_min"]))
        self._e_star_min.setFixedWidth(46)
        self._e_star_max = QLineEdit(_fmt_filter(st["star_max"]))
        self._e_star_max.setFixedWidth(46)
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(MODE_FILTERS)
        self._mode_combo.setCurrentText(st["game_mode"])

        fbar.addWidget(group(QLabel("首字母"), self._e_letter))
        fbar.addWidget(group(QLabel("artist"), self._e_artist))
        fbar.addWidget(group(QLabel("长度(秒)"), self._e_len_min, QLabel("~"), self._e_len_max))
        fbar.addWidget(group(QLabel("星级"), self._e_star_min, QLabel("~"), self._e_star_max))
        fbar.addWidget(group(QLabel("模式"), self._mode_combo))

        apply_btn = QPushButton("应用")
        apply_btn.setProperty("class", "primary")
        apply_btn.setStyleSheet(f"QPushButton {{ background: {self.colors['accent']}; color: {self.colors['accent_fg']}; border: none; border-radius: 8px; padding: 7px 14px; font-weight: 600; }}")
        apply_btn.clicked.connect(lambda: self._apply_filter(search, combo))
        reset_btn = QPushButton("重置")
        reset_btn.clicked.connect(lambda: self._reset_filter(search, combo))
        fbar.addWidget(apply_btn)
        fbar.addWidget(reset_btn)
        if not show_remove:
            move_btn = QPushButton("勾选加入收藏夹")
            move_btn.clicked.connect(self._batch_add_checked)
            del_btn = QPushButton("删除勾选")
            del_btn.setProperty("class", "danger")
            del_btn.setStyleSheet("QPushButton { color: #d9534f; }")
            del_btn.clicked.connect(self._batch_delete_checked)
            fbar.addWidget(move_btn)
            fbar.addWidget(del_btn)
        lay.addLayout(fbar)

        # 分类列表 + 歌曲树
        body = QHBoxLayout()
        body.setSpacing(10)
        self._cat_list = QListWidget()
        self._cat_list.setFixedWidth(170)
        self._cat_list.itemClicked.connect(lambda _: self._on_cat_select(combo))
        body.addWidget(self._cat_list)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(3)
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(18)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._song_context_menu)
        self._tree.header().setStretchLastSection(False)
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._tree.setColumnWidth(0, 34)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._tree.setColumnWidth(2, 148)
        body.addWidget(self._tree, 1)
        lay.addLayout(body, 1)

        pager = QHBoxLayout()
        self._sprev = QPushButton("‹ 上一页")
        self._snext = QPushButton("下一页 ›")
        self._slabel = QLabel("")
        self._slabel.setStyleSheet(f"color: {self.colors['muted']};")
        self._sprev.clicked.connect(lambda: self._song_page(-1, search, combo))
        self._snext.clicked.connect(lambda: self._song_page(1, search, combo))
        pager.addWidget(self._sprev)
        pager.addWidget(self._snext)
        pager.addWidget(self._slabel)
        pager.addStretch(1)
        lay.addLayout(pager)

        search.textChanged.connect(lambda _: self._song_page(0, search, combo))
        combo.currentTextChanged.connect(lambda _: self._song_page(0, search, combo))
        self._refresh_categories()
        self._song_page(0, search, combo)

    def _refresh_categories(self):
        st = self._view_state(self._show_remove)
        self._cat_list.clear()
        cats = _categories(self._songs, st["mode"])
        self._cat_list.addItems(cats)
        self._cat_list.setVisible(st["mode"] != "全部")

    def _on_cat_select(self, combo):
        st = self._view_state(self._show_remove)
        item = self._cat_list.currentItem()
        st["category"] = item.text() if item else None
        st["page"] = 0
        self._song_page(0, None, combo)

    def _apply_filter(self, search, combo):
        st = self._view_state(self._show_remove)
        st["letter"] = self._e_letter.text().strip()
        st["artist"] = self._e_artist.text().strip()
        st["len_min"] = _parse_float(self._e_len_min.text())
        st["len_max"] = _parse_float(self._e_len_max.text())
        st["star_min"] = _parse_float(self._e_star_min.text())
        st["star_max"] = _parse_float(self._e_star_max.text())
        st["game_mode"] = self._mode_combo.currentText()
        st["page"] = 0
        self._song_page(0, search, combo)

    def _reset_filter(self, search, combo):
        st = self._view_state(self._show_remove)
        for k in ("letter", "artist", "len_min", "len_max", "star_min", "star_max"):
            st[k] = "" if k in ("letter", "artist") else None
        st["game_mode"] = "全部"
        self._e_letter.setText("")
        self._e_artist.setText("")
        self._e_len_min.setText("")
        self._e_len_max.setText("")
        self._e_star_min.setText("")
        self._e_star_max.setText("")
        self._mode_combo.setCurrentText("全部")
        st["page"] = 0
        self._song_page(0, search, combo)

    def _song_page(self, delta, search, combo):
        st = self._view_state(self._show_remove)
        if search is not None:
            st["search"] = search.text().strip()
        if combo is not None:
            st["mode"] = combo.currentText()
            st["category"] = None
        st["page"] = max(0, st["page"] + delta)
        result = self._filtered_songs(self._songs, st)
        total = len(result)
        pages = max(1, math.ceil(total / PAGE_SIZE))
        if st["page"] >= pages:
            st["page"] = pages - 1
        start = st["page"] * PAGE_SIZE
        page = result[start:start + PAGE_SIZE]

        # 重建期间暂停重绘，避免逐条 addItem/setItemWidget 触发多次布局与绘制
        self._tree.setUpdatesEnabled(False)
        self._tree.clear()
        for s in page:
            parent = QTreeWidgetItem(["", "", ""])
            parent.setData(0, Qt.ItemDataRole.UserRole, ("song", s))

            for b in s.beatmaps:
                child = QTreeWidgetItem(["", "", ""])
                child.setData(0, Qt.ItemDataRole.UserRole, ("beatmap", b))
                child.setSizeHint(0, QSize(34, 42))
                parent.addChild(child)

            self._tree.addTopLevelItem(parent)

            cb = QCheckBox()
            cb.setCursor(Qt.CursorShape.PointingHandCursor)
            cb.setStyleSheet(
                "QCheckBox { background: transparent; }"
                f"QCheckBox::indicator {{ width: 16px; height: 16px; border: 2px solid {self.colors['border']}; border-radius: 4px; background: transparent; }}"
                f"QCheckBox::indicator:checked {{ background: {self.colors['accent']}; border-color: {self.colors['accent']}; }}"
            )
            self._tree.setItemWidget(parent, 0, cb)
            self._tree.setItemWidget(parent, 1, self._song_info_widget(s))
            self._tree.setItemWidget(parent, 2, self._song_actions_widget(s))

            for i, b in enumerate(s.beatmaps):
                ch = parent.child(i)
                self._tree.setItemWidget(ch, 1, self._beatmap_info_widget(b))
                self._tree.setItemWidget(ch, 2, self._beatmap_actions_widget(b))

        self._tree.setUpdatesEnabled(True)
        self._slabel.setText(f"第 {st['page'] + 1} / {pages} 页 · 共 {total} 首")
        self._sprev.setEnabled(st["page"] > 0)
        self._snext.setEnabled(st["page"] < pages - 1)

    def _star_text(self, s: Song) -> str:
        return f"{s.star_min:.1f}~{s.star_max:.1f}" if s.star_max > 0 else "-"

    def _stat_text(self, s: Song) -> str:
        def rng(vals):
            if not vals:
                return "-"
            lo, hi = min(vals), max(vals)
            return f"{lo:.1f}" if abs(hi - lo) < 0.05 else f"{lo:.1f}~{hi:.1f}"
        ars = [b.ar for b in s.beatmaps if b.ar > 0]
        ods = [b.od for b in s.beatmaps if b.od > 0]
        bpms = [b.bpm for b in s.beatmaps if b.bpm > 0]
        return f"AR {rng(ars)} · OD {rng(ods)} · BPM {rng(bpms)}"

    def _song_icon(self, s: Song, size: QSize = QSize(48, 48)) -> QPixmap:
        """加载谱面背景缩略图（带缓存）；无图时返回纯色占位。"""
        key = (s.folder_name, size.width(), size.height())
        if key in self._thumb_cache:
            return self._thumb_cache[key]
        pix = QPixmap(size)
        pix.fill(_qcolor(self.colors["card"]))
        path = self.mgr.find_song_image(s.folder_name)
        if path and os.path.isfile(path):
            loaded = QPixmap(path)
            if not loaded.isNull():
                loaded = loaded.scaled(size, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                       Qt.TransformationMode.SmoothTransformation)
                x = max(0, (loaded.width() - size.width()) // 2)
                y = max(0, (loaded.height() - size.height()) // 2)
                pix = loaded.copy(x, y, size.width(), size.height())
        self._thumb_cache[key] = pix
        while len(self._thumb_cache) > 500:
            self._thumb_cache.popitem(last=False)
        return pix

    def _song_context_menu(self, pos):
        menu = QMenu(self)
        selected = self._selected_songs()
        if len(selected) > 1:
            if self._show_remove:
                act = menu.addAction(f"从收藏夹移除（{len(selected)} 首）")
                act.triggered.connect(self._batch_remove_selected)
            else:
                act = menu.addAction(f"加入收藏夹（{len(selected)} 首）")
                act.triggered.connect(self._batch_add_selected)
            menu.exec(self._tree.viewport().mapToGlobal(pos))
            return

        item = self._tree.itemAt(pos)
        if item is None:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not data:
            return
        kind, obj = data
        if kind == "song":
            act = menu.addAction("播放音频")
            act.triggered.connect(lambda: self._toggle_audio(obj))
            if self._show_remove:
                act = menu.addAction("从收藏夹移除")
                act.triggered.connect(lambda: self._song_remove(obj))
            else:
                act = menu.addAction("加入收藏夹")
                act.triggered.connect(lambda: self._song_add(obj))
            act = menu.addAction("删除谱面集")
            act.triggered.connect(lambda: self._song_delete(obj))
        else:
            act = menu.addAction("删除该难度")
            act.triggered.connect(lambda: self._beatmap_delete(obj))
        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _selected_songs(self) -> list[Song]:
        songs: list[Song] = []
        seen = set()
        for item in self._tree.selectedItems():
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == "song":
                s = data[1]
                if id(s) not in seen:
                    seen.add(id(s))
                    songs.append(s)
        return songs

    def _batch_add_selected(self):
        songs = self._selected_songs()
        if not songs:
            return
        names = [c.name or "(未命名)" for c in self.mgr.collections]
        if not names:
            QMessageBox.information(self, "提示", "当前没有收藏夹，请先新建。")
            return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getItem(self, "加入收藏夹", f"将 {len(songs)} 首歌加入收藏夹：", names, 0, False)
        if not ok:
            return
        idx = names.index(name)
        added = 0
        for s in songs:
            hashes = [b.md5 for b in s.beatmaps if b.md5]
            added += self.mgr.add_hashes_to_collection(idx, hashes)
        QMessageBox.information(self, "结果", f"已加入 {added} 张谱面到「{self.mgr.collections[idx].name}」。")

    def _batch_remove_selected(self):
        songs = self._selected_songs()
        ci = self.viewing_collection
        if not songs or ci is None:
            return
        for s in songs:
            hashes = [b.md5 for b in s.beatmaps if b.md5]
            self.mgr.remove_hashes_from_collection(ci, hashes)
        self._reload_current_songs()

    def _audio_player(self):
        if self._player is None:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            self._player = QMediaPlayer(self)
            self._audio_out = QAudioOutput(self)
            self._player.setAudioOutput(self._audio_out)
            self._player.positionChanged.connect(self._on_position)
            self._player.durationChanged.connect(self._on_duration)
            self._player.playbackStateChanged.connect(self._on_state)
        return self._player

    def _toggle_audio(self, song: Song):
        path = self.mgr.find_song_audio(song.folder_name)
        if not path:
            QMessageBox.information(self, "提示", "未找到该谱面的音频文件。")
            return
        try:
            player = self._audio_player()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "提示", f"无法初始化音频播放：{e}")
            return
        from PySide6.QtMultimedia import QMediaPlayer
        state = player.playbackState()
        if self._current_audio == path:
            if state == QMediaPlayer.PlaybackState.PlayingState:
                player.pause()
            elif state == QMediaPlayer.PlaybackState.PausedState:
                player.play()
            else:
                player.setPosition(0)
                player.play()
            return
        from PySide6.QtCore import QUrl
        self._current_song = song
        self._current_audio = path
        self._now_title.setText(song.title or "(无标题)")
        player.setSource(QUrl.fromLocalFile(path))
        player.play()

    def _toggle_pause(self):
        if self._current_audio is None:
            return
        try:
            player = self._audio_player()
        except Exception:  # noqa: BLE001
            return
        from PySide6.QtMultimedia import QMediaPlayer
        if player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            player.pause()
        elif player.playbackState() == QMediaPlayer.PlaybackState.PausedState:
            player.play()
        else:
            player.setPosition(0)
            player.play()

    def _stop_audio(self):
        if self._player is None or self._current_audio is None:
            return
        self._player.stop()
        self._current_audio = None
        self._current_song = None
        self._now_title.setText("未播放")
        self._seek.setValue(0)
        self._time_cur.setText("0:00")
        self._time_total.setText("0:00")

    def _on_position(self, ms: int):
        if not self._seeking:
            self._seek.setValue(ms)
        self._time_cur.setText(self._fmt_time(ms))

    def _on_duration(self, ms: int):
        self._seek.setRange(0, ms if ms > 0 else 0)
        self._seek.setEnabled(ms > 0)
        self._time_total.setText(self._fmt_time(ms))

    def _on_state(self, state):
        from PySide6.QtMultimedia import QMediaPlayer
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self._btn_play.setText("暂停" if playing else "播放")

    def _on_seek_press(self):
        self._seeking = True

    def _on_seek_release(self):
        self._seeking = False
        if self._player is not None and self._current_audio is not None:
            self._player.setPosition(self._seek.value())

    @staticmethod
    def _fmt_time(ms: int) -> str:
        ms = max(0, int(ms))
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    def _song_actions_widget(self, song: Song) -> QWidget:
        """歌曲行右侧的操作按钮：加入/移出收藏夹 + 删除。"""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(6)
        btn_style = "QPushButton { padding: 6px 10px; font-size: 12px; min-width: 56px; }"
        if self._show_remove:
            b_rm = QPushButton("移除")
            b_rm.setStyleSheet(btn_style + " QPushButton { color: #d9534f; }")
            b_rm.setCursor(Qt.CursorShape.PointingHandCursor)
            b_rm.clicked.connect(lambda _=False, s=song: self._song_remove(s))
            h.addWidget(b_rm)
        else:
            b_add = QPushButton("收藏")
            b_add.setStyleSheet(btn_style)
            b_add.setCursor(Qt.CursorShape.PointingHandCursor)
            b_add.clicked.connect(lambda _=False, s=song: self._song_add(s))
            h.addWidget(b_add)
        b_del = QPushButton("删除")
        b_del.setStyleSheet(btn_style + " QPushButton { color: #d9534f; }")
        b_del.setCursor(Qt.CursorShape.PointingHandCursor)
        b_del.clicked.connect(lambda _=False, s=song: self._song_delete(s))
        h.addWidget(b_del)
        return w

    def _beatmap_actions_widget(self, b: Beatmap) -> QWidget:
        """难度行右侧的操作按钮：加入/移出收藏夹 + 删除该难度。"""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(6)
        btn_style = "QPushButton { padding: 6px 10px; font-size: 12px; min-width: 56px; }"
        if self._show_remove:
            b_rm = QPushButton("移除")
            b_rm.setStyleSheet(btn_style + " QPushButton { color: #d9534f; }")
            b_rm.setCursor(Qt.CursorShape.PointingHandCursor)
            b_rm.clicked.connect(lambda _=False, bm=b: self._beatmap_remove(bm))
            h.addWidget(b_rm)
        else:
            b_add = QPushButton("收藏")
            b_add.setStyleSheet(btn_style)
            b_add.setCursor(Qt.CursorShape.PointingHandCursor)
            b_add.clicked.connect(lambda _=False, bm=b: self._beatmap_add(bm))
            h.addWidget(b_add)
        b_del = QPushButton("删除")
        b_del.setStyleSheet(btn_style + " QPushButton { color: #d9534f; }")
        b_del.setCursor(Qt.CursorShape.PointingHandCursor)
        b_del.clicked.connect(lambda _=False, bm=b: self._beatmap_delete(bm))
        h.addWidget(b_del)
        return w

    def _song_info_widget(self, s: Song) -> QWidget:
        """歌曲行信息：缩略图 + 标题 + 播放按钮 + 艺术家/星级/AR·OD·BPM（可换行）。"""
        c = self.colors
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 2, 2, 2)
        h.setSpacing(8)

        thumb = QLabel()
        thumb.setPixmap(self._song_icon(s))
        thumb.setFixedSize(48, 48)
        h.addWidget(thumb)

        v = QVBoxLayout()
        v.setSpacing(2)

        tr = QHBoxLayout()
        tr.setSpacing(6)
        title = QLabel(s.title or "(无标题)")
        title.setStyleSheet(f"color: {c['fg']}; font-size: 14px; font-weight: 600;")
        title.setWordWrap(True)
        play = QPushButton("▶")
        play.setObjectName("playBtn")
        play.setFixedSize(28, 28)
        play.setCursor(Qt.CursorShape.PointingHandCursor)
        play.setToolTip("播放/暂停音频")
        play.clicked.connect(lambda _=False, sng=s: self._toggle_audio(sng))
        tr.addWidget(title)
        tr.addWidget(play)
        tr.addStretch(1)
        v.addLayout(tr)

        info = QLabel(self._song_info_text(s))
        info.setStyleSheet(f"color: {c['muted']}; font-size: 12px;")
        info.setWordWrap(True)
        v.addWidget(info)

        h.addLayout(v, 1)
        return w

    def _beatmap_info_widget(self, b: Beatmap) -> QWidget:
        """难度行信息：难度名 + 模式/星级/AR·OD·CS·HP·BPM（可换行）。"""
        c = self.colors
        bpm = f"{b.bpm:.0f}" if b.bpm > 0 else "-"
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(2, 1, 2, 1)
        h.setSpacing(6)

        name = QLabel(b.difficulty_name or "(未命名)")
        name.setStyleSheet(f"color: {c['fg']}; font-size: 13px;")
        name.setWordWrap(True)
        h.addWidget(name)

        info = QLabel(f"{b.mode_name} · ★ {b.star_rating:.2f} · AR{b.ar:.1f} OD{b.od:.1f} CS{b.cs:.1f} HP{b.hp:.1f} BPM{bpm}")
        info.setStyleSheet(f"color: {c['muted']}; font-size: 11px;")
        info.setWordWrap(True)
        h.addWidget(info, 1)
        return w

    def _song_info_text(self, s: Song) -> str:
        artist = s.artist or "(未知艺术家)"
        return f"{artist}  ·  ★ {self._star_text(s)}  ·  {self._stat_text(s)}"

    def _checked_songs(self) -> list[Song]:
        songs: list[Song] = []
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            cb = self._tree.itemWidget(item, 0)
            if isinstance(cb, QCheckBox) and cb.isChecked():
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and data[0] == "song":
                    songs.append(data[1])
        return songs

    def _batch_add_checked(self):
        songs = self._checked_songs()
        if not songs:
            QMessageBox.information(self, "提示", "请先在左侧勾选要加入收藏夹的歌曲。")
            return
        names = [c.name or "(未命名)" for c in self.mgr.collections]
        if not names:
            QMessageBox.information(self, "提示", "当前没有收藏夹，请先新建。")
            return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getItem(self, "加入收藏夹", f"将 {len(songs)} 首歌加入收藏夹：", names, 0, False)
        if not ok:
            return
        idx = names.index(name)
        added = 0
        for s in songs:
            hashes = [b.md5 for b in s.beatmaps if b.md5]
            added += self.mgr.add_hashes_to_collection(idx, hashes)
        QMessageBox.information(self, "结果", f"已加入 {added} 张谱面到「{self.mgr.collections[idx].name}」。")

    def _batch_delete_checked(self):
        songs = self._checked_songs()
        if not songs:
            QMessageBox.information(self, "提示", "请先在左侧勾选要删除的歌曲。")
            return
        n_diffs = sum(len(s.beatmaps) for s in songs)
        if not self._confirm_delete("删除歌曲", f"将删除勾选的 {len(songs)} 首歌（共 {n_diffs} 个难度），移入回收站。继续？"):
            return
        self._run_worker(lambda cb: self.mgr.delete_songs(songs, use_trash=True, progress_cb=cb),
                         "删除歌曲", "正在删除歌曲…",
                         self._after_batch_delete)

    def _song_add(self, song: Song):
        names = [c.name or "(未命名)" for c in self.mgr.collections]
        if not names:
            QMessageBox.information(self, "提示", "当前没有收藏夹，请先新建。")
            return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getItem(self, "加入收藏夹", "选择收藏夹：", names, 0, False)
        if ok:
            idx = names.index(name)
            hashes = [b.md5 for b in song.beatmaps if b.md5]
            self.mgr.add_hashes_to_collection(idx, hashes)

    def _song_remove(self, song: Song):
        ci = self.viewing_collection
        if ci is None:
            return
        hashes = [b.md5 for b in song.beatmaps if b.md5]
        self.mgr.remove_hashes_from_collection(ci, hashes)
        self._reload_current_songs()

    def _song_delete(self, song: Song):
        if not self._confirm_delete("删除谱面文件", f"将删除「{song.title}」的谱面集目录（移入回收站）。继续？"):
            return
        self.mgr.delete_song(song, use_trash=True)
        self._reload_current_songs()

    def _beatmap_delete(self, b: Beatmap):
        name = b.difficulty_name or "(未命名)"
        if not self._confirm_delete("删除单个难度", f"将删除「{b.title} [{name}]」这个难度（移入回收站）。继续？"):
            return
        self.mgr.delete_beatmaps([b], use_trash=True)
        self._reload_current_songs()

    def _beatmap_add(self, b: Beatmap):
        if not b.md5:
            return
        names = [c.name or "(未命名)" for c in self.mgr.collections]
        if not names:
            QMessageBox.information(self, "提示", "当前没有收藏夹，请先新建。")
            return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getItem(self, "加入收藏夹", "选择收藏夹：", names, 0, False)
        if ok:
            idx = names.index(name)
            self.mgr.add_hashes_to_collection(idx, [b.md5])

    def _beatmap_remove(self, b: Beatmap):
        ci = self.viewing_collection
        if ci is None or not b.md5:
            return
        self.mgr.remove_hashes_from_collection(ci, [b.md5])
        self._reload_current_songs()

    def _after_batch_delete(self, res):
        self._reload_current_songs()
        QMessageBox.information(self, "结果", f"已删除 {res[0]} 个谱面集目录。")

    def _reload_current_songs(self):
        """删除/移除后刷新歌曲数据，保持当前页、滚动位置与展开状态。"""
        if self.current_page == "collections" and self.viewing_collection is not None:
            self._songs = self.mgr.songs_in_collection(self.viewing_collection)
        else:
            self._songs = self.mgr.get_songs()
        sb = self._tree.verticalScrollBar()
        pos = sb.value()

        # 记录当前展开的歌曲（folder_name 标识）
        expanded = set()
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            if item.isExpanded():
                data = item.data(0, Qt.ItemDataRole.UserRole)
                if data and data[0] == "song":
                    s = data[1]
                    expanded.add(s.folder_name or s.title)

        self._song_page(0, None, None)

        # 恢复展开状态
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == "song":
                s = data[1]
                if (s.folder_name or s.title) in expanded:
                    item.setExpanded(True)

        # setItemWidget 的行高需在事件循环完成布局后才确定，延迟恢复滚动位置
        QTimer.singleShot(0, lambda: sb.setValue(pos))

    def _run_worker(self, fn, title, msg, on_done):
        dlg = QProgressDialog(msg, "取消", 0, 0, self)
        dlg.setWindowTitle(title)
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setCancelButton(None)
        worker = Worker(fn, self)
        worker.done.connect(lambda _: (dlg.close(), on_done(_)))
        worker.error.connect(lambda e: (dlg.close(), QMessageBox.critical(self, "错误", str(e))))
        worker.start()
        dlg.show()
        # 保持 worker 引用
        self._worker = worker

    # ------------------------------------------------------------------ 设置
    def _build_settings(self, lay):
        t = QLabel("设置")
        t.setStyleSheet(f"color: {self.colors['fg']}; font-size: 22px; font-weight: 700;")
        lay.addWidget(t)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        scroll.setWidget(body)
        form = QFormLayout(body)
        form.setContentsMargins(0, 0, 12, 0)
        form.setSpacing(14)

        # osu! 目录
        dir_row = QHBoxLayout()
        self._dir_edit = QLineEdit(self.mgr.osu_dir)
        dir_row.addWidget(self._dir_edit, 1)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._browse_dir)
        apply_dir = QPushButton("应用目录")
        apply_dir.setProperty("class", "primary")
        apply_dir.setStyleSheet(f"QPushButton {{ background: {self.colors['accent']}; color: {self.colors['accent_fg']}; border: none; border-radius: 8px; padding: 8px 14px; font-weight: 600; }}")
        apply_dir.clicked.connect(self._apply_dir)
        dir_row.addWidget(browse)
        dir_row.addWidget(apply_dir)
        form.addRow("osu! 目录", dir_row)

        # 主题
        self._theme_combo = QComboBox()
        self._theme_combo.addItems(list(config.THEMES.keys()))
        self._theme_combo.setCurrentText(self.theme_name)
        self._theme_combo.currentTextChanged.connect(self._apply_theme)
        form.addRow("主题颜色", self._theme_combo)

        # 强调色
        accent_row = QHBoxLayout()
        self._accent_swatch = QPushButton()
        self._accent_swatch.setFixedSize(40, 28)
        self._accent_swatch.setStyleSheet(f"background: {self.colors['accent']}; border-radius: 6px; border: 1px solid {self.colors['border']};")
        self._accent_swatch.clicked.connect(self._pick_accent)
        pick = QPushButton("选择强调色…")
        pick.clicked.connect(self._pick_accent)
        reset = QPushButton("恢复默认")
        reset.clicked.connect(self._reset_accent)
        accent_row.addWidget(self._accent_swatch)
        accent_row.addWidget(pick)
        accent_row.addWidget(reset)
        accent_row.addStretch(1)
        form.addRow("强调色", accent_row)

        # 背景图片 + 透明度
        bg_row = QHBoxLayout()
        self._bg_edit = QLineEdit(config.load_bg_image())
        bg_row.addWidget(self._bg_edit, 1)
        pick_bg = QPushButton("选择图片…")
        pick_bg.clicked.connect(self._pick_bg)
        clear_bg = QPushButton("清除背景")
        clear_bg.clicked.connect(self._clear_bg)
        bg_row.addWidget(pick_bg)
        bg_row.addWidget(clear_bg)
        form.addRow("背景图片", bg_row)

        op_row = QHBoxLayout()
        self._op_slider = QSlider(Qt.Orientation.Horizontal)
        self._op_slider.setRange(0, 100)
        self._op_slider.setValue(config.load_bg_opacity())
        self._op_slider.setFixedWidth(240)
        self._op_label = QLabel(f"{config.load_bg_opacity()}%")
        self._op_label.setStyleSheet(f"color: {self.colors['fg']};")
        self._op_slider.valueChanged.connect(self._on_opacity)
        op_row.addWidget(self._op_slider)
        op_row.addWidget(self._op_label)
        op_row.addStretch(1)
        form.addRow("透明度", op_row)

        # 数据操作
        data_row = QHBoxLayout()
        reload = QPushButton("重新读取歌曲文件")
        reload.clicked.connect(self._reload_songs)
        fill = QPushButton("计算缺失星级")
        fill.clicked.connect(self._fill_stars)
        bulk = QPushButton("批量删除低星难度")
        bulk.setProperty("class", "danger")
        bulk.setStyleSheet("QPushButton { color: #d9534f; }")
        bulk.clicked.connect(self._bulk_delete_low_star)
        imp = QPushButton("导入 .osz 文件")
        imp.clicked.connect(self._import_osz)
        data_row.addWidget(reload)
        data_row.addWidget(fill)
        data_row.addWidget(bulk)
        data_row.addWidget(imp)
        data_row.addStretch(1)
        form.addRow("数据", data_row)

        # 确认
        self._confirm_check = QCheckBox("删除前弹出确认")
        self._confirm_check.setChecked(config.load_confirm_delete())
        self._confirm_check.toggled.connect(lambda v: config.save_confirm_delete(v))
        form.addRow("确认", self._confirm_check)

        lay.addWidget(scroll, 1)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择 osu! 安装目录")
        if d:
            self._dir_edit.setText(d)

    def _apply_dir(self):
        d = self._dir_edit.text().strip()
        if not config.is_osu_dir(d):
            QMessageBox.critical(self, "错误", "所选目录不是有效的 osu! 目录（缺少 collection.db / osu!.db）")
            return
        self.mgr = OsuManager(d)
        self.mgr.load()
        config.save_osu_dir(d)
        self.show_page("home")

    def _apply_theme(self, name):
        config.save_theme(name)
        self.theme_name = name
        self.colors = config.get_theme_colors(name)
        self._reload_bg()
        self._apply_styles()

    def _pick_accent(self):
        col = QColorDialog.getColor(_qcolor(self.colors.get("accent", "#ff5c8a")), self, "选择强调色")
        if col.isValid():
            config.save_accent(col.name())
            self.colors = config.get_theme_colors(self.theme_name)
            self._apply_styles()

    def _reset_accent(self):
        config.save_accent("")
        self.colors = config.get_theme_colors(self.theme_name)
        self._apply_styles()

    def _pick_bg(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择背景图片", "", "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif)")
        if path:
            config.save_bg_image(path)
            self._bg_edit.setText(path)
            self._reload_bg()
            self.update()

    def _clear_bg(self):
        config.save_bg_image("")
        self._bg_edit.setText("")
        self._reload_bg()
        self.update()

    def _on_opacity(self, v):
        self._op_label.setText(f"{v}%")
        config.save_bg_opacity(v)
        self._bg_opacity = max(0.0, min(1.0, v / 100.0))
        self.update()

    def _reload_songs(self):
        self.mgr.load()
        self.show_page("home")

    def _fill_stars(self):
        if not diffcalc.is_available():
            QMessageBox.warning(self, "提示", "未安装 rosu-pp-py，无法本地计算星级。")
            return
        missing = sum(1 for b in self.mgr.beatmaps if b.star_rating == 0)
        if missing == 0:
            QMessageBox.information(self, "完成", "当前没有缺失星级的谱面。")
            return
        if QMessageBox.question(self, "计算星级", f"将为 {missing} 个缺失星级的谱面本地计算星级。继续？") != QMessageBox.StandardButton.Yes:
            return
        self._run_worker(lambda cb: self.mgr.fill_missing_stars(progress_cb=cb),
                         "计算星级", "正在本地计算缺失星级…",
                         lambda res: QMessageBox.information(self, "结果", f"已计算 {res[0]} 个，{res[1]} 个无法计算。"))

    def _bulk_delete_low_star(self):
        from PySide6.QtWidgets import QInputDialog
        v, ok = QInputDialog.getDouble(self, "批量删除低星难度", "删除星级低于多少的难度？", 2.0, 0.0, 100.0, 1)
        if not ok:
            return
        targets = [b for b in self.mgr.beatmaps if b.star_rating < v]
        if not targets:
            QMessageBox.information(self, "结果", "没有符合条件的低星难度。")
            return
        if not self._confirm_delete("批量删除低星难度", f"将删除 {len(targets)} 个星级低于 {v} 的难度（移入回收站）。继续？"):
            return
        self._run_worker(lambda cb: self.mgr.delete_beatmaps(targets, use_trash=True, progress_cb=cb),
                         "删除低星难度", "正在移入回收站…",
                         lambda res: QMessageBox.information(self, "结果", f"已删除 {res[0]} 个难度。"))

    def _import_osz(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "选择 .osz 文件", "", "osu! 谱面包 (*.osz)")
        if not paths:
            return
        add = QMessageBox.question(self, "导入", "是否将导入的谱面加入某个收藏夹？") == QMessageBox.StandardButton.Yes
        ci = None
        if add:
            names = [c.name or "(未命名)" for c in self.mgr.collections]
            if names:
                from PySide6.QtWidgets import QInputDialog
                name, ok = QInputDialog.getItem(self, "选择收藏夹", "选择收藏夹：", names, 0, False)
                if ok:
                    ci = names.index(name)
        total, failed = self.mgr.import_osz(list(paths), ci)
        QMessageBox.information(self, "结果", f"已导入 {total} 个难度。")
        self._reload_songs()


class _AutoCategorizeDialog(QDialog):
    def __init__(self, parent, mgr: OsuManager):
        super().__init__(parent)
        self.mgr = mgr
        self.setWindowTitle("自动分类")
        lay = QVBoxLayout(self)
        self._mode = QComboBox()
        self._mode.addItems(["按艺术家", "按星级"])
        lay.addWidget(QLabel("分类方式："))
        lay.addWidget(self._mode)

        form = QFormLayout()
        self._min = QLineEdit("1")
        self._th = QLineEdit("2,4,6,8")
        form.addRow("最小谱面数(仅艺术家)", self._min)
        form.addRow("星级阈值(仅星级)", self._th)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._run)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _run(self):
        try:
            if self._mode.currentText() == "按艺术家":
                min_songs = int(self._min.text().strip() or "1")
                summary = self.mgr.categorize_by_artist(min_songs=min_songs)
            else:
                th = _parse_thresholds(self._th.text())
                if not th:
                    QMessageBox.critical(self, "错误", "星级阈值格式无效。")
                    return
                summary = self.mgr.categorize_by_star(th)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "错误", f"分类失败：{e}")
            return
        self.accept()
        total = sum(summary.values())
        QMessageBox.information(self, "分类完成", f"共创建/更新 {len(summary)} 个收藏夹，新增 {total} 张谱面。")


class _ReorganizeDialog(QDialog):
    def __init__(self, parent, mgr: OsuManager):
        super().__init__(parent)
        self.mgr = mgr
        self.setWindowTitle("重新整理收藏夹")
        self.setMinimumWidth(360)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel("将清空全部收藏夹，按艺术家重新创建（优先著名、歌曲多的艺术家）。\n（仅影响收藏夹，不删除谱面文件；osu 显示上限约 250）"))

        form = QFormLayout()
        self._target = QLineEdit("200")
        self._min = QLineEdit("1")
        self._bpm_min = QLineEdit("")
        self._bpm_max = QLineEdit("")
        self._star_min = QLineEdit("")
        self._star_max = QLineEdit("")
        self._mode = QComboBox()
        self._mode.addItems(MODE_FILTERS)
        form.addRow("目标收藏夹数量", self._target)
        form.addRow("最小谱面数", self._min)

        bpm = QHBoxLayout()
        bpm.addWidget(self._bpm_min)
        bpm.addWidget(QLabel("~"))
        bpm.addWidget(self._bpm_max)
        form.addRow("BPM 范围(可选)", bpm)

        star = QHBoxLayout()
        star.addWidget(self._star_min)
        star.addWidget(QLabel("~"))
        star.addWidget(self._star_max)
        form.addRow("星级范围(可选)", star)

        form.addRow("模式(可选)", self._mode)
        lay.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self._run)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _num(self, text):
        s = text.strip()
        return float(s) if s else None

    def _run(self):
        try:
            target = int(self._target.text().strip() or "200")
            min_songs = int(self._min.text().strip() or "1")
            bpm_min = self._num(self._bpm_min.text())
            bpm_max = self._num(self._bpm_max.text())
            star_min = self._num(self._star_min.text())
            star_max = self._num(self._star_max.text())
        except ValueError:
            QMessageBox.critical(self, "错误", "输入有误：数字格式无效。")
            return
        criteria = FilterCriteria(bpm_min=bpm_min, bpm_max=bpm_max, star_min=star_min, star_max=star_max,
                                  mode=MODE_MAP.get(self._mode.currentText()))
        if QMessageBox.question(self, "确认", f"将清空全部 {len(self.mgr.collections)} 个收藏夹并重新整理。继续？") != QMessageBox.StandardButton.Yes:
            return
        summary = self.mgr.reorganize_collections(target_count=target, min_songs=min_songs, criteria=criteria)
        self.accept()
        QMessageBox.information(self, "完成", f"已整理为 {len(summary)} 个收藏夹，共 {sum(summary.values())} 张谱面。")


def run(osu_dir: str):
    app = QApplication.instance() or QApplication([])
    app.setFont(QFont(_FONT_FAMILY, 10))
    win = MainWindow(osu_dir)
    win.show()
    return app, win
