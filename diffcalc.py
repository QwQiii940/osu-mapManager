"""本地星级计算，基于 rosu-pp-py（osu!lazer 官方难度算法的 Rust 移植）。

用于补齐 osu!.db 中缺失的星级（star == 0 的谱面），让按星级筛选/删除覆盖全部谱面。
"""
from __future__ import annotations

from typing import Optional

try:
    from rosu_pp_py import Beatmap, Difficulty, GameMode
    _AVAILABLE = True
except ImportError:  # 未安装 rosu-pp-py 时优雅降级
    _AVAILABLE = False


def is_available() -> bool:
    return _AVAILABLE


def calculate_star(osu_file_path: str, mode: int) -> Optional[float]:
    """计算单个 .osu 文件的星级；失败或无内容返回 None。

    mode 为 osu! 游戏模式编号（0=osu, 1=taiko, 2=ctb, 3=mania）。
    """
    if not _AVAILABLE:
        return None
    mode_map = {0: GameMode.Osu, 1: GameMode.Taiko, 2: GameMode.Catch, 3: GameMode.Mania}
    try:
        bm = Beatmap(path=osu_file_path)
        bm.convert(mode_map.get(mode, GameMode.Osu))
        if bm.n_objects == 0:
            return None  # 无击打对象（如 hitsounds 谱面），无法计算
        return float(Difficulty().calculate(bm).stars)
    except Exception:
        return None
