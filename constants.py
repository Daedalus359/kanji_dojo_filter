VERB_SAMPLES = [
    # verbs of various types
    ("いる", "いる"),
    ("ある", "ある"),
    ("来る", "くる"),
    ("する", "する"),
    ("食べる", "たべる"),
    ("買う", "かう"),
    ("待つ", "まつ"),
    ("取る", "とる"),
    ("読む", "よむ"),
    ("遊ぶ", "あそぶ"),
    ("書く", "かく"),
    ("行く", "いく"),
    ("急ぐ", "いそぐ"),
    ("話す", "はなす"),
]

CHANGE_TO_KANA_WORDS = [
    ("後", "のち"),  # usu-kana for 2 of 3 non-archaic senses
    ("出来るだけ", "できるだけ"),  # straightforward usu-kana
    ("出来る丈", "できるだけ"), #another form of above  
]

CHANGE_TO_ANOTHER_KANJI_FORM = {
    ("楽む", "たのしむ"): "楽しむ",  # redirects straight to 楽しむ -- seems to be no entry in JMDict, so find where this comes from
    ("下る", "さがる"): "下がる",
    ("後", "うしろ"): "後ろ",
    ("明い", "あかるい"): "明るい",
    ("曲る", "まがる"): "曲がる",#曲る -> 曲がる
    
}

QUESTIONABLE_CHANGES = {
    ("ニ十日", "はつか"): "20日"# more commonly written ２０日-- can I use Arabic numerals? Look through the DB. Number kanji would be a common thing to replace
}

HAS_MULTIPLE_COMMON_ALT_READINGS = [
    # alternate reading pairs where both are used frequently, but maybe some more frequently
    ("言う", "いう"),
    ("言う", "ゆう"),
    ("行き", "ゆき"),
    ("行き", "いき"),
    ("明後日", "あさって"),
    ("明後日", "みょうごにち"),
    ("明日", "あす"),  # a "special reading"
    ("明日", "あした"),
    ("明日", "みょうにち"),
]

SAMPLE_WORDS = [
    ("生け花", "いけばな"),  # contains a table of common and uncommon writings / readings
    ("化け物", "ばけもの"),  # has the same kind of table of readings / writing as above
    ("答え", "こたえ"),  # JMDict(?) lists forms without any evaluations of regularity and no varying readings
    ("食う", "くう"),  # looking for "masculine" tag or something
] + HAS_MULTIPLE_COMMON_ALT_READINGS + list(CHANGE_TO_ANOTHER_KANJI_FORM) + list(QUESTIONABLE_CHANGES) + CHANGE_TO_KANA_WORDS + VERB_SAMPLES 



NORMAL_TAGS = frozenset({
    "n", "adv", "adj-no", "uk", "exp", "col", "sl",
    "suf", "n-suf", "male", "vulg",
    "v1", "v5", "v5u", "v5s", "v5g", "v5k", "v5b",
    "v5m", "v5t", "v5r", "v5k-s", "vs-i", "vk",
    "aux-v", "vt", "vi", "baseb",
})

VERB_TYPES = frozenset({"v1", "v5", "vs", "vk"})

USUALLY_ENTRIES = frozenset({
    "gikun", "news2k", "news3k", "news5k", "news6k",
    "news8k", "news9k", "news11k", "news13k",
    "news17k", "news21k",
})

#tags that indicate the word sense is not worth learning
#used to remove unimportant JMDict senses from weighing on the evaluation of an (expression, reading) pair
LOW_PRIORITY_SENSE_INDICATOR_TAGS = [
    "arch",#archaic
]

SCORING_CONSTS = {
    "uk_tag_kanji_word": 1.0,
}

JPDB_RECOMMEND_DELAY_FREQ_RANK = 18000
JPDB_CUTOFF_FREQ_RANK = 24000


#worth considering whether these make a word sense worth valuing over others
# HIGH_PRIORITY_SENSE_INDICATOR_TAGS = [
#     "⭐",
# ]

# #make another named list for this? Not sure if I need it.
# [
# "uk",#usually written with kana alone
# ]