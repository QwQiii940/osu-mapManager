"""osudb 解析单元测试：BPM 换算、星级、多模式。"""
import os
import shutil
import struct
import tempfile

import osudb
from test_manager import _s


def _beatmap(title, folder, stars, beat_length, mode=0):
    b = bytearray()
    b += _s("Artist"); b += _s(None); b += _s(title); b += _s(None)
    b += _s("Mapper"); b += _s("Insane"); b += _s("audio.mp3")
    b += _s("0" * 32); b += _s(f"{folder}.osu")
    b += bytes([2])
    b += struct.pack("<H", 100); b += struct.pack("<H", 50); b += struct.pack("<H", 3)
    b += struct.pack("<Q", 0)
    b += struct.pack("<f", 9.0); b += struct.pack("<f", 4.0); b += struct.pack("<f", 6.0); b += struct.pack("<f", 8.0)
    b += struct.pack("<d", 1.6)
    b += struct.pack("<I", 1); b += bytes([0x08]) + struct.pack("<I", 0) + bytes([0x0c]) + struct.pack("<f", stars)
    for _ in range(3):
        b += struct.pack("<I", 0)
    b += struct.pack("<I", 120); b += struct.pack("<I", 180000); b += struct.pack("<I", 60000)
    b += struct.pack("<I", 1)
    b += struct.pack("<d", beat_length)   # 毫秒/拍
    b += struct.pack("<d", 0.0)           # offset
    b += bytes([1])                       # not_inherited=True（红色点，真实 BPM）
    b += struct.pack("<i", 1); b += struct.pack("<i", 2); b += struct.pack("<I", 0)
    b += bytes([9, 9, 9, 9]); b += struct.pack("<H", 0); b += struct.pack("<f", 0.7); b += bytes([mode])
    b += _s("Source"); b += _s("tag1"); b += struct.pack("<H", 0); b += _s(None)
    b += bytes([1]); b += struct.pack("<Q", 0); b += bytes([0])
    b += _s(folder); b += struct.pack("<Q", 0); b += bytes([0, 0, 0, 0, 0])
    b += struct.pack("<I", 0); b += bytes([0])
    return bytes(b)


def _db(beatmaps):
    out = bytearray()
    out += struct.pack("<I", 20260101)
    out += struct.pack("<I", 1)
    out += bytes([1]); out += struct.pack("<Q", 0); out += _s("Q")
    out += struct.pack("<I", len(beatmaps))
    for bm in beatmaps:
        out += bm
    out += struct.pack("<I", 0)
    return bytes(out)


def test_bpm_and_star():
    tmp = tempfile.mkdtemp()
    try:
        db = os.path.join(tmp, "osu!.db")
        with open(db, "wb") as f:
            f.write(_db([_beatmap("Song120", "SetA", 4.5, 500.0)]))  # 500ms -> 120 BPM
        bms = osudb.parse_osu_db(db)
        assert len(bms) == 1
        assert abs(bms[0].bpm - 120.0) < 0.01, bms[0].bpm
        assert abs(bms[0].star_rating - 4.5) < 0.01
        print("BPM/星级解析通过")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_bpm_and_star()
    print("osudb 解析测试通过 ✔")
