"""Dialogs for collection classification and reorganization."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QVBoxLayout,
)

from common import MODE_FILTERS, MODE_MAP, _parse_thresholds
from manager import FilterCriteria, OsuManager


class AutoCategorizeDialog(QDialog):
    def __init__(self, parent, mgr: OsuManager):
        super().__init__(parent)
        self.mgr = mgr
        self.setWindowTitle("自动分类")
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)

        self._mode = QComboBox()
        self._mode.addItems(["按艺术家", "按星级"])
        layout.addWidget(QLabel("选择整理方式"))
        layout.addWidget(self._mode)

        form = QFormLayout()
        self._min = QLineEdit("1")
        self._th = QLineEdit("2,4,6,8")
        form.addRow("最小谱面数（艺术家）", self._min)
        form.addRow("星级区间阈值", self._th)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._run)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _run(self):
        try:
            if self._mode.currentText() == "按艺术家":
                summary = self.mgr.categorize_by_artist(min_songs=int(self._min.text().strip() or "1"))
            else:
                thresholds = _parse_thresholds(self._th.text())
                if not thresholds:
                    QMessageBox.critical(self, "错误", "星级阈值格式无效。")
                    return
                summary = self.mgr.categorize_by_star(thresholds)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "错误", f"分类失败：{exc}")
            return
        self.accept()
        QMessageBox.information(
            self, "分类完成",
            f"共创建/更新 {len(summary)} 个收藏夹，新增 {sum(summary.values())} 张谱面。",
        )


class ReorganizeDialog(QDialog):
    def __init__(self, parent, mgr: OsuManager):
        super().__init__(parent)
        self.mgr = mgr
        self.setWindowTitle("重新整理收藏夹")
        self.setMinimumWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)
        layout.addWidget(QLabel(
            "按艺术家重新创建收藏夹，并优先保留收录曲目较多的艺术家。\n"
            "现有收藏夹会被清空；谱面文件不会删除。"
        ))

        form = QFormLayout()
        self._target = QLineEdit("200")
        self._min = QLineEdit("1")
        self._bpm_min = QLineEdit()
        self._bpm_max = QLineEdit()
        self._star_min = QLineEdit()
        self._star_max = QLineEdit()
        self._mode = QComboBox()
        self._mode.addItems(MODE_FILTERS)
        form.addRow("目标收藏夹数量", self._target)
        form.addRow("最小谱面数", self._min)

        bpm = QHBoxLayout()
        bpm.addWidget(self._bpm_min)
        bpm.addWidget(QLabel("至"))
        bpm.addWidget(self._bpm_max)
        form.addRow("BPM 范围（可选）", bpm)

        star = QHBoxLayout()
        star.addWidget(self._star_min)
        star.addWidget(QLabel("至"))
        star.addWidget(self._star_max)
        form.addRow("星级范围（可选）", star)
        form.addRow("模式（可选）", self._mode)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._run)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _num(text):
        value = text.strip()
        return float(value) if value else None

    def _run(self):
        try:
            target = int(self._target.text().strip() or "200")
            min_songs = int(self._min.text().strip() or "1")
            criteria = FilterCriteria(
                bpm_min=self._num(self._bpm_min.text()),
                bpm_max=self._num(self._bpm_max.text()),
                star_min=self._num(self._star_min.text()),
                star_max=self._num(self._star_max.text()),
                mode=MODE_MAP.get(self._mode.currentText()),
            )
        except ValueError:
            QMessageBox.critical(self, "错误", "输入有误：请检查数字格式。")
            return

        if QMessageBox.question(
            self, "确认重新整理",
            f"将清空全部 {len(self.mgr.collections)} 个收藏夹并重新整理。继续？",
        ) != QMessageBox.StandardButton.Yes:
            return
        summary = self.mgr.reorganize_collections(
            target_count=target, min_songs=min_songs, criteria=criteria,
        )
        self.accept()
        QMessageBox.information(
            self, "完成",
            f"已整理为 {len(summary)} 个收藏夹，共 {sum(summary.values())} 张谱面。",
        )
