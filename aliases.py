"""艺术家别名归一化：把同一艺术家的英文/日文/中文等写法映射到统一规范名。

规范名优先用日文原名（保留原语言）；无日文名的用英文。
数据来源：Wikipedia、萌娘百科、VocaWiki、nicodb 等公开资料（2026-09 整理）。

使用方式：`canonical_artist("Camellia") -> "かめりあ"`。
"""
from __future__ import annotations

# 规范名 -> 别名列表（别名会 casefold 后作为查表 key）
_ALIAS_GROUPS: dict[str, list[str]] = {
    # 电子音乐作曲家
    "かめりあ": ["camellia", "cametek", "quarks", "カメリア", "かめりあ"],
    "削除": ["sakuzyo", "削除"],
    # 歌い手 / 歌手
    "ななひら": ["nanahira", "ナナヒラ", "ななひら"],
    "花たん": ["hanatan", "花碳", "花たん"],
    "ゆいこんぬ": ["yuikonnu", "ゆいこんぬ"],
    # VOCALOID 音源（虚拟歌手）
    "初音ミク": ["hatsune miku", "初音未来", "初音ミク"],
    "巡音ルカ": ["megurine luka", "巡音流歌", "巡音ルカ"],
    "鏡音リン": ["kagamine rin", "镜音铃", "鏡音リン"],
    "鏡音レン": ["kagamine len", "镜音连", "鏡音レン"],
    "メグッポイド": ["gumi", "megpoid", "メグッポイド"],
    "結月ゆかり": ["yuzuki yukari", "结月缘", "結月ゆかり"],
    "花譜": ["kaf", "花谱", "花譜"],
    "可不": ["kafu", "可不"],
    # ボカロP（作曲者）
    "DECO*27": ["deco*27", "deco27"],
    "ピノキオピー": ["pinocchiop", "pinocchio-p", "ピノキオピー", "ピノキオp", "匹诺曹p"],
    "じん": ["jin", "自然の敵p", "じん"],
    "ハチ": ["hachi", "kenshi yonezu", "米津玄師", "米津玄师", "ハチ"],
    "かいりきベア": ["kairiki bear", "怪力熊", "かいりきベア", "かいりきベアー"],
    "ナユタン星人": ["nayutan seijin", "那由他星人", "奶油糖星人", "nayutan星人", "ナユタン星人"],
    "はるまきごはん": ["harumaki gohan", "春卷饭", "はるまきごはん"],
    "ツミキ": ["tsumiki", "ツミキ"],
    "ぬゆり": ["nuyuri", "ぬゆり"],
    "蜂屋ななし": ["hachiya nanashi", "蜂屋ななし"],
    "ギガ": ["giga", "giga-p", "ギガp", "ギガ"],
    "みきとp": ["mikito-p", "mikito p", "みきとp", "みきとP"],
    "れるりり": ["rerulili", "れるりり", "当社比p"],
    # Hololive / VTuber（osu 谱面常见）
    "星街すいせい": ["hoshimachi suisei", "星街彗星", "星街すいせい", "hoshimati suisei"],
    "湊あくあ": ["minato aqua", "湊阿库娅", "湊阿庫婭", "湊あくあ"],
    "兎田ぺこら": ["usada pekora", "兔田佩克拉", "兎田ぺこら"],
    "さくらみこ": ["sakura miko", "樱巫女", "さくらみこ"],
    "戌神ころね": ["inugami korone", "戌神沁音", "戌神ころね"],
    "白上フブキ": ["shirakami fubuki", "白上吹雪", "白上フブキ"],
    "宝鐘マリン": ["houshou marine", "宝钟玛琳", "宝鐘マリン"],
}

# 别名（小写） -> 规范名
ARTIST_ALIASES: dict[str, str] = {}
for _canon, _aliases in _ALIAS_GROUPS.items():
    for _a in _aliases:
        ARTIST_ALIASES[_a.casefold()] = _canon

# 无别名、但同样著名的艺术家（英文名，小写）
_EXTRA_FAMOUS = [
    "frums", "t+pazolite", "kobaryo", "usaO", "xi",
    "wowaka", "orangestar", "neru", "n-buna", "maretu", "kemu",
    "ryo", "40mp", "mitchie m", "kz", "livetune", "honeyworks",
    "gyari", "halyosy", "164", "last note.", "buzzg", "junky",
]

# 著名艺术家（规范化名，小写）
FAMOUS_ARTISTS: frozenset[str] = frozenset(
    [c.casefold() for c in _ALIAS_GROUPS] + [f.casefold() for f in _EXTRA_FAMOUS]
)


def canonical_artist(name: str) -> str:
    """把艺术家名归一化到规范名（英文/日文/中文等同名合并）。"""
    s = (name or "").strip()
    if not s:
        return "(未知艺术家)"
    return ARTIST_ALIASES.get(s.casefold(), s)


def is_famous(name: str) -> bool:
    """判断艺术家是否著名（归一化后是否在著名名单中）。"""
    return canonical_artist(name).casefold() in FAMOUS_ARTISTS
