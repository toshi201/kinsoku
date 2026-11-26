"""Line-break opportunities: ASCII words with infix punctuation (#22) and
halfwidth katakana / punctuation (#24)."""

import pytest

from kinsoku import NO_END, NO_START, PRESETS, shorten, width, wrap

PRESET_NAMES = list(PRESETS)


# --- #22: decimals, versions, digit grouping, URLs, file names ----------------

@pytest.mark.parametrize("rules", PRESET_NAMES)
@pytest.mark.parametrize(
    "text, w, expected",
    [
        ("最新版はv1.2.3です。", 11, ["最新版は", "v1.2.3で", "す。"]),
        ("最新版はv1.2.3です。", 13, ["最新版は", "v1.2.3です。"]),
        ("価格は1,000,000円です", 12, ["価格は", "1,000,000円", "です"]),
        ("円周率は3.14です", 9, ["円周率は", "3.14です"]),
        ("開始は12:30です", 9, ["開始は", "12:30です"]),
        (
            "詳細はhttps://example.com/docsを参照してください",
            24,
            ["詳細は", "https://example.com/docs", "を参照してください"],
        ),
        (
            "設定は config.yaml の timeout: 30 を参照",
            16,
            ["設定は", "config.yaml の", "timeout: 30 を参", "照"],
        ),
    ],
)
def test_ascii_word_with_infix_punctuation(rules, text, w, expected):
    assert wrap(text, w, rules=rules) == expected


@pytest.mark.parametrize(
    "token", ["v1.2.3", "1,000,000", "3.14", "https://example.com/a/b", "config.yaml"]
)
@pytest.mark.parametrize("rules", PRESET_NAMES)
def test_token_never_split_when_it_fits(token, rules):
    text = "あいうえお" + token + "かきくけこ"
    for w in range(width(token), width(text) + 1):
        lines = wrap(text, w, rules=rules)
        assert any(token in line for line in lines), (w, lines)


def test_long_url_still_broken_with_break_long_words():
    url = "https://example.com/docs/guide.html"
    lines = wrap("詳細は" + url + "を参照", 20)
    assert all(width(line) <= 20 for line in lines)
    assert "".join(lines) == "詳細は" + url + "を参照"
    assert wrap("詳細は" + url, 20, break_long_words=False) == ["詳細は", url]


def test_trailing_punctuation_still_follows_kinsoku():
    # "." after the word (not followed by an ASCII word char) is separate
    assert wrap("版はv1.2.3.です", 9) == ["版は", "v1.2.3.で", "す"]
    assert wrap("end. Next", 5, hanging=True) == ["end.", "Next"]
    # Japanese punctuation is unchanged
    assert wrap("あいう。えお", 6) == ["あい", "う。え", "お"]


def test_infix_inside_ruby_text():
    assert wrap("漢字《かんじ》はv1.2.3です", 12, ruby=True) == [
        "漢字《かんじ》", "はv1.2.3です",
    ]


# --- #24: halfwidth katakana and punctuation -----------------------------------

@pytest.mark.parametrize("rules", ["ja", "strict", "loose"])
def test_halfwidth_punctuation_in_presets(rules):
    r = PRESETS[rules]
    for ch in "｡､｣･ﾞﾟ":
        assert ch in r.no_start
    assert "｢" in r.no_end
    assert ("ｰ" in r.no_start) == (rules != "loose")


def test_halfwidth_in_module_constants():
    assert set("｡､｣･ｰﾞﾟ") <= NO_START
    assert "｢" in NO_END


@pytest.mark.parametrize(
    "text, w",
    [
        ("あいう｡えお", 6),
        ("あい｢うえ｣お", 6),
        ("ﾃﾞｨｽﾌﾟﾚｲの表示｡ｱｲｳ｣", 6),
        ("ｱｲｳ､ｴｵ･ｶｷｰｸ", 3),
    ],
)
def test_halfwidth_kinsoku(text, w):
    lines = wrap(text, w)
    assert "".join(lines) == text
    for line in lines:
        assert width(line) <= w
        assert line[0] not in NO_START, lines
        assert line[-1] not in NO_END, lines


def test_halfwidth_examples():
    assert wrap("あいう｡えお", 6) == ["あい", "う｡え", "お"]
    assert wrap("あい｢うえ｣お", 6) == ["あい", "｢うえ｣", "お"]
    assert wrap("ﾃﾞｨｽﾌﾟﾚｲの表示｡ｱｲｳ｣", 6) == ["ﾃﾞｨｽﾌﾟ", "ﾚｲの表", "示｡ｱｲ", "ｳ｣"]


def test_halfwidth_kana_break_per_character():
    assert wrap("ｱｲｳｴｵｶｷｸｹｺ", 4) == ["ｱｲｳｴ", "ｵｶｷｸ", "ｹｺ"]
    assert wrap("ｱｲｳｴｵｶｷｸｹｺ", 4, break_long_words=False) == ["ｱｲｳｴ", "ｵｶｷｸ", "ｹｺ"]
    # keep_all still only breaks at spaces
    assert wrap("ｱｲｳ ｴｵ", 3, keep_all=True) == ["ｱｲｳ", "ｴｵ"]
    # loose lets ｰ start a line
    assert wrap("ｱｲｰｳ", 2, rules="loose") == ["ｱｲ", "ｰｳ"]
    assert wrap("ｱｲｰｳ", 2) == ["ｱ", "ｲｰ", "ｳ"]


@pytest.mark.parametrize("rules", PRESET_NAMES)
@pytest.mark.parametrize("w", range(1, 12))
def test_sound_marks_never_separated(rules, w):
    text = "ﾃﾞｨｽﾌﾟﾚｲﾊﾟﾊﾞﾋﾞﾌﾞ"
    for line in wrap(text, w, rules=rules):
        assert line[0] not in "ﾞﾟ", (w, line)
    for line in wrap("abcﾃﾞﾃﾞﾃﾞ", w, rules=rules):
        assert line[0] not in "ﾞﾟ", (w, line)


def test_sound_mark_kept_by_shorten():
    assert shorten("ｱｲｳﾃﾞｽ", 5) == "ｱｲｳ…"
    assert shorten("ｱｲﾃﾞｽｸ", 5) == "ｱｲﾃﾞ…"
