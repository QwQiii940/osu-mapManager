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
                result = [s for s in result if any(
                    b.star_rating >= lo and (hi is None or b.star_rating < hi)
                    for b in s.beatmaps
                )]
                break
    if search:
        q = search.lower()
        result = [s for s in result if q in f"{s.title} {s.artist} {s.creator} "
                  + " ".join(b.difficulty_name for b in s.beatmaps).lower()]
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


def _beatmap_matches_difficulty_filters(beatmap, game_mode="全部",
                                        star_min=None, star_max=None) -> bool:
    """判断单个难度是否命中模式与星级筛选。"""
    mode_id = MODE_MAP.get(game_mode)
    if mode_id is not None and beatmap.mode != mode_id:
        return False
    if star_min is not None and beatmap.star_rating < star_min:
        return False
    if star_max is not None and beatmap.star_rating > star_max:
        return False
    return True


def _filter_beatmaps_by_difficulty(beatmaps, game_mode="全部",
                                   star_min=None, star_max=None):
    return [b for b in beatmaps if _beatmap_matches_difficulty_filters(
        b, game_mode, star_min, star_max
    )]


def _beatmap_matches_filters(beatmap, filters: dict) -> bool:
    """按同一张难度谱面匹配模式、星级、属性、BPM 和难度名。"""
    if not _beatmap_matches_difficulty(
        beatmap, filters.get("game_mode", "全部"),
        filters.get("star_min"), filters.get("star_max"),
    ):
        return False
    for field in ("ar", "od", "cs", "hp", "bpm"):
        value = getattr(beatmap, field, 0)
        low, high = filters.get(f"{field}_min"), filters.get(f"{field}_max")
        if low is not None and value < low:
            return False
        if high is not None and value > high:
            return False
    difficulty = (filters.get("difficulty") or "").strip().casefold()
    if difficulty and difficulty not in (getattr(beatmap, "difficulty_name", "") or "").casefold():
        return False
    duration = getattr(beatmap, "total_time_s", 0)
    if filters.get("len_min") is not None and duration < filters["len_min"]:
        return False
    if filters.get("len_max") is not None and duration > filters["len_max"]:
        return False
    return True


def _beatmap_matches_difficulty(beatmap, game_mode="全部", star_min=None, star_max=None):
    return _beatmap_matches_difficulty_filters(beatmap, game_mode, star_min, star_max)


def _filter_beatmaps_by_filters(beatmaps, filters: dict):
    return [b for b in beatmaps if _beatmap_matches_filters(b, filters)]


def _filter_songs_by_filters(songs, filters: dict):
    """歌曲行只在至少一张难度同时满足所有难度级条件时保留。"""
    active = any(filters.get(k) is not None for k in (
        "star_min", "star_max", "ar_min", "ar_max", "od_min", "od_max",
        "cs_min", "cs_max", "hp_min", "hp_max", "bpm_min", "bpm_max",
        "len_min", "len_max",
    )) or filters.get("game_mode", "全部") != "全部" or bool(filters.get("difficulty", "").strip())
    if not active:
        return songs
    return [s for s in songs if _filter_beatmaps_by_filters(s.beatmaps, filters)]


def _filter_songs_by_difficulty(songs, game_mode="全部",
                                star_min=None, star_max=None):
    """保留至少含一个命中难度的歌曲行，模式与星级在同一难度上取交集。"""
    if MODE_MAP.get(game_mode) is None and star_min is None and star_max is None:
        return songs
    return [s for s in songs if _filter_beatmaps_by_difficulty(
        s.beatmaps, game_mode, star_min, star_max
    )]


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
    if star_min is not None or star_max is not None:
        result = [s for s in result if any(
            (star_min is None or b.star_rating >= star_min)
            and (star_max is None or b.star_rating <= star_max)
            for b in s.beatmaps
        )]
    return result


def _filter_by_mode(songs: list[Song], mode_name: str) -> list[Song]:
    """按游戏模式筛选歌曲（保留含该模式难度的谱面集）。"""
    m = MODE_MAP.get(mode_name)
    if m is None:
        return songs
    return [s for s in songs if any(b.mode == m for b in s.beatmaps)]
