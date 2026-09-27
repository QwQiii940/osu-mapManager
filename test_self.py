"""自测：验证 osudb 的读写逻辑（collection.db 往返 + osu!.db 解析）。

由于本机 osu! stable 数据目录当前不可用，这里用合成字节做确定性校验。
"""
import struct
import os
import osudb

VERSION = 20260101  # 取一个 >= 20250107 的现代版本


def build_string(s):
    if s is None:
        return b"\x00"
    raw = s.encode("utf-8")
    return b"\x0b" + osudb._write_uleb128(len(raw)) + raw


def build_osu_db():
    out = bytearray()
    out += struct.pack("<I", VERSION)       # version
    out += struct.pack("<I", 1)             # folder_count
    out += bytes([1])                        # account_unlocked
    out += struct.pack("<Q", 0)              # unlock_date
    out += build_string("Q_Qiii")            # player_name
    out += struct.pack("<I", 2)              # beatmap_count

    def beatmap(title, stars):
        b = bytearray()
        b += build_string("Artist")          # artist_ascii
        b += build_string("アーティスト")     # artist_unicode
        b += build_string(title)             # title_ascii
        b += build_string(None)              # title_unicode
        b += build_string("Mapper")          # creator
        b += build_string("Insane")          # difficulty_name
        b += build_string("audio.mp3")       # audio
        b += build_string("0123456789abcdef0123456789abcdef")  # hash (32)
        b += build_string("Artist - Title (Mapper) [Insane].osu")  # file_name
        b += bytes([2])                      # status (pending/wip/graveyard)
        b += struct.pack("<H", 100)          # hitcircle_count
        b += struct.pack("<H", 50)           # slider_count
        b += struct.pack("<H", 3)            # spinner_count
        b += struct.pack("<Q", 132000000000000000)  # last_modified
        b += struct.pack("<f", 9.0)          # ar
        b += struct.pack("<f", 4.0)          # cs
        b += struct.pack("<f", 6.0)          # hp
        b += struct.pack("<f", 8.0)          # od
        b += struct.pack("<d", 1.6)          # slider_velocity
        # std_ratings: 2 条 (nomod + DT)
        b += struct.pack("<I", 2)
        b += bytes([0x08]) + struct.pack("<I", 0) + bytes([0x0c]) + struct.pack("<f", stars)
        b += bytes([0x08]) + struct.pack("<I", 1 << 6) + bytes([0x0c]) + struct.pack("<f", stars + 1.5)
        for _ in range(3):  # taiko/ctb/mania ratings 均为空
            b += struct.pack("<I", 0)
        b += struct.pack("<I", 120)          # drain_time
        b += struct.pack("<I", 180000)       # total_time
        b += struct.pack("<I", 60000)        # preview_time
        b += struct.pack("<I", 1)            # timing_points count
        b += struct.pack("<d", 60000.0 / 180.0)  # beat length in ms for 180 BPM
        b += struct.pack("<d", 0.0)          # offset
        b += bytes([1])                      # inherits
        b += struct.pack("<i", 12345)        # beatmap_id
        b += struct.pack("<i", 67890)        # beatmapset_id
        b += struct.pack("<I", 0)            # thread_id
        b += bytes([9, 9, 9, 9])             # grades (unplayed)
        b += struct.pack("<H", 0)            # local_beatmap_offset
        b += struct.pack("<f", 0.7)          # stack_leniency
        b += bytes([0])                      # mode (std)
        b += build_string("Source")          # song_source
        b += build_string("tag1 tag2")       # tags
        b += struct.pack("<H", 0)            # online_offset
        b += build_string(None)              # title_font
        b += bytes([1])                      # unplayed
        b += struct.pack("<Q", 0)            # last_played
        b += bytes([0])                      # is_osz2
        b += build_string("Artist - Title")  # folder_name
        b += struct.pack("<Q", 132000000000000000)  # last_online_check
        b += bytes([0, 0, 0, 0, 0])          # ignore_* / disable_* / visual_override
        b += struct.pack("<I", 0)            # mysterious_last_modified
        b += bytes([0])                      # mania_scroll_speed
        return bytes(b)

    out += beatmap("TitleA", 4.2)
    out += beatmap("TitleB", 6.8)
    out += struct.pack("<I", 0)              # user_permissions
    return bytes(out)


def test_osu_db():
    data = build_osu_db()
    with open("_synthetic_osu.db", "wb") as f:
        f.write(data)
    bms = osudb.parse_osu_db("_synthetic_osu.db")
    assert len(bms) == 2, f"期望 2 张谱面，得到 {len(bms)}"
    a, b = bms
    assert a.title == "TitleA" and abs(a.star_rating - 4.2) < 1e-3, (a.title, a.star_rating)
    assert b.title == "TitleB" and abs(b.star_rating - 6.8) < 1e-3, (b.title, b.star_rating)
    # Unicode 艺术家优先于罗马音
    assert a.artist == "アーティスト" and a.creator == "Mapper"
    assert a.ar == 9.0 and a.od == 8.0 and a.cs == 4.0 and a.hp == 6.0
    assert abs(a.bpm - 180.0) < 1e-3
    assert a.mode == 0 and a.mode_name == "osu"
    assert a.md5 == "0123456789abcdef0123456789abcdef"
    assert a.folder_name == "Artist - Title"
    print("osu!.db 解析通过：", [(x.title, round(x.star_rating, 2)) for x in bms])


def test_collection_db_roundtrip():
    cols = [
        osudb.Collection(name="我的收藏", beatmap_hashes=["a" * 32, "b" * 32]),
        osudb.Collection(name="4星以下", beatmap_hashes=["c" * 32]),
        osudb.Collection(name="空收藏夹", beatmap_hashes=[]),
    ]
    osudb.write_collection_db("_synthetic_col.db", VERSION, cols)
    ver, read = osudb.parse_collection_db("_synthetic_col.db")
    assert ver == VERSION
    assert len(read) == 3
    assert read[0].name == "我的收藏" and read[0].beatmap_hashes == ["a" * 32, "b" * 32]
    assert read[1].name == "4星以下" and read[1].beatmap_hashes == ["c" * 32]
    assert read[2].name == "空收藏夹" and read[2].beatmap_hashes == []
    print("collection.db 往返通过：", [(c.name, len(c.beatmap_hashes)) for c in read])


def test_uleb128():
    assert osudb._write_uleb128(0) == b"\x00"
    assert osudb._write_uleb128(127) == b"\x7f"
    assert osudb._write_uleb128(128) == b"\x80\x01"
    assert osudb._write_uleb128(300) == b"\xac\x02"
    print("ULEB128 通过")


if __name__ == "__main__":
    test_uleb128()
    test_collection_db_roundtrip()
    test_osu_db()
    # 清理临时文件
    for p in ("_synthetic_osu.db", "_synthetic_col.db"):
        if os.path.exists(p):
            os.remove(p)
    print("全部自测通过 ✔")
