"""Application window composition for the osu! beatmap manager."""
from __future__ import annotations

from PySide6.QtWidgets import QWidget
from ui.pages.shared import (
    OrderedDict,
    OsuManager,
    QApplication,
    QFont,
    QImage,
    Song,
    _FONT_FAMILY,
    config,
)
from ui.pages.shell import ShellMixin
from ui.pages.collections import CollectionsMixin
from ui.pages.library import LibraryMixin
from ui.pages.settings import SettingsMixin


class MainWindow(ShellMixin, CollectionsMixin, LibraryMixin, SettingsMixin, QWidget):
    """App shell and shared state; screen behavior lives in focused page modules."""

    def __init__(self, osu_dir: str):
        QWidget.__init__(self)
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
        self._checked_song_keys: set[str] = set()          # 跨页勾选的歌曲（folder_name 或 title 标识）
        self._checked_collection_ids: set[int] = set()  # 用对象身份保留跨页勾选，避免删减后索引漂移
        self._checked_collection_refs: dict[int, object] = {}  # 保持对象存活，避免 id 重用
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
        self.resize(1360, 880)
        self.setMinimumSize(980, 660)

        self._build_ui()
        self.show_page("home")

def run(osu_dir: str):
    app = QApplication.instance() or QApplication([])
    app.setFont(QFont(_FONT_FAMILY, 10))
    win = MainWindow(osu_dir)
    win.show()
    return app, win
