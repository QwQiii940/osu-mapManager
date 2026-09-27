"""核心管理逻辑：装载数据、筛选、移动、删除、导入、导出。"""
from __future__ import annotations

import ctypes
import hashlib
import os
import re
import shutil
import zipfile
from collections import defaultdict
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Optional

import osudb
from aliases import canonical_artist, is_famous
from osudb import Beatmap, Collection


# ---------------------------------------------------------------------------
# 回收站删除（Windows Shell API）
# ---------------------------------------------------------------------------

def send_to_recycle_bin(path: str) -> bool:
    """把文件/目录移入 Windows 回收站（可恢复）。成功返回 True。"""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return False

    class SHFILEOPSTRUCT(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", ctypes.c_uint),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x40
    FOF_NOCONFIRMATION = 0x10
    FOF_SILENT = 0x04

    p_from = path + "\0\0"
    op = SHFILEOPSTRUCT()
    op.wFunc = FO_DELETE
    op.pFrom = p_from
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
    try:
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    except OSError:
        return False
    return result == 0 and not op.fAnyOperationsAborted


def md5_of_file(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _fmt(x: float) -> str:
    """把浮点格式化为紧凑字符串（2.0 -> '2'，2.5 -> '2.5'）。"""
    return f"{x:g}"


# 合作类分隔符（x / vs / × / 逗号）：取第一位艺术家
_ARTIST_SPLIT = re.compile(
    r"\s+(?:versus|vs\.?|x|×)\s+|\s*,\s*",
    re.IGNORECASE,
)

# featuring 分隔符：A feat. B / A ft. B / A featuring B —— 取后面的合作者 B
_FEAT_SPLIT = re.compile(
    r"\s+(?:featuring|feat\.?|ft\.?)\s+",
    re.IGNORECASE,
)


def primary_artist(artist: str) -> str:
    """提取单个首要艺术家（用于「按艺术家」分类视图的逐曲归类）。

    - "A feat. B" / "A ft. B" / "A featuring B" -> "B"（取后面的合作者）
    - "1234 X 5678" / "A vs B" / "A × B" / "A, B" -> "1234" / "A"（取第一位）
    - 保留原始语言（日文/中文等），不罗马化；空值回退 "(未知艺术家)"。

    注意：建收藏夹（categorize_by_artist）用的是 split_artists + 热度最高的艺术家，
    与此处的逐曲规则不同。
    """
    a = (artist or "").strip()
    if not a:
        return "(未知艺术家)"
    m = _FEAT_SPLIT.search(a)
    if m:
        a = a[m.end():].strip() or a
    first = _ARTIST_SPLIT.split(a, maxsplit=1)[0].strip()
    return canonical_artist(first or a)


# 全部多艺术家分隔符（feat. / ft. / featuring / vs. / x / × / 逗号）
_ALL_ARTIST_SEPARATORS = re.compile(
    r"\s+(?:featuring|feat\.?|ft\.?|versus|vs\.?|x|×)\s+|\s*,\s*",
    re.IGNORECASE,
)


def split_artists(artist: str) -> list[str]:
    """把艺术家字段拆分为候选艺术家列表（去重、保序）。

    "A feat. B" -> ["A", "B"]；"1234 X 5678" -> ["1234", "5678"]。
    保留原始语言；空值回退为 ["(未知艺术家)"]。
    """
    a = (artist or "").strip()
    if not a:
        return ["(未知艺术家)"]
    parts = [p.strip() for p in _ALL_ARTIST_SEPARATORS.split(a) if p.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        p = canonical_artist(p)
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out or [a]


def _ranked_artist_groups(pool: list[Beatmap]) -> list[tuple[str, list[str]]]:
    """把谱面按艺术家分组，返回按（是否著名、谱面数）降序的 [(artist, [md5])]。

    多艺术家谱面只归入一个艺术家：著名优先、其次歌曲更多。
    """
    counts: dict[str, int] = defaultdict(int)
    multi: list[Beatmap] = []
    for b in pool:
        if not b.md5:
            continue
        cands = split_artists(b.artist)
        if len(cands) == 1:
            counts[cands[0]] += 1
        else:
            multi.append(b)

    groups: dict[str, list[str]] = defaultdict(list)
    for b in pool:
        if not b.md5:
            continue
        cands = split_artists(b.artist)
        if len(cands) == 1:
            groups[cands[0]].append(b.md5)

    def rank(a: str) -> tuple[bool, int]:
        return (is_famous(a), counts.get(a, 0))

    for b in multi:
        cands = split_artists(b.artist)
        groups[max(cands, key=rank)].append(b.md5)

    return sorted(groups.items(), key=lambda kv: (is_famous(kv[0]), len(kv[1])), reverse=True)


# ---------------------------------------------------------------------------
# 筛选条件
# ---------------------------------------------------------------------------

@dataclass
class FilterCriteria:
    star_min: Optional[float] = None
    star_max: Optional[float] = None
    ar_min: Optional[float] = None
    ar_max: Optional[float] = None
    od_min: Optional[float] = None
    od_max: Optional[float] = None
    cs_min: Optional[float] = None
    cs_max: Optional[float] = None
    hp_min: Optional[float] = None
    hp_max: Optional[float] = None
    bpm_min: Optional[float] = None
    bpm_max: Optional[float] = None
    mode: Optional[int] = None            # None = 全部
    text: str = ""

    def matches(self, b: Beatmap) -> bool:
        if self.star_min is not None and b.star_rating < self.star_min:
            return False
        if self.star_max is not None and b.star_rating > self.star_max:
            return False
        if self.ar_min is not None and b.ar < self.ar_min:
            return False
        if self.ar_max is not None and b.ar > self.ar_max:
            return False
        if self.od_min is not None and b.od < self.od_min:
            return False
        if self.od_max is not None and b.od > self.od_max:
            return False
        if self.cs_min is not None and b.cs < self.cs_min:
            return False
        if self.cs_max is not None and b.cs > self.cs_max:
            return False
        if self.hp_min is not None and b.hp < self.hp_min:
            return False
        if self.hp_max is not None and b.hp > self.hp_max:
            return False
        if self.bpm_min is not None and b.bpm and b.bpm < self.bpm_min:
            return False
        if self.bpm_max is not None and b.bpm and b.bpm > self.bpm_max:
            return False
        if self.mode is not None and b.mode != self.mode:
            return False
        if self.text:
            q = self.text.lower()
            hay = " ".join([
                b.title, b.artist, b.creator, b.difficulty_name,
                b.song_source, b.tags,
            ]).lower()
            if q not in hay:
                return False
        return True


# ---------------------------------------------------------------------------
# 谱面集（Song）
# ---------------------------------------------------------------------------

@dataclass
class Song:
    """一个谱面集：同一首歌的多个难度（.osu）聚合成一行。"""
    title: str = ""
    artist: str = ""
    creator: str = ""
    folder_name: str = ""
    beatmaps: list = field(default_factory=list)  # list[Beatmap]

    @property
    def star_min(self) -> float:
        return min((b.star_rating for b in self.beatmaps), default=0.0)

    @property
    def star_max(self) -> float:
        return max((b.star_rating for b in self.beatmaps), default=0.0)

    @property
    def modes(self) -> list[str]:
        return sorted({b.mode_name for b in self.beatmaps})


def group_into_songs(beatmaps: list[Beatmap]) -> list[Song]:
    """把难度列表按谱面集聚合为 Song 列表。"""
    groups: dict[str, list[Beatmap]] = {}
    order: list[str] = []
    for b in beatmaps:
        if b.folder_name:
            key = b.folder_name
        elif b.beatmapset_id > 0:
            key = f"set:{b.beatmapset_id}"
        else:
            key = f"md5:{b.md5}"
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(b)

    songs: list[Song] = []
    for key in order:
        bms = sorted(groups[key], key=lambda x: x.star_rating)
        first = bms[0]
        songs.append(Song(
            title=first.title,
            artist=first.artist,
            creator=first.creator,
            folder_name=first.folder_name,
            beatmaps=bms,
        ))
    return songs


# ---------------------------------------------------------------------------
# 管理器
# ---------------------------------------------------------------------------

class OsuManager:
    def __init__(self, osu_dir: str):
        self.osu_dir = osu_dir
        self.songs_dir = os.path.join(osu_dir, "Songs")
        self.beatmaps: list[Beatmap] = []
        self.collections: list[Collection] = []
        self.collection_version = 0

    # ---- 装载 / 保存 ----

    def load(self) -> None:
        self.beatmaps = []
        self.collections = []
        osu_db = os.path.join(self.osu_dir, "osu!.db")
        if os.path.isfile(osu_db):
            try:
                self.beatmaps = osudb.parse_osu_db(osu_db)
            except Exception as e:  # 解析失败不阻断启动
                print(f"解析 osu!.db 失败：{e}")
        col_db = os.path.join(self.osu_dir, "collection.db")
        if os.path.isfile(col_db):
            try:
                self.collection_version, self.collections = osudb.parse_collection_db(col_db)
            except Exception as e:
                print(f"解析 collection.db 失败：{e}")

    def save_collections(self) -> None:
        osudb.write_collection_db(
            os.path.join(self.osu_dir, "collection.db"),
            self.collection_version,
            self.collections,
        )

    # ---- 查询 ----

    def beatmaps_in_collection(self, index: int) -> list[Beatmap]:
        hashes = set(self.collections[index].beatmap_hashes)
        return [b for b in self.beatmaps if b.md5 in hashes]

    def filter(self, criteria: FilterCriteria, source: Optional[list[Beatmap]] = None) -> list[Beatmap]:
        pool = source if source is not None else self.beatmaps
        return [b for b in pool if criteria.matches(b)]

    def get_songs(self) -> list[Song]:
        """全部谱面按谱面集聚合为 Song 列表。"""
        return group_into_songs(self.beatmaps)

    def songs_in_collection(self, index: int) -> list[Song]:
        """收藏夹内谱面聚合为 Song 列表（只含收藏夹内的难度）。"""
        hashes = set(self.collections[index].beatmap_hashes)
        selected = [b for b in self.beatmaps if b.md5 in hashes]
        return group_into_songs(selected)

    def find_song_image(self, folder_name: str) -> Optional[str]:
        """在谱面集目录中查找背景图（取最大的 jpg/png）。"""
        if not folder_name:
            return None
        folder = os.path.join(self.songs_dir, folder_name)
        if not os.path.isdir(folder):
            return None
        try:
            entries = os.listdir(folder)
        except OSError:
            return None
        images = [os.path.join(folder, n) for n in entries
                  if n.lower().endswith((".jpg", ".jpeg", ".png"))]
        if not images:
            return None
        try:
            return max(images, key=os.path.getsize)
        except OSError:
            return None

    def find_song_audio(self, folder_name: str) -> Optional[str]:
        """在谱面集目录中查找音频文件（优先 mp3/ogg）。"""
        if not folder_name:
            return None
        folder = os.path.join(self.songs_dir, folder_name)
        if not os.path.isdir(folder):
            return None
        try:
            entries = os.listdir(folder)
        except OSError:
            return None
        audios = [n for n in entries if n.lower().endswith((".mp3", ".ogg", ".wav", ".flac", ".m4a"))]
        if not audios:
            return None
        for ext in (".mp3", ".ogg", ".wav", ".flac", ".m4a"):
            for n in audios:
                if n.lower().endswith(ext):
                    return os.path.join(folder, n)
        return os.path.join(folder, audios[0])

    def fill_missing_stars(self, progress_cb=None) -> tuple[int, int]:
        """本地计算缺失星级的谱面（star == 0），更新内存视图。

        返回 (已填充数量, 无法计算数量)。不写入 osu!.db。
        """
        import diffcalc
        filled = failed = 0
        targets = [b for b in self.beatmaps if b.star_rating == 0 and b.folder_name and b.file_name]
        total = len(targets)
        for i, b in enumerate(targets):
            path = os.path.join(self.songs_dir, b.folder_name, b.file_name)
            if not os.path.isfile(path):
                failed += 1
            else:
                stars = diffcalc.calculate_star(path, b.mode)
                if stars is not None and stars > 0:
                    b.star_rating = stars
                    filled += 1
                else:
                    failed += 1
            if progress_cb:
                progress_cb(i + 1, total)
        return filled, failed

    # ---- 收藏夹操作 ----

    def add_collection(self, name: str) -> int:
        self.collections.append(Collection(name=name, beatmap_hashes=[]))
        self.save_collections()
        return len(self.collections) - 1

    def rename_collection(self, index: int, new_name: str) -> None:
        self.collections[index].name = new_name
        self.save_collections()

    def delete_collection(self, index: int) -> None:
        del self.collections[index]
        self.save_collections()

    def delete_collections(self, indices: list[int]) -> int:
        """批量删除收藏夹（仅删除收藏夹，不删除谱面文件）。返回删除数量。"""
        idxs = sorted({i for i in indices if 0 <= i < len(self.collections)}, reverse=True)
        for i in idxs:
            del self.collections[i]
        if idxs:
            self.save_collections()
        return len(idxs)

    def merge_collections(self, indices: list[int]) -> str:
        """把多个收藏夹合并到第一个，其余删除。返回合并后的收藏夹名。"""
        idxs = sorted({i for i in indices if 0 <= i < len(self.collections)})
        if len(idxs) < 2:
            return ""
        keep = idxs[0]
        target = self.collections[keep]
        seen = set(target.beatmap_hashes)
        for i in idxs[1:]:
            for h in self.collections[i].beatmap_hashes:
                if h not in seen:
                    seen.add(h)
                    target.beatmap_hashes.append(h)
        for i in reversed(idxs[1:]):
            del self.collections[i]
        self.save_collections()
        return target.name or "(未命名)"

    def dedupe_collections(self) -> int:
        """合并同名收藏夹（谱面 MD5 去重后保留一个）。返回被合并掉的数量。"""
        by_name: dict[str, int] = {}
        to_remove: list[int] = []
        for i, c in enumerate(self.collections):
            key = (c.name or "").strip()
            if key in by_name:
                keep = by_name[key]
                existing = set(self.collections[keep].beatmap_hashes)
                for h in c.beatmap_hashes:
                    if h not in existing:
                        existing.add(h)
                        self.collections[keep].beatmap_hashes.append(h)
                to_remove.append(i)
            else:
                by_name[key] = i
        for i in reversed(to_remove):
            del self.collections[i]
        if to_remove:
            self.save_collections()
        return len(to_remove)

    def add_hashes_to_collection(self, index: int, hashes: list[str]) -> int:
        """把谱面 MD5 加入收藏夹，去重；返回新增数量。"""
        added = self._add_hashes_no_save(index, hashes)
        if added:
            self.save_collections()
        return added

    def _add_hashes_no_save(self, index: int, hashes: list[str]) -> int:
        """加入谱面 MD5（去重），不写盘。"""
        existing = set(self.collections[index].beatmap_hashes)
        added = [h for h in hashes if h and h not in existing]
        self.collections[index].beatmap_hashes.extend(added)
        return len(added)

    def _collection_index_by_name(self, name: str) -> Optional[int]:
        for i, c in enumerate(self.collections):
            if c.name == name:
                return i
        return None

    def remove_hashes_from_collection(self, index: int, hashes: list[str]) -> int:
        hs = set(hashes)
        before = len(self.collections[index].beatmap_hashes)
        self.collections[index].beatmap_hashes = [
            h for h in self.collections[index].beatmap_hashes if h not in hs
        ]
        removed = before - len(self.collections[index].beatmap_hashes)
        if removed:
            self.save_collections()
        return removed

    # ---- 自动分类 ----

    def categorize_by_artist(self, min_songs: int = 1, prefix: str = "",
                             max_collections: Optional[int] = None,
                             other_name: str = "其他") -> dict[str, int]:
        """按艺术家分组，为每组创建（或合并到同名）收藏夹。

        min_songs：艺术家谱面数（难度数）低于该值则跳过。
        多艺术家谱面只归入一个艺术家：著名优先、其次歌曲更多（减少收藏夹数量、提高整合）。
        若指定 max_collections，则只保留热度最高的前 N 个艺术家，
        其余（含未达 min_songs 的）合并到 other_name。
        返回 {收藏夹名: 本次新增谱面数}。
        """
        ranked = _ranked_artist_groups(self.beatmaps)
        summary: dict[str, int] = {}

        def _ensure(name: str) -> int:
            idx = self._collection_index_by_name(name)
            if idx is None:
                self.collections.append(Collection(name=name, beatmap_hashes=[]))
                idx = len(self.collections) - 1
            return idx

        if max_collections and max_collections > 0:
            qualified = [(a, hs) for a, hs in ranked if len(hs) >= min_songs]
            kept = qualified[:max_collections]
            leftover = qualified[max_collections:]
            leftover += [(a, hs) for a, hs in ranked if len(hs) < min_songs]

            for artist, hashes in kept:
                name = f"{prefix}{artist}"
                summary[name] = self._add_hashes_no_save(_ensure(name), hashes)
            others = [h for _, hs in leftover for h in hs]
            if others:
                name = f"{prefix}{other_name}"
                summary[name] = self._add_hashes_no_save(_ensure(name), others)
        else:
            for artist, hashes in ranked:
                if len(hashes) < min_songs:
                    continue
                name = f"{prefix}{artist}"
                summary[name] = self._add_hashes_no_save(_ensure(name), hashes)

        self.save_collections()
        return summary

    def categorize_by_star(
        self, thresholds: list[float], prefix: str = ""
    ) -> dict[str, int]:
        """按星级区间分组并创建（或合并到同名）收藏夹。

        thresholds：升序星级阈值列表，例如 [2,4,6,8] 生成
        0-2 / 2-4 / 4-6 / 6-8 / 8+ 五档。
        返回 {收藏夹名: 本次新增谱面数}。
        """
        ranges: list[tuple[float, Optional[float], str]] = []
        lo = 0.0
        for i, hi in enumerate(thresholds):
            label = f"{_fmt(lo)}-{_fmt(hi)}星"
            ranges.append((lo, hi, label))
            lo = hi
        ranges.append((lo, None, f"{_fmt(lo)}星以上"))

        groups: dict[str, list[str]] = defaultdict(list)
        for b in self.beatmaps:
            if not b.md5:
                continue
            for r_lo, r_hi, label in ranges:
                if b.star_rating >= r_lo and (r_hi is None or b.star_rating < r_hi):
                    groups[label].append(b.md5)
                    break

        summary: dict[str, int] = {}
        for _lo, _hi, label in ranges:
            hashes = groups.get(label, [])
            if not hashes:
                continue
            name = f"{prefix}{label}"
            idx = self._collection_index_by_name(name)
            if idx is None:
                self.collections.append(Collection(name=name, beatmap_hashes=[]))
                idx = len(self.collections) - 1
            added = self._add_hashes_no_save(idx, hashes)
            summary[name] = added
        self.save_collections()
        return summary

    def reorganize_collections(
        self,
        target_count: int = 200,
        min_songs: int = 1,
        criteria: Optional[FilterCriteria] = None,
        other_name: str = "其他",
    ) -> dict[str, int]:
        """清空全部收藏夹，按艺术家重新整理。

        - 只保留热度最高（著名优先、歌曲多）的 target_count 个艺术家收藏夹；
        - 其余（含未达 min_songs 的）合并到 other_name；
        - criteria 非空时只纳入符合条件（如 BPM/星级/模式）的谱面；
        - 返回 {收藏夹名: 谱面数}。仅影响收藏夹，不删除谱面文件。
        """
        pool = [b for b in self.beatmaps if b.md5]
        if criteria is not None:
            pool = [b for b in pool if criteria.matches(b)]

        ranked = _ranked_artist_groups(pool)
        qualified = [(a, hs) for a, hs in ranked if len(hs) >= min_songs]
        keep_n = max(1, int(target_count))
        kept = qualified[:keep_n]
        leftover = qualified[keep_n:]
        leftover += [(a, hs) for a, hs in ranked if len(hs) < min_songs]

        self.collections = []
        summary: dict[str, int] = {}
        for artist, hashes in kept:
            self.collections.append(Collection(name=artist, beatmap_hashes=list(hashes)))
            summary[artist] = len(hashes)

        others = [h for _, hs in leftover for h in hs]
        if others:
            self.collections.append(Collection(name=other_name, beatmap_hashes=others))
            summary[other_name] = len(others)

        self.save_collections()
        return summary

    # ---- 删除文件 ----

    def delete_beatmap_files(self, beatmaps: list[Beatmap], use_trash: bool = True) -> tuple[int, list[str]]:
        """删除谱面所在的 Songs 目录（按 folder_name 去重）。返回 (成功数, 失败列表)。"""
        folders = []
        seen = set()
        for b in beatmaps:
            if not b.folder_name or b.folder_name in seen:
                continue
            seen.add(b.folder_name)
            folders.append(b.folder_name)

        ok, failed = 0, []
        for name in folders:
            path = os.path.join(self.songs_dir, name)
            if not os.path.exists(path):
                failed.append(name)
                continue
            try:
                if use_trash:
                    if send_to_recycle_bin(path):
                        ok += 1
                    else:
                        failed.append(name)
                else:
                    shutil.rmtree(path)
                    ok += 1
            except OSError:
                failed.append(name)
        return ok, failed

    def delete_song(self, song: Song, use_trash: bool = True) -> tuple[int, list[str]]:
        """删除一个谱面集目录，并从内存与所有收藏夹中清除该谱面。"""
        ok, failed = self.delete_beatmap_files(song.beatmaps, use_trash=use_trash)
        if ok:
            hashes = {b.md5 for b in song.beatmaps if b.md5}
            self.beatmaps = [b for b in self.beatmaps if b.md5 not in hashes]
            for c in self.collections:
                c.beatmap_hashes = [h for h in c.beatmap_hashes if h not in hashes]
            self.save_collections()
        return ok, failed

    def delete_songs(self, songs: list[Song], use_trash: bool = True,
                     progress_cb=None) -> tuple[int, list[str]]:
        """批量删除多个谱面集目录，一次性清理内存与收藏夹。

        返回 (成功删除的目录数, 失败列表)。progress_cb(done, total) 用于进度提示。
        """
        all_hashes: set[str] = set()
        folders: list[str] = []
        seen: set[str] = set()
        for song in songs:
            for b in song.beatmaps:
                if b.md5:
                    all_hashes.add(b.md5)
                if b.folder_name and b.folder_name not in seen:
                    seen.add(b.folder_name)
                    folders.append(b.folder_name)

        ok, failed = 0, []
        total = len(folders)
        for i, name in enumerate(folders):
            path = os.path.join(self.songs_dir, name)
            if not os.path.exists(path):
                ok += 1  # 已不存在，视为已删除
            else:
                try:
                    if use_trash:
                        if send_to_recycle_bin(path):
                            ok += 1
                        else:
                            failed.append(name)
                    else:
                        shutil.rmtree(path)
                        ok += 1
                except OSError:
                    failed.append(name)
            if progress_cb:
                progress_cb(i + 1, total)

        if all_hashes:
            self.beatmaps = [b for b in self.beatmaps if b.md5 not in all_hashes]
            for c in self.collections:
                c.beatmap_hashes = [h for h in c.beatmap_hashes if h not in all_hashes]
            self.save_collections()
        return ok, failed

    def delete_beatmaps(self, beatmaps: list[Beatmap], use_trash: bool = True,
                        progress_cb=None) -> tuple[int, list[str]]:
        """删除单个难度（.osu 文件）；若某集目录不再含 .osu 则一并删除该目录。

        返回 (已删除难度数, 失败列表)。删除后同步清理内存与收藏夹。
        progress_cb(done, total)：每处理一个难度回调一次，用于界面进度提示。
        """
        hashes_by_path: dict[tuple[str, str], set[str]] = {}
        for beatmap in beatmaps:
            if not beatmap.folder_name or not beatmap.file_name:
                continue
            path_key = (beatmap.folder_name, beatmap.file_name)
            hashes_by_path.setdefault(path_key, set())
            if beatmap.md5:
                hashes_by_path[path_key].add(beatmap.md5)
        targets = list(hashes_by_path)
        affected = sorted({folder for folder, _ in targets})
        total = len(targets)

        ok, failed = 0, []
        removed_paths: set[tuple[str, str]] = set()
        for i, (folder, file) in enumerate(targets):
            path = os.path.join(self.songs_dir, folder, file)
            if not os.path.exists(path):
                ok += 1  # 文件已不存在，视为已删除
                removed_paths.add((folder, file))
            else:
                try:
                    if use_trash:
                        if send_to_recycle_bin(path):
                            ok += 1
                            removed_paths.add((folder, file))
                        else:
                            failed.append(f"{folder}/{file}")
                    else:
                        os.remove(path)
                        ok += 1
                        removed_paths.add((folder, file))
                except OSError:
                    failed.append(f"{folder}/{file}")
            if progress_cb:
                progress_cb(i + 1, total)

        # 清理不再含 .osu 的谱面集目录（避免留下只有音频/图片的空目录）
        for folder in affected:
            fdir = os.path.join(self.songs_dir, folder)
            if not os.path.isdir(fdir):
                continue
            try:
                entries = os.listdir(fdir)
            except OSError:
                continue
            if not any(e.lower().endswith(".osu") for e in entries):
                try:
                    if use_trash:
                        send_to_recycle_bin(fdir)
                    else:
                        shutil.rmtree(fdir)
                except OSError:
                    pass

        # 清理内存与收藏夹
        hashes = {h for path_key in removed_paths for h in hashes_by_path[path_key]}
        self.beatmaps = [b for b in self.beatmaps
                         if (b.folder_name, b.file_name) not in removed_paths]
        if hashes:
            for c in self.collections:
                c.beatmap_hashes = [h for h in c.beatmap_hashes if h not in hashes]
            self.save_collections()
        return ok, failed

    # ---- 导出 ----

    def export_collection(self, index: int, target_dir: str) -> tuple[int, list[str]]:
        """把收藏夹内谱面集打包为 .osz，返回 (成功数, 失败列表)。"""
        bms = self.beatmaps_in_collection(index)
        folders = []
        seen = set()
        for b in bms:
            if b.folder_name and b.folder_name not in seen:
                seen.add(b.folder_name)
                folders.append(b.folder_name)

        os.makedirs(target_dir, exist_ok=True)
        ok, failed = 0, []
        for name in folders:
            src = os.path.join(self.songs_dir, name)
            if not os.path.isdir(src):
                failed.append(name)
                continue
            dst = os.path.join(target_dir, name + ".osz")
            try:
                _zip_folder(src, dst)
                ok += 1
            except OSError:
                failed.append(name)
        return ok, failed

    # ---- 导入 ----

    def import_osz(self, osz_paths: list[str], collection_index: Optional[int] = None) -> tuple[int, list[str]]:
        """解包 .osz 到 Songs/，返回 (导入的谱面数, 失败列表)。"""
        os.makedirs(self.songs_dir, exist_ok=True)
        total, failed = 0, []
        all_hashes: list[str] = []

        for osz in osz_paths:
            try:
                hashes = self._import_one(osz)
                total += len(hashes)
                all_hashes.extend(hashes)
            except Exception as e:
                failed.append(f"{os.path.basename(osz)}: {e}")

        if collection_index is not None and all_hashes:
            self.add_hashes_to_collection(collection_index, all_hashes)
        return total, failed

    def _import_one(self, osz_path: str) -> list[str]:
        """解包单个 .osz 到 Songs 目录并返回其中 .osu 文件的 MD5。"""
        base = os.path.splitext(os.path.basename(osz_path))[0]
        # 目标目录名 = .osz 文件名（去扩展名）
        dest = os.path.join(self.songs_dir, base)

        with zipfile.ZipFile(osz_path) as zf:
            root = os.path.realpath(dest)
            for member in zf.infolist():
                member_path = member.filename.replace("/", os.sep).replace("\\", os.sep)
                target = os.path.realpath(os.path.join(root, member_path))
                try:
                    within_root = os.path.normcase(os.path.commonpath((root, target))) == os.path.normcase(root)
                except ValueError:
                    within_root = False
                if not within_root:
                    raise ValueError(f"压缩包包含目标目录之外的路径：{member.filename}")
            os.makedirs(dest, exist_ok=True)
            zf.extractall(dest)

        hashes = []
        for root, _dirs, files in os.walk(dest):
            for f in files:
                if f.lower().endswith(".osu"):
                    hashes.append(md5_of_file(os.path.join(root, f)))
        return hashes


def _zip_folder(src_dir: str, dst_osz: str) -> None:
    """把目录打包为 .osz（ZIP）。"""
    with zipfile.ZipFile(dst_osz, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(src_dir):
            for f in files:
                full = os.path.join(root, f)
                arcname = os.path.relpath(full, src_dir)
                zf.write(full, arcname)
