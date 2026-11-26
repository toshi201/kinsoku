"""Emoji grapheme clusters and their display width (#23)."""

import pytest

import kinsoku
from kinsoku._core import _clusters

FAMILY = "\U0001F468‍\U0001F469‍\U0001F467"  # 👨‍👩‍👧
THUMBS_SKIN = "\U0001F44D\U0001F3FD"  # 👍🏽
RAINBOW_FLAG = "\U0001F3F3️‍\U0001F308"  # 🏳️‍🌈
KEYCAP_1 = "1️⃣"  # 1️⃣
KEYCAP_HASH = "#️⃣"  # #️⃣
HEART = "❤️"  # ❤️
WARNING = "⚠️"  # ⚠️
JP = "\U0001F1EF\U0001F1F5"  # 🇯🇵
US = "\U0001F1FA\U0001F1F8"
FR = "\U0001F1EB\U0001F1F7"
DE = "\U0001F1E9\U0001F1EA"
ENGLAND = "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F"

EMOJI_CLUSTERS = [
    FAMILY, THUMBS_SKIN, RAINBOW_FLAG, KEYCAP_1, KEYCAP_HASH,
    HEART, WARNING, JP, ENGLAND, "\U0001F44D", "\U0001F600",
]


@pytest.mark.parametrize("s", EMOJI_CLUSTERS)
def test_emoji_cluster_is_one_cluster_of_width_2(s):
    assert list(_clusters(s)) == [s]
    assert kinsoku.width(s) == 2


@pytest.mark.parametrize("s", EMOJI_CLUSTERS)
def test_emoji_cluster_with_ansi(s):
    t = "\x1b[31m" + s + "\x1b[0m"
    assert kinsoku.width(t) == 2
    assert len(list(_clusters(t))) == 1


@pytest.mark.parametrize(
    "s, w",
    [
        ("☺︎", 1),  # ☺︎ text presentation keeps its own width
        ("⌚︎", 2),  # ⌚︎ is East Asian Wide on its own
        ("❤", 1),  # ❤ without VS16
        ("❤︎", 1),
        ("\U0001F1EF", 1),  # a lone regional indicator
        ("a‍\U0001F44D", 3),  # not an emoji ZWJ sequence
        ("1⃣", 2),  # keycap without VS16
        ("é", 1),
        ("か゚", 2),
    ],
)
def test_other_widths(s, w):
    assert kinsoku.width(s) == w


def test_mixed_text_width():
    assert kinsoku.width("家族" + FAMILY + "と" + JP + "旅行" + HEART) == 4 + 2 + 2 + 2 + 4 + 2


def test_flags_pair_up_in_order():
    assert list(_clusters(JP + US + FR + "\U0001F1E9")) == [JP, US, FR, "\U0001F1E9"]


def test_wrap_never_splits_flags():
    assert kinsoku.wrap(JP + US + FR + DE, 3) == [JP, US, FR, DE]
    assert kinsoku.wrap(JP + US + FR + DE, 4) == [JP + US, FR + DE]


def test_truncate_never_splits_flags():
    assert kinsoku.truncate(JP + US + FR, 4) == JP + "…"
    assert kinsoku.truncate(JP + US + FR, 5) == JP + US + "…"


@pytest.mark.parametrize("s", EMOJI_CLUSTERS)
def test_wrap_and_truncate_keep_clusters_whole(s):
    text = s * 5
    for w in (2, 3, 5):
        lines = kinsoku.wrap(text, w)
        assert "".join(lines) == text
        for line in lines:
            assert kinsoku.width(line) <= w
            assert set(_clusters(line)) == {s}
    out = kinsoku.truncate(text, 6)
    assert out == s * 2 + "…"
    assert kinsoku.width(out) == 5


@pytest.mark.parametrize("s", EMOJI_CLUSTERS)
def test_pad(s):
    out = kinsoku.pad(s, 5)
    assert out == s + "   "
    assert kinsoku.width(out) == 5
    assert kinsoku.pad(s, 6, "center") == "  " + s + "  "


def test_width_is_sum_of_cluster_widths():
    text = "あ" + FAMILY + "abc" + THUMBS_SKIN + KEYCAP_1 + JP + "☺︎" + HEART + "é"
    assert kinsoku.width(text) == sum(kinsoku.width(c) for c in _clusters(text))
