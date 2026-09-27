"""osu! 私有二进制数据库（osu!.db / collection.db）的解析与写入。

osu! stable 客户端使用一套自定义二进制格式存储谱面缓存与收藏夹，
并非 SQLite。本模块实现了对该格式的读取与写入。

格式参考（社区逆向工程）：
  - osu-db (Rust): https://github.com/kovaxis/osu-db
  - 数据均为小端序；字符串采用 "0x00=空 / 0x0b=ULEB128 长度 + UTF-8" 编码。
"""
from __future__ import annotations

import struct
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

# Windows FILETIME 纪元：自 0001-01-01 起的 100 纳秒间隔
_WINDOWS_EPOCH = datetime(1, 1, 1)

# osu! 数据库格式发生破坏性变更的版本阈值
_CHANGE_20140609 = 20140609
_CHANGE_20191106 = 20191106
_CHANGE_20250107 = 20250107

MODE_NAMES = {0: "osu", 1: "taiko", 2: "ctb", 3: "mania"}


def ticks_to_datetime(ticks: int) -> Optional[datetime]:
    """把 Windows FILETIME tick 转换为 datetime（0 表示空/未设置）。"""
    if not ticks:
        return None
    try:
        return _WINDOWS_EPOCH + timedelta(microseconds=ticks // 10)
    except OverflowError:
        return None


class BinaryReader:
    """带指针的二进制读取器，所有多字节整数均为小端序。"""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def read(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise EOFError(f"读取越界：pos={self.pos} 需要 {n} 字节，剩余 {len(self.data) - self.pos}")
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def u8(self) -> int:
        return self.read(1)[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.read(2))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.read(4))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.read(4))[0]

    def u64(self) -> int:
        return struct.unpack("<Q", self.read(8))[0]

    def f32(self) -> float:
        return struct.unpack("<f", self.read(4))[0]

    def f64(self) -> float:
        return struct.unpack("<d", self.read(8))[0]

    def boolean(self) -> bool:
        return self.u8() != 0

    def uleb128(self) -> int:
        """ULEB128 变长整数，用于字符串长度。"""
        result = 0
        shift = 0
        while True:
            b = self.u8()
            result |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        return result

    def string(self) -> Optional[str]:
        """读取 osu! 字符串：0x00 表示 None，0x0b 表示后跟 ULEB128 长度 + UTF-8 字节。"""
        first = self.u8()
        if first == 0x00:
            return None
        if first == 0x0B:
            length = self.uleb128()
            return self.read(length).decode("utf-8", errors="replace")
        raise ValueError(f"非法字符串标记 0x{first:02x}（pos={self.pos - 1}）")


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class Beatmap:
    """一张谱面（单个难度）的元数据。"""
    artist: str = ""
    title: str = ""
    creator: str = ""
    difficulty_name: str = ""   # 难度名（如 Easy/Normal/Hard/Insane）
    audio: str = ""
    md5: str = ""               # 谱面 MD5，收藏夹以此标识谱面
    file_name: str = ""         # .osu 文件名
    folder_name: str = ""       # Songs 下的谱面集文件夹名
    mode: int = 0
    star_rating: float = 0.0    # 无 mod 星级
    ar: float = 0.0
    od: float = 0.0
    cs: float = 0.0
    hp: float = 0.0
    bpm: float = 0.0
    hitcircle_count: int = 0
    slider_count: int = 0
    spinner_count: int = 0
    total_time_ms: int = 0
    drain_time_s: int = 0
    beatmap_id: int = 0
    beatmapset_id: int = 0
    status: int = 0
    song_source: str = ""
    tags: str = ""
    last_modified: Optional[datetime] = None

    @property
    def mode_name(self) -> str:
        return MODE_NAMES.get(self.mode, str(self.mode))

    @property
    def total_time_s(self) -> int:
        return self.total_time_ms // 1000


@dataclass
class Collection:
    """一个收藏夹：名称 + 谱面 MD5 列表。"""
    name: str = ""
    beatmap_hashes: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# osu!.db 解析
# ---------------------------------------------------------------------------

def _parse_star_ratings(r: BinaryReader, version: int) -> list[tuple[int, float]]:
    """读取一组 (modset, 星级) 列表。

    每个条目带类型标记：0x08 + u32 modset，随后是星级。
    2025-01-07 之前星级为 0x0d + f64，之后为 0x0c + f32。
    """
    if version < _CHANGE_20140609:
        return []
    count = r.u32()
    ratings = []
    for _ in range(count):
        tag = r.u8()
        if tag != 0x08:
            raise ValueError(f"星级条目标记异常：0x{tag:02x}（pos={r.pos - 1}）")
        modset = r.u32()
        if version < _CHANGE_20250107:
            r.u8()  # 0x0d
            rating = r.f64()
        else:
            r.u8()  # 0x0c
            rating = r.f32()
        ratings.append((modset, rating))
    return ratings


def _parse_timing_point(r: BinaryReader) -> tuple[float, float, bool]:
    beat_length = r.f64()   # 毫秒/拍（beat length），BPM = 60000 / beat_length
    offset = r.f64()
    not_inherited = r.boolean()  # 真=未继承（红色点，真实 BPM）；假=继承（绿色点，SV）
    return beat_length, offset, not_inherited


