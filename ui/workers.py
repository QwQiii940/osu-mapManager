"""Background worker used by long-running UI actions."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    progress = Signal(int, int)
    done = Signal(object)
    error = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn(self._cb))
        except Exception as exc:  # noqa: BLE001
            self.error.emit(str(exc))

    def _cb(self, done, total):
        self.progress.emit(done, total)
