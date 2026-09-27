"""Shared Qt widgets, core services and helpers used by page controllers."""
from __future__ import annotations

import math
import os
from collections import OrderedDict

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFont, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication, QWidget, QFrame, QLabel, QPushButton, QLineEdit, QComboBox,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem, QStackedWidget,
    QHBoxLayout, QVBoxLayout, QFormLayout, QScrollArea, QFileDialog,
    QMessageBox, QColorDialog, QSlider, QCheckBox, QProgressDialog, QMenu,
    QAbstractItemView, QDialog, QHeaderView, QSizePolicy,
    QListView,
)

import config
import diffcalc
from manager import OsuManager, Song, Beatmap
from common import (
    PAGE_SIZE, COLLECTION_PAGE_SIZE, CLASSIFY_MODES, MODE_FILTERS,
    _categories, _filter_songs_impl, _parse_float, _fmt_filter,
    _apply_advanced_filter, _filter_by_mode,
)
from ui.theme import qcolor as _qcolor, stylesheet
from ui.widgets import CollectionCardDelegate, FlowLayout, PageHeading, SquareCheckBox, SurfaceCard
from ui.dialogs import AutoCategorizeDialog, ReorganizeDialog
from ui.workers import Worker

_FONT_FAMILY = "Microsoft YaHei UI"

__all__ = [name for name in globals() if not name.startswith('__')]
__all__ += ['_categories', '_filter_songs_impl', '_parse_float', '_fmt_filter', '_apply_advanced_filter', '_filter_by_mode', '_qcolor', '_FONT_FAMILY']