def _parse_beatmap(r: BinaryReader, version: int) -> Beatmap:
    b = Beatmap()

    # 优先使用 Unicode（原始语言）标题/艺术家，缺失时回退到罗马音
    artist_ascii = r.string() or ""
    artist_unicode = r.string() or ""
    title_ascii = r.string() or ""
    title_unicode = r.string() or ""
    b.artist = artist_unicode or artist_ascii
    b.title = title_unicode or title_ascii
    b.creator = r.string() or ""
    b.difficulty_name = r.string() or ""
    b.audio = r.string() or ""
    b.md5 = r.string() or ""
    b.file_name = r.string() or ""

    b.status = r.u8()
    b.hitcircle_count = r.u16()
    b.slider_count = r.u16()
    b.spinner_count = r.u16()
    b.last_modified = ticks_to_datetime(r.u64())

    # 20140609 之后难度值为 f32，之前为 u8
    if version >= _CHANGE_20140609:
        b.ar = r.f32()
        b.cs = r.f32()
        b.hp = r.f32()
        b.od = r.f32()
    else:
        b.ar = float(r.u8())
        b.cs = float(r.u8())
        b.hp = float(r.u8())
        b.od = float(r.u8())

    _ = r.f64()  # slider_velocity

    std_ratings = _parse_star_ratings(r, version)
    taiko_ratings = _parse_star_ratings(r, version)
    ctb_ratings = _parse_star_ratings(r, version)
    mania_ratings = _parse_star_ratings(r, version)

    b.drain_time_s = r.u32()
    b.total_time_ms = r.u32()
    _ = r.u32()  # preview_time

    tp_count = r.u32()
    for _ in range(tp_count):
        beat_length, _offset, not_inherited = _parse_timing_point(r)
        # 仅未继承（红色）timing point 的 beat_length 代表真实 BPM
        if b.bpm == 0.0 and not_inherited and beat_length > 0:
            b.bpm = 60000.0 / beat_length

    b.beatmap_id = r.i32()
    b.beatmapset_id = r.i32()
    _ = r.u32()  # thread_id

    _ = r.u8()  # std_grade
    _ = r.u8()  # taiko_grade
    _ = r.u8()  # ctb_grade
    _ = r.u8()  # mania_grade

    _ = r.u16()  # local_beatmap_offset
    _ = r.f32()  # stack_leniency
    b.mode = r.u8()

    b.song_source = r.string() or ""
    b.tags = r.string() or ""

    _ = r.u16()  # online_offset
    _ = r.string()  # title_font

    _ = r.boolean()  # unplayed
    _ = r.u64()      # last_played (datetime)
    _ = r.boolean()  # is_osz2
    b.folder_name = r.string() or ""
    _ = r.u64()      # last_online_check
    _ = r.boolean()  # ignore_sounds
    _ = r.boolean()  # ignore_skin
    _ = r.boolean()  # disable_storyboard
    _ = r.boolean()  # disable_video
    _ = r.boolean()  # visual_override

    _ = r.u32()  # mysterious_last_modified
    _ = r.u8()   # mania_scroll_speed

    # 选取对应游戏模式的无 mod 星级
    ratings = {0: std_ratings, 1: taiko_ratings, 2: ctb_ratings, 3: mania_ratings}[b.mode]
    for modset, rating in ratings:
        if modset == 0:
            b.star_rating = rating
            break

    return b


def parse_osu_db(path: str) -> list[Beatmap]:
    """解析 osu!.db，返回全部谱面。"""
    with open(path, "rb") as f:
        data = f.read()
    r = BinaryReader(data)

    version = r.u32()
    folder_count = r.u32()
    _ = r.boolean()  # account_unlocked
    _ = r.u64()      # unlock_date
    _ = r.string()   # player_name

    beatmap_count = r.u32()
    beatmaps = []
    for _ in range(beatmap_count):
        if version < _CHANGE_20191106:
            _ = r.u32()  # beatmap_size（旧版字段）
        beatmaps.append(_parse_beatmap(r, version))

    _ = r.u32()  # user_permissions
    return beatmaps


# ---------------------------------------------------------------------------
# collection.db 解析与写入
# ---------------------------------------------------------------------------

def parse_collection_db(path: str) -> tuple[int, list[Collection]]:
    """解析 collection.db，返回 (version, 收藏夹列表)。"""
    with open(path, "rb") as f:
        data = f.read()
    r = BinaryReader(data)

    version = r.u32()
    count = r.u32()
    collections = []
    for _ in range(count):
        name = r.string() or ""
        n = r.u32()
        hashes = []
        for _ in range(n):
            h = r.string() or ""
            hashes.append(h)
        collections.append(Collection(name=name, beatmap_hashes=hashes))
    return version, collections


def write_collection_db(path: str, version: int, collections: list[Collection]) -> None:
    """原子写回 collection.db，并在修改前刷新可恢复备份。"""
    out = bytearray()
    out += struct.pack("<I", version)
    out += struct.pack("<I", len(collections))
    for c in collections:
        out += _write_string(c.name)
        out += struct.pack("<I", len(c.beatmap_hashes))
        for h in c.beatmap_hashes:
            out += _write_string(h)
    path = os.path.abspath(path)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=directory, prefix=".collection.db.", suffix=".tmp", delete=False
        ) as f:
            temp_path = f.name
            f.write(out)
            f.flush()
            os.fsync(f.fileno())

        if os.path.isfile(path):
            backup_path = path + ".bak"
            shutil.copy2(path, backup_path)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


def _write_string(s: Optional[str]) -> bytes:
    if not s:
        return b"\x00"
    raw = s.encode("utf-8")
    return b"\x0b" + _write_uleb128(len(raw)) + raw


def _write_uleb128(value: int) -> bytes:
    out = bytearray()
    while True:
        b = value & 0x7F
        value >>= 7
        if value:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)
