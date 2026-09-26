"""共享常量与纯函数（供各页面子模块使用，避免与 gui.py 循环导入）。"""
from __future__ import annotations

from manager import Song, primary_artist

_FONT = "Microsoft YaHei UI"

# 歌曲列表每页显示数量（防止一次性渲染数千行导致界面卡死）
PAGE_SIZE = 50

# 收藏夹每页显示数量（分类后收藏夹可能很多）
COLLECTION_PAGE_SIZE = 60

# 难度（星级）分类档位
DIFF_RANGES: list[tuple[float, float | None, str]] = [
    (0.0, 2.0, "0-2星"),
    (2.0, 4.0, "2-4星"),
    (4.0, 6.0, "4-6星"),
    (6.0, 8.0, "6-8星"),
    (8.0, None, "8星以上"),
]

CLASSIFY_MODES = ["全部", "按艺术家", "按首字母", "按难度(星级)"]

# 游戏模式筛选（osu / taiko / ctb / mania）
MODE_FILTERS = ["全部", "osu", "taiko", "ctb", "mania"]
MODE_MAP = {"全部": None, "osu": 0, "taiko": 1, "ctb": 2, "mania": 3}


def _first_letter(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "#"
    ch = s[0].upper()
    return ch if "A" <= ch <= "Z" else "#"


def _parse_thresholds(text: str) -> list[float]:
    parts = [p for p in text.replace("，", ",").split(",") if p.strip()]
    vals = []
    for p in parts:
        try:
            v = float(p.strip())
        except ValueError:
            return []
        if v <= 0:
            return []
        vals.append(v)
    return sorted(set(vals))


def _categories(songs: list[Song], mode: str) -> list[str]:
    if mode == "按艺术家":
        return sorted({primary_artist(s.artist) for s in songs})
    if mode == "按首字母":
        return sorted({_first_letter(s.title) for s in songs})
    if mode == "按难度(星级)":
        return [label for _, _, label in DIFF_RANGES]
    return []


def _filter_songs_impl(songs: list[Song], mode: str, category: str | None, search: str) -> list[Song]:
    result = songs
    if mode == "按艺术家":
        result = [s for s in result if primary_artist(s.artist) == category]
    elif mode == "按首字母":
        result = [s for s in result if _first_letter(s.title) == category]
    elif mode == "按难度(星级)":
        for lo, hi, label in DIFF_RANGES:
            if label == category:
                result = [s for s in result if s.star_max >= lo and (hi is None or s.star_max < hi)]
                break
    if search:
        q = search.lower()
        result = [s for s in result if q in f"{s.title} {s.artist} {s.creator}".lower()]
    return result


def _parse_float(text: str) -> float | None:
    t = (text or "").strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _fmt_filter(v) -> str:
    return "" if v is None else str(v)


def _apply_advanced_filter(songs: list[Song], letter="", artist="",
                           len_min=None, len_max=None, star_min=None, star_max=None) -> list[Song]:
    """按自定义条件（首字母 / artist / 长度秒 / 星级）过滤歌曲列表。"""
    result = songs
    if letter:
        letters = {ch.upper() for ch in letter if ch.isalpha()}
        if letters:
            result = [s for s in result if _first_letter(s.title) in letters]
    if artist:
        q = artist.lower()
        result = [s for s in result if q in (s.artist or "").lower()]
    if len_min is not None or len_max is not None:
        def dur(s):
            return max((b.total_time_s for b in s.beatmaps), default=0)
        if len_min is not None:
            result = [s for s in result if dur(s) >= len_min]
        if len_max is not None:
            result = [s for s in result if dur(s) <= len_max]
    if star_min is not None:
        result = [s for s in result if s.star_max >= star_min]
    if star_max is not None:
        result = [s for s in result if s.star_max <= star_max]
    return result


def _filter_by_mode(songs: list[Song], mode_name: str) -> list[Song]:
    """按游戏模式筛选歌曲（保留含该模式难度的谱面集）。"""
    m = MODE_MAP.get(mode_name)
    if m is None:
        return songs
    return [s for s in songs if any(b.mode == m for b in s.beatmaps)]
