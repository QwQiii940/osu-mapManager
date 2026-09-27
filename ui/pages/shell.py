"""Shell page controller methods."""
from __future__ import annotations

from .shared import (
    PageHeading,
    QFrame,
    QHBoxLayout,
    QImage,
    QLabel,
    QPainter,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
    Qt,
    SurfaceCard,
    _FONT_FAMILY,
    _qcolor,
    config,
    os,
    stylesheet,
)


class ShellMixin:
    """Coordinates the shell screen while reusing the shared app state."""

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

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(14)

        content = QHBoxLayout()
        content.setSpacing(14)

        # 侧边栏
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(224)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(18, 24, 18, 20)
        side.setSpacing(7)

        brand = QLabel("osu!")
        brand.setObjectName("brand")
        side.addWidget(brand)

        subtitle = QLabel("谱面管理 · Beatmap Manager")
        subtitle.setObjectName("sidebarSubtitle")
        side.addWidget(subtitle)
        side.addSpacing(10)
        group_label = QLabel("LIBRARY")
        group_label.setObjectName("eyebrow")
        side.addWidget(group_label)
        side.addSpacing(4)

        self.nav_buttons: dict[str, QPushButton] = {}
        for key, label in [("home", "⌂   首页"), ("collections", "♡   收藏夹"),
                           ("songs", "♫   全部歌曲"), ("settings", "⚙   设置")]:
            b = QPushButton(label)
            b.setObjectName("navBtn")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, k=key: self.show_page(k))
            side.addWidget(b)
            self.nav_buttons[key] = b

        side.addStretch(1)
        foot = QLabel("LOCAL LIBRARY\n数据均在本地处理")
        foot.setObjectName("sidebarFoot")
        foot.setWordWrap(True)
        side.addWidget(foot)

        # 页面堆叠
        self.stack = QStackedWidget()
        self.pages: dict[str, QWidget] = {}
        for key in ("home", "collections", "songs", "settings"):
            page = QWidget()
            page.setObjectName("page")
            lay = QVBoxLayout(page)
            lay.setContentsMargins(8, 8, 8, 8)
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
        bar = QFrame()
        bar.setObjectName("playerBar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 8, 16, 8)
        lay.setSpacing(10)

        self._btn_play = QPushButton("播放")
        self._btn_play.setProperty("class", "primary")
        self._btn_play.setFixedSize(76, 34)
        self._btn_play.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_play.clicked.connect(self._toggle_pause)
        lay.addWidget(self._btn_play)

        self._btn_stop = QPushButton("停止")
        self._btn_stop.setFixedSize(76, 34)
        self._btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_stop.clicked.connect(self._stop_audio)
        lay.addWidget(self._btn_stop)

        self._now_title = QLabel("未播放")
        self._now_title.setObjectName("playerTitle")
        self._now_title.setFixedWidth(220)
        self._now_title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self._now_title)

        self._time_cur = QLabel("0:00")
        self._time_cur.setObjectName("playerTime")
        lay.addWidget(self._time_cur)

        self._seek = QSlider(Qt.Orientation.Horizontal)
        self._seek.setRange(0, 0)
        self._seek.setEnabled(False)
        self._seek.sliderPressed.connect(self._on_seek_press)
        self._seek.sliderReleased.connect(self._on_seek_release)
        lay.addWidget(self._seek, 1)

        self._time_total = QLabel("0:00")
        self._time_total.setObjectName("playerTime")
        lay.addWidget(self._time_total)

        return bar

    def _apply_styles(self):
        self.setStyleSheet(stylesheet(self.colors, _FONT_FAMILY))

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                self._clear_layout(item.layout())

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

    def _build_home(self, lay):
        songs = self.mgr.get_songs()
        lay.addWidget(PageHeading("谱面管理", "管理谱面、整理收藏夹，快速找到下一首想玩的歌。"))
        lay.addSpacing(8)

        stats = [("谱面集", len(songs)), ("难度", len(self.mgr.beatmaps)), ("收藏夹", len(self.mgr.collections))]
        grid = QHBoxLayout()
        grid.setSpacing(12)
        for t, v in stats:
            card = SurfaceCard(margins=(22, 20, 22, 20), spacing=8)
            cl = card.content
            num = QLabel(str(v))
            num.setStyleSheet(f"color: {self.colors['accent']}; font-size: 30px; font-weight: 800;")
            lbl = QLabel(t)
            lbl.setStyleSheet(f"color: {self.colors['muted']}; font-size: 12px;")
            cl.addWidget(num)
            cl.addWidget(lbl)
            grid.addWidget(card, 1)
        lay.addLayout(grid)
        lay.addSpacing(14)

        dcard = SurfaceCard(margins=(20, 16, 20, 16), spacing=8)
        dl = dcard.content
        library_label = QLabel("LOCAL LIBRARY  ·  osu! stable")
        library_label.setObjectName("eyebrow")
        dl.addWidget(library_label)
        location = QLabel(self.mgr.osu_dir)
        location.setStyleSheet(f"color: {self.colors['fg']}; font-size: 13px;")
        location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        dl.addWidget(location)
        lay.addWidget(dcard)
        lay.addSpacing(16)

        lay.addWidget(PageHeading("快速访问", "从常用任务继续整理你的谱面库。", "QUICK ACCESS"))
        action_grid = QHBoxLayout()
        action_grid.setSpacing(12)
        actions = [
            ("01", "全部歌曲", "搜索、筛选难度，并进行批量整理。", "songs"),
            ("02", "收藏夹", "整理曲包，合并、导出或重新分类。", "collections"),
            ("03", "库设置", "扫描 osu! 目录并管理本地偏好。", "settings"),
        ]
        for number, title, description, page in actions:
            card = SurfaceCard(margins=(18, 16, 18, 16), spacing=8)
            index_label = QLabel(number)
            index_label.setStyleSheet(f"color: {self.colors['accent']}; font-size: 11px; font-weight: 800;")
            title_label = QLabel(title)
            title_label.setStyleSheet("font-size: 16px; font-weight: 700;")
            detail = QLabel(description)
            detail.setStyleSheet(f"color: {self.colors['muted']}; font-size: 12px;")
            detail.setWordWrap(True)
            action = QPushButton("打开页面  ›")
            action.setProperty("class", "secondary")
            action.setCursor(Qt.CursorShape.PointingHandCursor)
            action.clicked.connect(lambda _=False, p=page: self.show_page(p))
            card.content.addWidget(index_label)
            card.content.addWidget(title_label)
            card.content.addWidget(detail, 1)
            card.content.addWidget(action)
            action_grid.addWidget(card, 1)
        lay.addLayout(action_grid)
        lay.addStretch(1)
