"""程序入口：定位 osu! 目录并启动 PySide6 图形界面。"""
from __future__ import annotations

import sys
import traceback

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

import config


def _fatal(exc_type, exc_value, exc_tb):
    """启动阶段未捕获异常：记录并弹窗，避免 --windowed 下静默闪退。"""
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    try:
        log_path = config.app_dir() / "error.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n" + "=" * 60 + "\n" + text)
    except OSError:
        pass
    try:
        app = QApplication.instance() or QApplication([])
        log_path = config.app_dir() / "error.log"
        QMessageBox.critical(
            None, "发生错误",
            f"程序启动失败：\n\n{exc_value}\n\n详情已记录到：\n{log_path}",
        )
    except Exception:
        pass


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)

    osu_dir = config.find_osu_dir()
    if not osu_dir:
        QMessageBox.information(
            None, "未找到 osu!",
            "未自动检测到 osu!（stable）安装目录。\n请在下一步选择包含 collection.db / osu!.db 的目录。",
        )
        osu_dir = QFileDialog.getExistingDirectory(None, "选择 osu! 安装目录")

    if not osu_dir:
        return
    if not config.is_osu_dir(osu_dir):
        QMessageBox.critical(None, "错误", "所选目录不是有效的 osu! 目录（缺少 collection.db / osu!.db）")
        return

    config.save_osu_dir(osu_dir)

    import qt_app
    qt_app.run(osu_dir)
    sys.exit(app.exec())


if __name__ == "__main__":
    sys.excepthook = _fatal
    try:
        main()
    except SystemExit:
        raise
    except BaseException as e:
        _fatal(type(e), e, e.__traceback__)
