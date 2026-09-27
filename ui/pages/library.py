"""Library page controller methods."""
from __future__ import annotations

from .shared import (
    Beatmap,
    CLASSIFY_MODES,
    DIFF_RANGES,
    ElidedLabel,
    FlowLayout,
    MODE_FILTERS,
    PAGE_SIZE,
    PageHeading,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QPixmap,
    QProgressDialog,
    QPushButton,
    QSize,
    QTimer,
    QStringListModel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
    Qt,
    Song,
    SquareCheckBox,
    SurfaceCard,
    Worker,
    _apply_advanced_filter,
    _categories,
    _filter_beatmaps_by_filters,
    _filter_songs_by_filters,
    _filter_songs_impl,
    _fmt_filter,
    _parse_float,
    _qcolor,
    math,
    os,
)


class LibraryMixin:
    """Coordinates the library screen while reusing the shared app state."""

    def _view_state(self, show_remove: bool) -> dict:
        key = "collection" if show_remove else "songs"
        st = self._view_states.setdefault(key, {
            "mode": "全部", "category": None, "search": "", "page": 0,
            "letter": "", "artist": "", "len_min": None, "len_max": None,
            "star_min": None, "star_max": None, "game_mode": "全部",
            "difficulty": "", **{f"{field}_{edge}": None for field in ("ar", "od", "cs", "hp", "bpm") for edge in ("min", "max")},
        })
        return st

    def _filtered_songs(self, songs: list[Song], st: dict) -> list[Song]:
        out = _filter_songs_impl(songs, st["mode"], st["category"], st["search"])
        out = _apply_advanced_filter(
            out, st["letter"], st["artist"], None, None,
            st["star_min"], st["star_max"],
        )
        return _filter_songs_by_filters(out, self._effective_map_filters(st))

    def _effective_map_filters(self, st: dict) -> dict:
        """把星级分类也落实到难度行和批量操作的目标集合。"""
        filters = dict(st)
        if st.get("mode") == "按难度(星级)" and st.get("category"):
            for low, high, label in DIFF_RANGES:
                if label == st["category"]:
                    filters["star_min"] = max(
                        low, st["star_min"] if st.get("star_min") is not None else low
                    )
                    if high is not None:
                        upper = math.nextafter(high, float("-inf"))
                        filters["star_max"] = min(
                            upper, st["star_max"] if st.get("star_max") is not None else upper
                        )
                    break
        return filters

    def _build_song_browser(self, lay, songs: list[Song], title: str, show_remove: bool):
        old_timer = getattr(self, "_song_search_timer", None)
        if old_timer is not None:
            old_timer.stop()
            old_timer.deleteLater()
        self._songs = songs
        self._show_remove = show_remove
        st = self._view_state(show_remove)

        head = QHBoxLayout()
        if show_remove:
            back = QPushButton("← 返回")
            back.clicked.connect(self._back_to_collections)
            head.addWidget(back)
        count_text = f"{len(songs):,} 首歌曲" if not show_remove else f"{len(songs):,} 首歌曲 · 收藏夹内容"
        head.addWidget(PageHeading(title, count_text), 1)
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
        self._song_search_edit = search
        search.setPlaceholderText("搜索 标题/艺术家/创作者…")
        search.setFixedWidth(240)
        head.addWidget(search)

        combo = QComboBox()
        combo.addItems(CLASSIFY_MODES)
        combo.setCurrentText(st["mode"])
        self._song_classify_combo = combo
        head.addWidget(combo)
        lay.addLayout(head)

        selection_panel = SurfaceCard(margins=(14, 8, 14, 8), spacing=0)
        select_bar = QHBoxLayout()
        select_bar.setContentsMargins(0, 0, 0, 0)
        select_hint = QLabel("选择当前筛选结果")
        select_hint.setStyleSheet(f"color: {self.colors['muted']}; font-size: 12px;")
        self._song_selection_hint = select_hint
        select_bar.addWidget(select_hint)
        select_bar.addStretch(1)
        sel_all_btn = QPushButton("全选")
        sel_all_btn.setProperty("class", "secondary")
        sel_all_btn.clicked.connect(lambda: self._set_all_songs_checked(True))
        sel_none_btn = QPushButton("取消")
        sel_none_btn.clicked.connect(lambda: self._set_all_songs_checked(False))
        select_bar.addWidget(sel_all_btn)
        select_bar.addWidget(sel_none_btn)
        if not show_remove:
            move_btn = QPushButton("加入收藏夹")
            move_btn.setProperty("class", "primary")
            move_btn.clicked.connect(self._batch_add_checked)
            del_btn = QPushButton("删除勾选")
            del_btn.setProperty("class", "danger")
            del_btn.clicked.connect(self._batch_delete_checked)
            select_bar.addWidget(move_btn)
            select_bar.addWidget(del_btn)
        selection_panel.content.addLayout(select_bar)
        lay.addWidget(selection_panel)

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

        self._extra_filter_inputs = {}
        for field, label in (("ar", "AR"), ("od", "OD"), ("cs", "CS"), ("hp", "HP"), ("bpm", "BPM")):
            low = QLineEdit(_fmt_filter(st.get(f"{field}_min")))
            high = QLineEdit(_fmt_filter(st.get(f"{field}_max")))
            low.setFixedWidth(48)
            high.setFixedWidth(48)
            low.setPlaceholderText("最小")
            high.setPlaceholderText("最大")
            self._extra_filter_inputs[f"{field}_min"] = low
            self._extra_filter_inputs[f"{field}_max"] = high
            fbar.addWidget(group(QLabel(label), low, QLabel("~"), high))
        self._e_difficulty = QLineEdit(st.get("difficulty", ""))
        self._e_difficulty.setPlaceholderText("难度名")
        self._e_difficulty.setFixedWidth(130)
        fbar.addWidget(group(QLabel("难度"), self._e_difficulty))

        apply_btn = QPushButton("应用")
        apply_btn.setProperty("class", "primary")
        apply_btn.clicked.connect(lambda: self._apply_filter(search, combo))
        reset_btn = QPushButton("重置")
        reset_btn.clicked.connect(lambda: self._reset_filter(search, combo))
        fbar.addWidget(apply_btn)
        fbar.addWidget(reset_btn)
        filter_panel = SurfaceCard(margins=(14, 10, 14, 10), spacing=0)
        filter_panel.content.addLayout(fbar)
        lay.addWidget(filter_panel)

        # 分类列表 + 歌曲树
        body = QHBoxLayout()
        body.setSpacing(10)
        self._cat_list = QListView()
        self._cat_list.setFixedWidth(170)
        self._cat_list.setUniformItemSizes(True)
        self._cat_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._category_model = QStringListModel(self._cat_list)
        self._cat_list.setModel(self._category_model)
        self._cat_list.clicked.connect(lambda _: self._on_cat_select(combo))
        body.addWidget(self._cat_list)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(4)
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(True)
        self._tree.setIndentation(14)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._song_context_menu)
        self._tree.itemExpanded.connect(self._populate_expanded_beatmaps)
        self._tree.header().setStretchLastSection(False)
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self._tree.setColumnWidth(0, 36)  # 展开难度
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._tree.setColumnWidth(1, 54)  # 批量选择，留足整格点击区域
        self._tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self._tree.setColumnWidth(3, 216)
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

        self._song_search_timer = QTimer(self)
        self._song_search_timer.setSingleShot(True)
        self._song_search_timer.setInterval(180)
        self._song_search_timer.timeout.connect(
            lambda search=search, combo=combo: self._song_page(0, search, combo)
        )
        search.textChanged.connect(lambda _: self._song_search_timer.start())
        search.returnPressed.connect(lambda: (self._song_search_timer.stop(), self._song_page(0, search, combo)))
        combo.currentTextChanged.connect(lambda _: self._song_page(0, search, combo))
        self._refresh_categories()
        self._song_page(0, search, combo)

    def _refresh_categories(self):
        st = self._view_state(self._show_remove)
        cats = _categories(self._songs, st["mode"])
        self._category_values = cats
        self._category_model.setStringList(cats)
        if st.get("category"):
            try:
                index = cats.index(st["category"])
                self._cat_list.setCurrentIndex(self._category_model.index(index, 0))
            except ValueError:
                pass
        self._cat_list.setVisible(st["mode"] != "全部")

    def _on_cat_select(self, combo):
        st = self._view_state(self._show_remove)
        st["category"] = self._cat_list.currentIndex().data() or None
        st["page"] = 0
        self._song_page(0, getattr(self, "_song_search_edit", None), combo)

    def _apply_filter(self, search, combo):
        st = self._view_state(self._show_remove)
        st["letter"] = self._e_letter.text().strip()
        st["artist"] = self._e_artist.text().strip()
        st["len_min"] = _parse_float(self._e_len_min.text())
        st["len_max"] = _parse_float(self._e_len_max.text())
        st["star_min"] = _parse_float(self._e_star_min.text())
        st["star_max"] = _parse_float(self._e_star_max.text())
        st["game_mode"] = self._mode_combo.currentText()
        for key, edit in self._extra_filter_inputs.items():
            st[key] = _parse_float(edit.text())
        st["difficulty"] = self._e_difficulty.text().strip()
        st["page"] = 0
        self._song_page(0, search, combo)

    def _reset_filter(self, search, combo):
        st = self._view_state(self._show_remove)
        for k in ("letter", "artist", "len_min", "len_max", "star_min", "star_max",
                  *self._extra_filter_inputs):
            st[k] = "" if k in ("letter", "artist") else None
        st["difficulty"] = ""
        st["game_mode"] = "全部"
        self._e_letter.setText("")
        self._e_artist.setText("")
        self._e_len_min.setText("")
        self._e_len_max.setText("")
        self._e_star_min.setText("")
        self._e_star_max.setText("")
        self._e_difficulty.setText("")
        for edit in self._extra_filter_inputs.values():
            edit.setText("")
        self._mode_combo.setCurrentText("全部")
        st["page"] = 0
        self._song_page(0, search, combo)

    def _song_page(self, delta, search, combo):
        timer = getattr(self, "_song_search_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
        st = self._view_state(self._show_remove)
        if search is not None:
            query = search.text().strip()
            if query != st["search"]:
                st["page"] = 0
            st["search"] = query
        if combo is not None:
            mode = combo.currentText()
            if mode != st["mode"]:
                st["mode"] = mode
                st["category"] = None
                st["page"] = 0
                self._refresh_categories()
        st["page"] = max(0, st["page"] + delta)
        result = self._filtered_songs(self._songs, st)
        self._current_filter_result = result
        total = len(result)
        pages = max(1, math.ceil(total / PAGE_SIZE))
        if st["page"] >= pages:
            st["page"] = pages - 1
        start = st["page"] * PAGE_SIZE
        page = result[start:start + PAGE_SIZE]
        self._song_render_generation = getattr(self, "_song_render_generation", 0) + 1
        render_generation = self._song_render_generation

        # 重建期间暂停重绘，避免逐条 addItem/setItemWidget 触发多次布局与绘制
        self._tree.setUpdatesEnabled(False)
        self._tree.clear()
        for s in page:
            # 标题由歌曲信息控件统一绘制，树项单元格保持空白，避免异步挂载控件前后的文字重影。
            parent = QTreeWidgetItem(["", "", "", ""])
            parent.setData(0, Qt.ItemDataRole.UserRole, ("song", s))
            parent.setSizeHint(1, QSize(54, 76))

            visible_beatmaps = _filter_beatmaps_by_filters(
                s.beatmaps, self._effective_map_filters(st)
            )
            for b in visible_beatmaps:
                child = QTreeWidgetItem(["", "", "", ""])
                child.setData(0, Qt.ItemDataRole.UserRole, ("beatmap", b))
                child.setSizeHint(1, QSize(54, 50))
                parent.addChild(child)

            self._tree.addTopLevelItem(parent)

        self._tree.setUpdatesEnabled(True)
        QTimer.singleShot(0, lambda: self._populate_song_rows(render_generation, page, 0))
        self._slabel.setText(f"第 {st['page'] + 1} / {pages} 页 · 共 {total} 首")
        self._sprev.setEnabled(st["page"] > 0)
        self._snext.setEnabled(st["page"] < pages - 1)
        if hasattr(self, "_song_selection_hint"):
            selected = sum(self._song_key(song) in self._checked_song_keys for song in result)
            self._song_selection_hint.setText(f"当前结果已选 {selected} / {total} 首")

    def _populate_song_rows(self, generation: int, songs: list[Song], offset: int):
        """分批挂载歌曲行控件，让筛选和页面切换期间事件循环持续响应。"""
        if generation != getattr(self, "_song_render_generation", -1):
            return
        end = min(offset + 6, len(songs))
        for index in range(offset, end):
            song = songs[index]
            parent = self._tree.topLevelItem(index)
            if parent is None:
                continue
            key = self._song_key(song)
            checkbox = SquareCheckBox(self.colors)
            checkbox.setAccessibleName(f"选择歌曲：{song.title or '(未知标题)'}")
            checkbox.setChecked(key in self._checked_song_keys)
            checkbox.toggled.connect(lambda checked, k=key: self._toggle_song_checked(k, checked))
            self._tree.setItemWidget(parent, 1, checkbox)
            self._tree.setItemWidget(parent, 2, self._song_info_widget(song))
            self._tree.setItemWidget(parent, 3, self._song_actions_widget(song))
        if end < len(songs):
            QTimer.singleShot(8, lambda: self._populate_song_rows(generation, songs, end))

    def _populate_expanded_beatmaps(self, parent):
        """只在歌曲行展开时创建难度控件，减少首次渲染和筛选时的控件数量。"""
        if parent.data(0, Qt.ItemDataRole.UserRole + 1):
            return
        parent.setData(0, Qt.ItemDataRole.UserRole + 1, True)
        for i in range(parent.childCount()):
            child = parent.child(i)
            data = child.data(0, Qt.ItemDataRole.UserRole)
            if not data or data[0] != "beatmap":
                continue
            beatmap = data[1]
            self._tree.setItemWidget(child, 2, self._beatmap_info_widget(beatmap))
            self._tree.setItemWidget(child, 3, self._beatmap_actions_widget(beatmap))

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
            self._audio_out.setVolume(1.0)
            self._player.positionChanged.connect(self._on_position)
            self._player.durationChanged.connect(self._on_duration)
            self._player.playbackStateChanged.connect(self._on_state)
            self._player.errorOccurred.connect(self._on_audio_error)
        return self._player

    def _toggle_audio(self, song: Song):
        path = self.mgr.find_song_audio(song.folder_name)
        if not path or not os.path.isfile(path):
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

    def _on_audio_error(self, error, message: str):
        from PySide6.QtMultimedia import QMediaPlayer
        if error == QMediaPlayer.Error.NoError:
            return
        detail = message or "音频解码器或输出设备不可用。"
        self._now_title.setText("播放失败")
        self._btn_play.setText("播放")
        QMessageBox.warning(self, "无法播放歌曲", detail)

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
        h.setContentsMargins(8, 4, 10, 4)
        h.setSpacing(8)
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self._show_remove:
            b_rm = QPushButton("移除")
            b_rm.setProperty("class", "secondary")
            b_rm.setFixedWidth(78)
            b_rm.setFixedHeight(34)
            b_rm.setCursor(Qt.CursorShape.PointingHandCursor)
            b_rm.clicked.connect(lambda _=False, s=song: self._song_remove(s))
            h.addWidget(b_rm)
        else:
            b_add = QPushButton("收藏")
            b_add.setProperty("class", "secondary")
            b_add.setFixedWidth(78)
            b_add.setFixedHeight(34)
            b_add.setCursor(Qt.CursorShape.PointingHandCursor)
            b_add.clicked.connect(lambda _=False, s=song: self._song_add(s))
            h.addWidget(b_add)
        b_del = QPushButton("删除")
        b_del.setProperty("class", "danger")
        b_del.setFixedWidth(78)
        b_del.setFixedHeight(34)
        b_del.setCursor(Qt.CursorShape.PointingHandCursor)
        b_del.clicked.connect(lambda _=False, s=song: self._song_delete(s))
        h.addWidget(b_del)
        return w

    def _beatmap_actions_widget(self, b: Beatmap) -> QWidget:
        """难度行右侧的操作按钮：加入/移出收藏夹 + 删除该难度。"""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(8, 2, 10, 2)
        h.setSpacing(8)
        h.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self._show_remove:
            b_rm = QPushButton("移除")
            b_rm.setProperty("class", "secondary")
            b_rm.setFixedWidth(78)
            b_rm.setFixedHeight(32)
            b_rm.setCursor(Qt.CursorShape.PointingHandCursor)
            b_rm.clicked.connect(lambda _=False, bm=b: self._beatmap_remove(bm))
            h.addWidget(b_rm)
        else:
            b_add = QPushButton("收藏")
            b_add.setProperty("class", "secondary")
            b_add.setFixedWidth(78)
            b_add.setFixedHeight(32)
            b_add.setCursor(Qt.CursorShape.PointingHandCursor)
            b_add.clicked.connect(lambda _=False, bm=b: self._beatmap_add(bm))
            h.addWidget(b_add)
        b_del = QPushButton("删除")
        b_del.setProperty("class", "danger")
        b_del.setFixedWidth(78)
        b_del.setFixedHeight(32)
        b_del.setCursor(Qt.CursorShape.PointingHandCursor)
        b_del.clicked.connect(lambda _=False, bm=b: self._beatmap_delete(bm))
        h.addWidget(b_del)
        return w

    def _song_info_widget(self, s: Song) -> QWidget:
        """歌曲行信息使用固定两层：标题/试听一行，艺术家与谱面数据一行。"""
        c = self.colors
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(6, 4, 6, 4)
        h.setSpacing(10)
        h.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        thumb = QLabel()
        thumb.setPixmap(self._song_icon(s))
        thumb.setFixedSize(54, 54)
        h.addWidget(thumb)

        v = QVBoxLayout()
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        tr = QHBoxLayout()
        tr.setContentsMargins(0, 0, 0, 0)
        tr.setSpacing(8)
        title = ElidedLabel(s.title or "(无标题)")
        title.setStyleSheet(f"color: {c['fg']}; font-size: 14px; font-weight: 600;")
        title.setFixedHeight(22)
        play = QPushButton("试听")
        play.setObjectName("playBtn")
        play.setFixedSize(48, 28)
        play.setCursor(Qt.CursorShape.PointingHandCursor)
        play.setToolTip("播放/暂停音频")
        play.clicked.connect(lambda _=False, sng=s: self._toggle_audio(sng))
        tr.addWidget(title, 1)
        tr.addWidget(play)
        v.addLayout(tr)

        info = ElidedLabel(self._song_info_text(s))
        info.setStyleSheet(f"color: {c['muted']}; font-size: 12px;")
        info.setFixedHeight(18)
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

        name = ElidedLabel(b.difficulty_name or "(未命名)")
        name.setStyleSheet(f"color: {c['fg']}; font-size: 13px;")
        h.addWidget(name, 1)

        info = ElidedLabel(f"{b.mode_name} · ★ {b.star_rating:.2f} · AR{b.ar:.1f} OD{b.od:.1f} CS{b.cs:.1f} HP{b.hp:.1f} BPM{bpm}")
        info.setStyleSheet(f"color: {c['muted']}; font-size: 11px;")
        h.addWidget(info, 2)
        return w

    def _song_info_text(self, s: Song) -> str:
        artist = s.artist or "(未知艺术家)"
        return f"{artist}  ·  ★ {self._star_text(s)}  ·  {self._stat_text(s)}"

    def _song_key(self, s: Song) -> str:
        return s.folder_name or s.title or ""

    def _toggle_song_checked(self, key: str, checked: bool):
        if checked:
            self._checked_song_keys.add(key)
        else:
            self._checked_song_keys.discard(key)
        self._update_song_selection_hint()

    def _update_song_selection_hint(self):
        hint = getattr(self, "_song_selection_hint", None)
        if hint is None:
            return
        st = self._view_state(self._show_remove)
        result = getattr(self, "_current_filter_result", None)
        if result is None:
            result = self._filtered_songs(self._songs, st)
        selected = sum(self._song_key(song) in self._checked_song_keys for song in result)
        hint.setText(f"当前结果已选 {selected} / {len(result)} 首")

    def _set_all_songs_checked(self, checked: bool):
        """全选/取消当前筛选结果的所有歌曲（跨页）。"""
        self._flush_song_search()
        st = self._view_state(self._show_remove)
        result = getattr(self, "_current_filter_result", None)
        if result is None:
            result = self._filtered_songs(self._songs, st)
        keys = {self._song_key(s) for s in result}
        if checked:
            self._checked_song_keys |= keys
        else:
            self._checked_song_keys -= keys
        # 就地刷新当前页复选框显示
        for i in range(self._tree.topLevelItemCount()):
            item = self._tree.topLevelItem(i)
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and data[0] == "song":
                cb = self._tree.itemWidget(item, 1)
                if isinstance(cb, QCheckBox):
                    cb.blockSignals(True)
                    cb.setChecked(self._song_key(data[1]) in self._checked_song_keys)
                    cb.blockSignals(False)
        self._update_song_selection_hint()

    def _checked_songs(self) -> list[Song]:
        self._flush_song_search()
        result = getattr(self, "_current_filter_result", None)
        if result is None:
            st = self._view_state(self._show_remove)
            result = self._filtered_songs(self._songs, st)
        return [s for s in result if self._song_key(s) in self._checked_song_keys]

    def _flush_song_search(self):
        timer = getattr(self, "_song_search_timer", None)
        if timer is not None and timer.isActive():
            timer.stop()
            search = getattr(self, "_song_search_edit", None)
            combo = getattr(self, "_song_classify_combo", None)
            self._song_page(0, search, combo)

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
        st = self._view_state(self._show_remove)
        map_filters = self._effective_map_filters(st)
        targets = [b for song in songs for b in _filter_beatmaps_by_filters(song.beatmaps, map_filters)]
        if not targets:
            QMessageBox.information(self, "提示", "勾选的歌曲中没有符合当前筛选条件的难度。")
            return

        limited_by_difficulty = (
            map_filters.get("game_mode", "全部") != "全部"
            or bool(map_filters.get("difficulty", "").strip())
            or any(map_filters.get(key) is not None for key in (
                "star_min", "star_max", "ar_min", "ar_max", "od_min", "od_max",
                "cs_min", "cs_max", "hp_min", "hp_max", "bpm_min", "bpm_max",
                "len_min", "len_max",
            ))
        )
        if limited_by_difficulty:
            message = (
                f"将删除勾选歌曲中符合当前难度筛选的 {len(targets)} 个难度谱面，"
                "未匹配的其他难度会保留，并移入回收站。继续？"
            )
        else:
            message = f"将删除勾选的 {len(songs)} 首歌中的全部 {len(targets)} 个难度谱面，移入回收站。继续？"
        if not self._confirm_delete("删除难度谱面", message):
            return
        self._run_worker(lambda cb: self.mgr.delete_beatmaps(targets, use_trash=True, progress_cb=cb),
                         "删除难度谱面", "正在删除筛选命中的难度…",
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
        message = f"已删除 {res[0]} 个难度谱面。"
        if len(res) > 1 and res[1]:
            message += f"\n{len(res[1])} 个难度删除失败：\n" + "\n".join(res[1][:8])
            if len(res[1]) > 8:
                message += f"\n另有 {len(res[1]) - 8} 个失败项。"
        QMessageBox.information(self, "结果", message)

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
