"""Settings page controller methods."""
from __future__ import annotations

from .shared import (
    OsuManager,
    PageHeading,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
    Qt,
    SurfaceCard,
    _qcolor,
    config,
    diffcalc,
)


class SettingsMixin:
    """Coordinates the settings screen while reusing the shared app state."""

    def _build_settings(self, lay):
        lay.addWidget(PageHeading("设置", "调整 osu! 数据目录、外观与维护选项。", eyebrow="PREFERENCES"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll.viewport().setStyleSheet("background: transparent;")
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        settings_card = SurfaceCard(body, margins=(22, 20, 22, 20), spacing=16)
        settings_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        body_layout.addWidget(settings_card)
        body_layout.addStretch(1)
        scroll.setWidget(body)
        form = QFormLayout()
        form.setSpacing(14)
        settings_card.content.addLayout(form)

        def section(text):
            label = QLabel(text)
            label.setObjectName("settingsSection")
            form.addRow(label)

        # osu! 目录
        section("游戏库")
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
        section("外观")
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
        section("数据维护")
        form.addRow("数据", data_row)

        # 确认
        section("操作习惯")
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
        self._view_states.clear()
        self._checked_song_keys.clear()
        self._checked_collection_ids.clear()
        self._checked_collection_refs.clear()
        self._collections_page = 0
        self.viewing_collection = None
        config.save_osu_dir(d)
        self.show_page("home")

    def _apply_theme(self, name):
        config.save_theme(name)
        self.theme_name = name
        self.colors = config.get_theme_colors(name)
        self._reload_bg()
        self._apply_styles()
        self.update()
        self.show_page(self.current_page)

    def _pick_accent(self):
        col = QColorDialog.getColor(_qcolor(self.colors.get("accent", "#ff5c8a")), self, "选择强调色")
        if col.isValid():
            config.save_accent(col.name())
            self.colors = config.get_theme_colors(self.theme_name)
            self._apply_styles()
            self.update()
            self.show_page(self.current_page)

    def _reset_accent(self):
        config.save_accent("")
        self.colors = config.get_theme_colors(self.theme_name)
        self._apply_styles()
        self.update()
        self.show_page(self.current_page)

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
