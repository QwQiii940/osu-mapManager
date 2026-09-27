"""Collections page controller methods."""
from __future__ import annotations

from .shared import (
    AutoCategorizeDialog,
    COLLECTION_PAGE_SIZE,
    CollectionCardDelegate,
    PageHeading,
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSize,
    Qt,
    ReorganizeDialog,
    SurfaceCard,
    config,
    math,
)


class CollectionsMixin:
    """Coordinates the collections screen while reusing the shared app state."""

    def _build_collections(self, lay):
        head = QHBoxLayout()
        head.addWidget(PageHeading("谱面收藏夹", "整理曲包，记录每一次练习。"), 1)
        head.addStretch(1)

        search = QLineEdit()
        search.setPlaceholderText("搜索收藏夹…")
        search.setFixedWidth(220)
        head.addWidget(search)

        btn_new = QPushButton("新建收藏夹")
        btn_new.setProperty("class", "primary")
        btn_new.clicked.connect(self._new_collection)
        head.addWidget(btn_new)

        btn_auto = QPushButton("自动分类…")
        btn_auto.clicked.connect(self._auto_categorize)

        btn_reorg = QPushButton("重新整理…")
        btn_reorg.clicked.connect(self._reorganize_collections)
        lay.addLayout(head)

        select_bar = QHBoxLayout()
        select_bar.setContentsMargins(0, 0, 0, 0)
        self._col_selection_hint = QLabel("当前筛选已选 0 个")
        self._col_selection_hint.setStyleSheet(f"color: {self.colors['muted']}; font-size: 12px;")
        select_bar.addWidget(self._col_selection_hint)
        self._batch_label = QLabel("已选 0 个")
        self._batch_label.setStyleSheet(f"color: {self.colors['muted']}; font-size: 12px;")
        select_bar.addWidget(self._batch_label)
        select_bar.addStretch(1)
        self._col_select_all_btn = QPushButton("全选")
        self._col_select_all_btn.clicked.connect(lambda: self._set_all_collections_checked(True))
        self._col_select_none_btn = QPushButton("取消")
        self._col_select_none_btn.clicked.connect(lambda: self._set_all_collections_checked(False))
        select_bar.addWidget(self._col_select_all_btn)
        select_bar.addWidget(self._col_select_none_btn)
        self._merge_btn = QPushButton("合并所选")
        self._merge_btn.clicked.connect(self._merge_selected)
        self._delete_btn = QPushButton("删除所选")
        self._delete_btn.setProperty("class", "danger")
        self._delete_btn.clicked.connect(self._delete_selected)
        self._export_btn = QPushButton("导出所选")
        self._export_btn.clicked.connect(self._export_selected)
        select_bar.addWidget(self._merge_btn)
        select_bar.addWidget(self._delete_btn)
        select_bar.addWidget(self._export_btn)
        select_panel = SurfaceCard(margins=(14, 8, 14, 8), spacing=0)
        select_panel.content.addLayout(select_bar)
        lay.addWidget(select_panel)

        # 分类、去重与排序工具栏
        btn_dedupe = QPushButton("合并同名收藏夹")
        btn_dedupe.clicked.connect(self._dedupe_collections)
        tools = QHBoxLayout()
        tools.addWidget(btn_auto)
        tools.addWidget(btn_reorg)
        tools.addWidget(btn_dedupe)
        tools.addStretch(1)
        tools.addWidget(QLabel("排序"))
        self._sort_combo = QComboBox()
        self._sort_combo.addItems(["默认顺序", "按名称", "按数量"])
        self._sort_combo.currentIndexChanged.connect(lambda _: self._refresh_collections())
        tools.addWidget(self._sort_combo)
        lay.addLayout(tools)

        self.col_list = QListWidget()
        self.col_list.setViewMode(QListView.ViewMode.IconMode)
        self.col_list.setResizeMode(QListView.ResizeMode.Adjust)
        self.col_list.setMovement(QListView.Movement.Static)
        self.col_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.col_list.setItemDelegate(CollectionCardDelegate(self.colors, self.col_list))
        self.col_list.setGridSize(QSize(216, 174))
        self.col_list.setWordWrap(True)
        self.col_list.setMouseTracking(True)
        self.col_list.itemDoubleClicked.connect(lambda it: self._open_collection(it.data(Qt.ItemDataRole.UserRole)))
        self.col_list.itemChanged.connect(self._on_collection_item_changed)
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

    def _on_collections_search(self, text):
        self._collections_query = text.strip().lower()
        self._collections_page = 0
        self._refresh_collections()

    def _filtered_collection_items(self) -> list[tuple[int, object]]:
        items = [(i, c) for i, c in enumerate(self.mgr.collections)
                 if not self._collections_query or self._collections_query in (c.name or "").lower()]
        sort_mode = getattr(self, "_sort_combo", None)
        if sort_mode is not None:
            sort_mode = sort_mode.currentText()
            if sort_mode == "按名称":
                items = sorted(items, key=lambda t: (t[1].name or "").lower())
            elif sort_mode == "按数量":
                items = sorted(items, key=lambda t: len(t[1].beatmap_hashes), reverse=True)
        return items

    def _refresh_collections(self):
        items = self._filtered_collection_items()
        total = len(items)
        pages = max(1, math.ceil(total / COLLECTION_PAGE_SIZE))
        if self._collections_page >= pages:
            self._collections_page = pages - 1
        start = self._collections_page * COLLECTION_PAGE_SIZE
        page = items[start:start + COLLECTION_PAGE_SIZE]

        self.col_list.clear()
        for gidx, c in page:
            it = QListWidgetItem(c.name or "(未命名)")
            it.setData(Qt.ItemDataRole.UserRole, gidx)
            it.setData(Qt.ItemDataRole.UserRole + 1, len(c.beatmap_hashes))
            it.setToolTip(f"{c.name}\n{len(c.beatmap_hashes)} 张谱面")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if id(c) in self._checked_collection_ids else Qt.CheckState.Unchecked)
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
        return [i for i, collection in enumerate(self.mgr.collections)
                if id(collection) in self._checked_collection_ids]

    def _on_collection_item_changed(self, item):
        gidx = item.data(Qt.ItemDataRole.UserRole)
        if gidx is None:
            return
        collection = self.mgr.collections[gidx]
        collection_id = id(collection)
        if item.checkState() == Qt.CheckState.Checked:
            self._checked_collection_ids.add(collection_id)
            self._checked_collection_refs[collection_id] = collection
        else:
            self._checked_collection_ids.discard(collection_id)
            self._checked_collection_refs.pop(collection_id, None)
        self._update_batch_buttons()

    def _set_all_collections_checked(self, checked: bool):
        """全选/取消当前筛选结果的所有收藏夹（跨页）。"""
        for _, collection in self._filtered_collection_items():
            collection_id = id(collection)
            if checked:
                self._checked_collection_ids.add(collection_id)
                self._checked_collection_refs[collection_id] = collection
            else:
                self._checked_collection_ids.discard(collection_id)
                self._checked_collection_refs.pop(collection_id, None)
        self._refresh_collections()

    def _update_batch_buttons(self):
        n = len(self._selected_indices())
        self._batch_label.setText(f"已选 {n} 个")
        self._merge_btn.setEnabled(n >= 2)
        self._delete_btn.setEnabled(n >= 1)
        self._export_btn.setEnabled(n >= 1)
        hint = getattr(self, "_col_selection_hint", None)
        if hint is not None:
            visible = {id(collection) for _, collection in self._filtered_collection_items()}
            picked = len(visible & self._checked_collection_ids)
            hint.setText(f"当前筛选已选 {picked} / {len(visible)} 个收藏夹")

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
        self._checked_collection_ids.clear()
        self._checked_collection_refs.clear()
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
        self._checked_collection_ids.clear()
        self._checked_collection_refs.clear()
        self._refresh_collections()
        QMessageBox.information(self, "完成", f"已合并到「{target}」。")

    def _delete_selected(self):
        idxs = self._selected_indices()
        if not idxs:
            return
        if not self._confirm_delete("删除收藏夹", f"确定删除选中的 {len(idxs)} 个收藏夹？\n（仅删除收藏夹，不删除谱面文件）"):
            return
        self.mgr.delete_collections(idxs)
        self._checked_collection_ids.clear()
        self._checked_collection_refs.clear()
        self._refresh_collections()

    def _dedupe_collections(self):
        if QMessageBox.question(self, "合并同名收藏夹", "将合并名称相同的收藏夹（谱面去重）。继续？") != QMessageBox.StandardButton.Yes:
            return
        merged = self.mgr.dedupe_collections()
        self._checked_collection_ids.clear()
        self._checked_collection_refs.clear()
        self._refresh_collections()
        QMessageBox.information(self, "完成", f"已合并 {merged} 个同名收藏夹。" if merged else "没有发现同名收藏夹。")

    def _auto_categorize(self):
        dlg = AutoCategorizeDialog(self, self.mgr)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._checked_collection_ids.clear()
            self._checked_collection_refs.clear()
            self._refresh_collections()

    def _reorganize_collections(self):
        dlg = ReorganizeDialog(self, self.mgr)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.viewing_collection = None
            self._checked_collection_ids.clear()
            self._checked_collection_refs.clear()
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


