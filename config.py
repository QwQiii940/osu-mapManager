"""osu! 安装目录定位与主题配置。"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def app_dir() -> Path:
    """应用可写数据目录：打包为 exe 时用 exe 所在目录，否则用源码目录。

    避免 PyInstaller onefile 下 __file__ 指向临时解压目录导致设置不持久。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


_CONFIG_FILE = app_dir() / ".settings.json"

# 主题配色：bg 主背景、sidebar 侧边栏、card 卡片/列表项、accent 强调色、accent_fg 强调色上的文字、
# fg 正文、muted 次要文字、border 边框、hover 悬停背景
_BASE_THEME: dict[str, str] = {
    "bg": "#f6f7fa", "sidebar": "#eef0f5", "card": "#ffffff",
    "accent": "#e84c73", "accent_fg": "#ffffff", "fg": "#22252d",
    "muted": "#8a8d98", "border": "#e4e6ec", "hover": "#f0f1f6",
}

THEMES: dict[str, dict[str, str]] = {
    "浅色": {
        "bg": "#f6f7fa", "sidebar": "#eef0f5", "card": "#ffffff",
        "accent": "#e84c73", "accent_fg": "#ffffff", "fg": "#22252d",
        "muted": "#8a8d98", "border": "#e4e6ec", "hover": "#f0f1f6",
    },
    "深色": {
        "bg": "#1a1b21", "sidebar": "#121317", "card": "#23242c",
        "accent": "#ff5c8a", "accent_fg": "#ffffff", "fg": "#f0f1f5",
        "muted": "#8a8d98", "border": "#2e3039", "hover": "#2c2e37",
    },
    "蓝色": {
        "bg": "#eef4fc", "sidebar": "#dbe7f7", "card": "#ffffff",
        "accent": "#2f6fe0", "accent_fg": "#ffffff", "fg": "#1b2430",
        "muted": "#75839a", "border": "#d6e2f2", "hover": "#e3eefa",
    },
    "绿色": {
        "bg": "#edf7f0", "sidebar": "#d8eee0", "card": "#ffffff",
        "accent": "#23a55a", "accent_fg": "#ffffff", "fg": "#1a2820",
        "muted": "#758a7d", "border": "#d4e8db", "hover": "#e2f2e8",
    },
}

DEFAULT_SETTINGS = {"osu_dir": "", "theme": "深色", "confirm_delete": True, "accent": "",
                    "bg_image": "", "bg_opacity": 25}


def _load() -> dict:
    try:
        data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return dict(DEFAULT_SETTINGS)


def _save(data: dict) -> None:
    try:
        _CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def _update(**kwargs) -> None:
    data = _load()
    data.update(kwargs)
    _save(data)


def default_candidates() -> list[str]:
    out: list[str] = []
    local = os.environ.get("LOCALAPPDATA")
    if local:
        out.append(os.path.join(local, "osu!"))
    out.extend((r"C:\Program Files\osu!", r"C:\Program Files (x86)\osu!"))
    return out


def is_osu_dir(path: str) -> bool:
    if not path:
        return False
    return os.path.isfile(os.path.join(path, "collection.db")) or os.path.isfile(
        os.path.join(path, "osu!.db")
    )


def find_osu_dir() -> str | None:
    saved = _load().get("osu_dir", "")
    if saved and is_osu_dir(saved):
        return saved
    for p in default_candidates():
        if is_osu_dir(p):
            return p
    return None


def save_osu_dir(path: str) -> None:
    _update(osu_dir=path)


def load_theme() -> str:
    theme = _load().get("theme", "深色")
    return theme if theme in THEMES else "深色"


def save_theme(name: str) -> None:
    _update(theme=name)


def load_accent() -> str:
    return str(_load().get("accent", "")).strip()


def save_accent(value: str) -> None:
    _update(accent=(value or "").strip())


def load_bg_image() -> str:
    return str(_load().get("bg_image", "")).strip()


def save_bg_image(value: str) -> None:
    _update(bg_image=(value or "").strip())


def load_bg_opacity() -> int:
    try:
        return max(0, min(100, int(_load().get("bg_opacity", 25))))
    except (TypeError, ValueError):
        return 25


def save_bg_opacity(value: int) -> None:
    try:
        value = max(0, min(100, int(value)))
    except (TypeError, ValueError):
        value = 25
    _update(bg_opacity=value)


def _is_light(hex_color: str) -> bool:
    """判断颜色是否偏亮（用于决定强调色上的文字用深色还是白色）。"""
    hex_color = (hex_color or "").lstrip("#")
    if len(hex_color) != 6:
        return False
    try:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
    except ValueError:
        return False
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150


def load_confirm_delete() -> bool:
    return bool(_load().get("confirm_delete", True))


def save_confirm_delete(value: bool) -> None:
    _update(confirm_delete=bool(value))


def get_theme_colors(name: str | None = None) -> dict[str, str]:
    theme = name or load_theme()
    colors = {**_BASE_THEME, **THEMES.get(theme, THEMES["深色"])}
    accent = load_accent()
    if accent:
        colors["accent"] = accent
        colors["accent_fg"] = "#222222" if _is_light(accent) else "#ffffff"
    return colors
