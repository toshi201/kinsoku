"""NFD Hangul clusters (#44) and grapheme clusters in tategaki (#45)."""

import unicodedata

import pytest

import kinsoku
from kinsoku import char_width, pad, tategaki, truncate, width, wrap
from kinsoku._core import _clusters, _clusters_plain

FS = "　"


def nfd(s):
    return unicodedata.normalize("NFD", s)


def nfc(s):
    return unicodedata.normalize("NFC", s)


KO = [
    "한국어 텍스트입니다",
    "각",
    "안녕하세요 반갑습니다",
    "닭갈비와 삼겹살을 먹었다",
    "가나다라마바사아자차카타파하",
]


# --- #44: widths ------------------------------------------------------------


def test_jamo_char_widths():
    assert [char_width(c) for c in nfd("각")] == [2, 0, 0]
    assert char_width("ᄀ") == 2  # L
    assert char_width("ꥠ") == 2  # L, Jamo Extended-A
    assert char_width("ᅡ") == 0  # V
    assert char_width("ᅠ") == 0  # V filler
    assert char_width("ᆨ") == 0  # T
    assert char_width("ힰ") == 0  # V, Jamo Extended-B
    assert char_width("ퟋ") == 0  # T, Jamo Extended-B


@pytest.mark.parametrize("s", KO)
@pytest.mark.parametrize("aw", [1, 2])
def test_nfd_width_matches_nfc(s, aw):
    assert width(nfd(s), aw) == width(s, aw)


def test_width_with_ansi_and_emoji_sequences():
    s = nfd("한글") + "👨‍👩‍👧"
    assert width(s) == 6
    assert width("\x1b[31m" + s + "\x1b[0m") == 6


# --- #44: clusters ----------------------------------------------------------


@pytest.mark.parametrize("s", KO)
def test_nfd_clusters_are_syllables(s):
    d = nfd(s)
    cls = list(_clusters(d))
    assert [nfc(c) for c in cls] == list(s)
    assert list(_clusters_plain(d)) == cls


def test_uax29_hangul_rules():
    L, L2, V, T = "ᄀ", "ᄂ", "ᅡ", "ᆨ"
    # L × (L | V | LV | LVT)
    assert list(_clusters(L + L2 + V)) == [L + L2 + V]
    assert list(_clusters(L + "가")) == [L + "가"]
    assert list(_clusters(L + "각")) == [L + "각"]
    # LV × (V | T), LVT × T
    assert list(_clusters("가" + V + T)) == ["가" + V + T]
    assert list(_clusters("각" + T)) == ["각" + T]
    # syllables do not join each other
    assert list(_clusters("가각")) == ["가", "각"]
    assert list(_clusters(L + V + L2 + V)) == [L + V, L2 + V]
    # extension blocks
    assert list(_clusters("ꥠힰퟋ")) == ["ꥠힰퟋ"]
    # a leading consonant does not join non-Hangul
    assert list(_clusters(L + "a")) == [L, "a"]


def test_clusters_with_ansi_inside_syllable():
    d = nfd("각")
    s = d[0] + "\x1b[31m" + d[1:] + "\x1b[0m"
    assert len(list(_clusters(s))) == 1


# --- #44: wrap / truncate / pad never split a syllable -----------------------


@pytest.mark.parametrize("s", KO)
@pytest.mark.parametrize("w", range(2, 13))
def test_wrap_nfd_matches_nfc(s, w):
    lines = wrap(nfd(s), w)
    assert [nfc(x) for x in lines] == wrap(s, w)
    for line in lines:
        assert unicodedata.category(line[0]) != "Lo" or not ("ᅠ" <= line[0] <= "ᇿ")
        assert width(line) <= w


def test_wrap_issue_example():
    d = nfd("한국어 텍스트입니다")
    assert width(d) == 19
    assert [nfc(x) for x in wrap(d, 8)] == wrap("한국어 텍스트입니다", 8)


@pytest.mark.parametrize("s", KO)
@pytest.mark.parametrize("w", range(1, 14))
def test_truncate_nfd_matches_nfc(s, w):
    assert nfc(truncate(nfd(s), w)) == truncate(s, w)


@pytest.mark.parametrize("s", KO)
@pytest.mark.parametrize("align", ["left", "right", "center"])
def test_pad_nfd_matches_nfc(s, align):
    w = width(s) + 3
    out = pad(nfd(s), w, align=align)
    assert width(out) == w
    assert nfc(out) == pad(s, w, align=align)


# --- #45: tategaki ------------------------------------------------------------


def rows(out):
    return out.split("\n")


def assert_aligned(out):
    assert len({width(r) for r in rows(out)}) == 1, out


@pytest.mark.parametrize(
    "seq",
    [
        "👨‍👩‍👧",  # ZWJ
        "🇯🇵",  # flag
        "👍🏽",  # skin tone
        "1️⃣",  # keycap
        "❤️",  # VS16
        "🏴󠁧󠁢󠁥󠁮󠁧󠁿",  # tag sequence
    ],
)
def test_tategaki_emoji_one_cell(seq):
    out = tategaki(seq + "あ", 2)
    assert rows(out) == [seq, "あ"]
    assert_aligned(out)


def test_tategaki_issue_example():
    out = tategaki("😀👨‍👩‍👧🇯🇵", 2)
    assert rows(out) == ["🇯🇵 😀", FS + " 👨‍👩‍👧"]
    assert_aligned(out)


@pytest.mark.parametrize("halfwidth", ["fullwidth", "pair"])
def test_tategaki_emoji_both_modes(halfwidth):
    out = tategaki("ab👨‍👩‍👧🇯🇵", 4, halfwidth=halfwidth)
    assert "👨‍👩‍👧" in out and "🇯🇵" in out
    assert_aligned(out)


def test_tategaki_nfd_hangul_one_cell():
    out = tategaki(nfd("한글"), 3)
    assert [nfc(r) for r in rows(out)] == ["한", "글", FS]
    assert_aligned(out)
    assert nfc(tategaki(nfd("안녕하세요"), 2)) == tategaki("안녕하세요", 2)


def test_tategaki_combining_mark_stays_with_base():
    out = tategaki("がき", 2)
    assert rows(out) == ["が", "き"]
    out = tategaki("éx", 2)
    assert rows(out) == ["ｅ́", "ｘ"]
    assert_aligned(out)


def test_tategaki_halfwidth_kana_fullwidth():
    out = tategaki("ｱｲｶﾞﾊﾟｰ", 5)
    assert rows(out) == ["ア", "イ", "ガ", "パ", "｜"]
    # no precomposed form: base + combining sound mark in one cell
    out = tategaki("ｱﾞ", 1)
    assert out == "ア゙"
    assert_aligned(tategaki("ｱｲｳｶﾞ｡", 2))


def test_tategaki_halfwidth_kana_kinsoku_on_original():
    # ｯ must not start a column (judged on the original char)
    assert "ｯ" in kinsoku.NO_START
    out = tategaki("ｱｲｯ", 2, hanging=False)
    assert rows(out) == ["イ ア", "ッ " + FS]


def test_tategaki_pair_mode_keeps_halfwidth_kana():
    out = tategaki("ｱ", 1, halfwidth="pair")
    assert out == "ｱ "
