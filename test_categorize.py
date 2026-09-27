"""分类功能与回收站删除自测。"""
import os
import shutil
import tempfile

import manager
import osudb
from manager import OsuManager


def _beatmaps():
    return [
        osudb.Beatmap(md5="a" * 32, artist="Alpha", title="T1", star_rating=4.2, folder_name="A"),
        osudb.Beatmap(md5="b" * 32, artist="Alpha", title="T2", star_rating=6.8, folder_name="B"),
        osudb.Beatmap(md5="c" * 32, artist="Beta", title="T3", star_rating=3.0, folder_name="C"),
    ]


def test_categorize_artist():
    tmp = tempfile.mkdtemp()
    try:
        m = OsuManager(tmp)
        m.beatmaps = _beatmaps()
        m.collections = []
        m.collection_version = 20260101

        summary = m.categorize_by_artist()
        assert summary == {"Alpha": 2, "Beta": 1}, summary
        assert len(m.collections) == 2

        # 再次运行：应合并到同名收藏夹，不产生重复
        summary2 = m.categorize_by_artist()
        assert summary2 == {"Alpha": 0, "Beta": 0}, summary2
        assert len(m.collections) == 2
        print("按艺术家分类通过")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_categorize_star():
    tmp = tempfile.mkdtemp()
    try:
        m = OsuManager(tmp)
        m.beatmaps = _beatmaps()
        m.collections = []
        m.collection_version = 20260101

        summary = m.categorize_by_star([4, 7])
        assert summary == {"0-4星": 1, "4-7星": 2}, summary
        assert len(m.collections) == 2
        print("按星级分类通过")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_recycle_bin():
    tmp = tempfile.mkdtemp()
    try:
        f = os.path.join(tmp, "_recycle_bin_probe.txt")
        with open(f, "w", encoding="utf-8") as fp:
            fp.write("probe")
        ok = manager.send_to_recycle_bin(f)
        assert ok, "send_to_recycle_bin 返回 False"
        assert not os.path.exists(f), "文件未被移入回收站"
        print("回收站删除通过")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_categorize_artist()
    test_categorize_star()
    test_recycle_bin()
    print("分类/回收站 自测通过 ✔")
