"""核心管理逻辑自测：用合成数据跑通筛选/移动/导出/导入。"""
import os
import shutil
import struct
import tempfile
import zipfile

import osudb
import manager
from manager import FilterCriteria, OsuManager


def _s(s):
    if s is None:
        return b"\x00"
    raw = s.encode("utf-8")
    return b"\x0b" + osudb._write_uleb128(len(raw)) + raw


def _beatmap(title, folder, stars, mode=0):
    b = bytearray()
    b += _s("Artist")
    b += _s(None)
    b += _s(title)
    b += _s(None)
    b += _s("Mapper")
    b += _s("Insane")
    b += _s("audio.mp3")
    b += _s("0" * 32 if folder == "Set A" else "1" * 32)  # md5 区分
    b += _s(f"{folder}.osu")
    b += bytes([2])
    b += struct.pack("<H", 100)
    b += struct.pack("<H", 50)
    b += struct.pack("<H", 3)
    b += struct.pack("<Q", 0)
    b += struct.pack("<f", 9.0)  # ar
    b += struct.pack("<f", 4.0)  # cs
    b += struct.pack("<f", 6.0)  # hp
    b += struct.pack("<f", 8.0)  # od
    b += struct.pack("<d", 1.6)
    b += struct.pack("<I", 1)  # std_ratings count
    b += bytes([0x08]) + struct.pack("<I", 0) + bytes([0x0c]) + struct.pack("<f", stars)
    for _ in range(3):
        b += struct.pack("<I", 0)
    b += struct.pack("<I", 120)
    b += struct.pack("<I", 180000)
    b += struct.pack("<I", 60000)
    b += struct.pack("<I", 1)
    b += struct.pack("<d", 180.0)
    b += struct.pack("<d", 0.0)
    b += bytes([1])
    b += struct.pack("<i", 1)
    b += struct.pack("<i", 2)
    b += struct.pack("<I", 0)
    b += bytes([9, 9, 9, 9])
    b += struct.pack("<H", 0)
    b += struct.pack("<f", 0.7)
    b += bytes([mode])
    b += _s("Source")
    b += _s("tag1")
    b += struct.pack("<H", 0)
    b += _s(None)
    b += bytes([1])
    b += struct.pack("<Q", 0)
    b += bytes([0])
    b += _s(folder)
    b += struct.pack("<Q", 0)
    b += bytes([0, 0, 0, 0, 0])
    b += struct.pack("<I", 0)
    b += bytes([0])
    return bytes(b)


def _build_osu_db():
    out = bytearray()
    out += struct.pack("<I", 20260101)
    out += struct.pack("<I", 2)
    out += bytes([1])
    out += struct.pack("<Q", 0)
    out += _s("Q_Qiii")
    out += struct.pack("<I", 2)
    out += _beatmap("TitleA", "Set A", 4.2)
    out += _beatmap("TitleB", "Set B", 6.8)
    out += struct.pack("<I", 0)
    return bytes(out)


def main():
    tmp = tempfile.mkdtemp()
    try:
        osu_dir = os.path.join(tmp, "osu!")
        songs = os.path.join(osu_dir, "Songs")
        os.makedirs(songs)

        with open(os.path.join(osu_dir, "osu!.db"), "wb") as f:
            f.write(_build_osu_db())

        # 初始收藏夹：只有 TitleA 的 md5
        col = osudb.Collection(name="收藏1", beatmap_hashes=["0" * 32])
        osudb.write_collection_db(os.path.join(osu_dir, "collection.db"), 20260101, [col])

        # Songs 目录
        for folder in ("Set A", "Set B"):
            d = os.path.join(songs, folder)
            os.makedirs(d)
            with open(os.path.join(d, f"{folder}.osu"), "w", encoding="utf-8") as f:
                f.write("osu file format v14\n")

        mgr = OsuManager(osu_dir)
        mgr.load()
        assert len(mgr.beatmaps) == 2, len(mgr.beatmaps)
        assert len(mgr.collections) == 1
        assert [b.md5 for b in mgr.beatmaps_in_collection(0)] == ["0" * 32]

        # 筛选：星级 < 5 → 只有 TitleA
        res = mgr.filter(FilterCriteria(star_max=5.0))
        assert [b.title for b in res] == ["TitleA"], [b.title for b in res]

        # 文本筛选
        res = mgr.filter(FilterCriteria(text="titleb"))
        assert [b.title for b in res] == ["TitleB"]

        # 添加 TitleB 到收藏夹
        added = mgr.add_hashes_to_collection(0, ["1" * 32])
        assert added == 1
        assert len(mgr.beatmaps_in_collection(0)) == 2

        # 移除 TitleA
        removed = mgr.remove_hashes_from_collection(0, ["0" * 32])
        assert removed == 1
        assert len(mgr.beatmaps_in_collection(0)) == 1

        # 导出收藏夹（当前只剩 TitleB -> Set B）
        export_dir = os.path.join(tmp, "export")
        ok, failed = mgr.export_collection(0, export_dir)
        assert ok == 1 and not failed, (ok, failed)
        assert os.path.isfile(os.path.join(export_dir, "Set B.osz"))

        # 导入 .osz：造一个包含 .osu 的包
        src = os.path.join(tmp, "src")
        os.makedirs(src)
        with open(os.path.join(src, "New.osu"), "w", encoding="utf-8") as f:
            f.write("osu file format v14\n")
        osz = os.path.join(tmp, "New Set.osz")
        with zipfile.ZipFile(osz, "w") as zf:
            zf.write(os.path.join(src, "New.osu"), "New.osu")

        total, failed = mgr.import_osz([osz], collection_index=0)
        assert total == 1 and not failed, (total, failed)
        # 重新加载后，收藏夹里应有 2 个 md5（原 TitleB + 新导入的 .osu）
        # 注意：新导入谱面尚未被 osu! 索引进 osu!.db，故不能通过 beatmaps_in_collection 统计
        mgr.load()
        assert len(mgr.collections[0].beatmap_hashes) == 2, mgr.collections[0].beatmap_hashes

        print("manager 自测通过 ✔")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
