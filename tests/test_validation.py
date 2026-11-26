"""Argument validation is shared by every public function (#30, #41)."""

import pytest

import kinsoku
from kinsoku import KinsokuWrapper

AW_MSG = "ambiguous_width must be 1 or 2, not {!r}"
WIDTH_MSG = "invalid width {!r} (must be > 0)"
WIDTH0_MSG = "invalid width {!r} (must be >= 0)"
ALIGN_MSG = "unknown align {!r} (choose from left, right, center)"


def _raises(call, msg):
    with pytest.raises(ValueError) as e:
        call()
    assert str(e.value) == msg


# --- ambiguous_width ----------------------------------------------------------

AW_CALLS = {
    "width": lambda aw: kinsoku.width("○", aw),
    "width_ascii": lambda aw: kinsoku.width("abc", aw),
    "char_width": lambda aw: kinsoku.char_width("○", aw),
    "char_width_ascii": lambda aw: kinsoku.char_width("a", aw),
    "wrap": lambda aw: kinsoku.wrap("○", 10, ambiguous_width=aw),
    "fill": lambda aw: kinsoku.fill("○", 10, ambiguous_width=aw),
    "shorten": lambda aw: kinsoku.shorten("○", 10, ambiguous_width=aw),
    "truncate": lambda aw: kinsoku.truncate("○○○", 2, ambiguous_width=aw),
    "truncate_fits": lambda aw: kinsoku.truncate("○", 10, ambiguous_width=aw),
    "pad": lambda aw: kinsoku.pad("○", 5, ambiguous_width=aw),
    "pad_no_gap": lambda aw: kinsoku.pad("○○○", 2, ambiguous_width=aw),
    "table": lambda aw: kinsoku.table([["○"]], ambiguous_width=aw),
    "rewrap": lambda aw: kinsoku.rewrap("○", 10, ambiguous_width=aw),
    "rewrap_empty": lambda aw: kinsoku.rewrap("", 10, ambiguous_width=aw),
    "wrapper_wrap": lambda aw: KinsokuWrapper(10, ambiguous_width=aw).wrap("○"),
    "wrapper_fill": lambda aw: KinsokuWrapper(10, ambiguous_width=aw).fill("○"),
    "wrapper_empty": lambda aw: KinsokuWrapper(10, ambiguous_width=aw).wrap(""),
    "wrapper_tab": lambda aw: KinsokuWrapper(10, ambiguous_width=aw).wrap("\t○"),
}


@pytest.mark.parametrize("aw", [0, 3, -1, "2", None])
@pytest.mark.parametrize("name", list(AW_CALLS))
def test_bad_ambiguous_width(name, aw):
    _raises(lambda: AW_CALLS[name](aw), AW_MSG.format(aw))


@pytest.mark.parametrize("aw", [1, 2])
@pytest.mark.parametrize("name", list(AW_CALLS))
def test_good_ambiguous_width(name, aw):
    AW_CALLS[name](aw)


# --- width --------------------------------------------------------------------

WIDTH_CALLS = {
    "wrap": lambda w: kinsoku.wrap("abc", w),
    "wrap_empty": lambda w: kinsoku.wrap("", w),
    "fill": lambda w: kinsoku.fill("abc", w),
    "shorten": lambda w: kinsoku.shorten("abc", w),
    "rewrap": lambda w: kinsoku.rewrap("abc", w),
    "table": lambda w: kinsoku.table([["abc"]], width=w),
    "wrapper_wrap": lambda w: KinsokuWrapper(w).wrap("abc"),
    "wrapper_fill": lambda w: KinsokuWrapper(w).fill("abc"),
    "wrapper_empty": lambda w: KinsokuWrapper(w).wrap(""),
}


@pytest.mark.parametrize("w", [0, -1])
@pytest.mark.parametrize("name", list(WIDTH_CALLS))
def test_bad_width(name, w):
    _raises(lambda: WIDTH_CALLS[name](w), WIDTH_MSG.format(w))


# pad and truncate accept 0 columns (e.g. an empty table column)
WIDTH0_CALLS = {
    "pad": lambda w: kinsoku.pad("abc", w),
    "pad_empty": lambda w: kinsoku.pad("", w),
    "truncate": lambda w: kinsoku.truncate("abc", w, ""),
    "truncate_empty": lambda w: kinsoku.truncate("", w),
}


@pytest.mark.parametrize("w", [-1, -10])
@pytest.mark.parametrize("name", list(WIDTH0_CALLS))
def test_bad_width_allow_zero(name, w):
    _raises(lambda: WIDTH0_CALLS[name](w), WIDTH0_MSG.format(w))


@pytest.mark.parametrize("name", list(WIDTH0_CALLS))
def test_zero_width_allowed(name):
    WIDTH0_CALLS[name](0)


def test_tategaki_height_and_gap():
    _raises(lambda: kinsoku.tategaki("あ", 0), "invalid height 0 (must be > 0)")
    _raises(lambda: kinsoku.tategaki("あ", 2, gap=-1), "invalid gap -1 (must be >= 0)")


# --- align --------------------------------------------------------------------

ALIGN_CALLS = {
    "pad": lambda a: kinsoku.pad("abc", 5, a),
    "pad_no_gap": lambda a: kinsoku.pad("abc", 2, a),
    "pad_exact": lambda a: kinsoku.pad("abc", 3, a),
    "table": lambda a: kinsoku.table([["abc"]], align=a),
    "table_list": lambda a: kinsoku.table([["abc", "d"]], align=["left", a]),
}


@pytest.mark.parametrize("align", ["middle", "LEFT", "", "=="])
@pytest.mark.parametrize("name", list(ALIGN_CALLS))
def test_bad_align(name, align):
    _raises(lambda: ALIGN_CALLS[name](align), ALIGN_MSG.format(align))


def test_pad_align_none():
    # None means "default" only for table(); pad() needs a real value
    _raises(lambda: kinsoku.pad("abc", 2, None), ALIGN_MSG.format(None))
    assert kinsoku.table([["a"]], align=None) == kinsoku.table([["a"]])


@pytest.mark.parametrize("align,alias", [("left", "<"), ("right", ">"), ("center", "^")])
def test_align_aliases(align, alias):
    assert kinsoku.pad("あ", 5, alias) == kinsoku.pad("あ", 5, align)
    assert kinsoku.table([["あ"], ["abcd"]], align=alias) == kinsoku.table(
        [["あ"], ["abcd"]], align=align
    )


def test_table_markdown_alias():
    assert kinsoku.table([["a"]], headers=["h"], style="markdown", align=">") == (
        kinsoku.table([["a"]], headers=["h"], style="markdown", align="right")
    )


# --- a wide character in width=1 ----------------------------------------------

def test_wide_char_overflows_width_1():
    # documented: a cluster is never split, so it gets a line of its own
    assert kinsoku.wrap("あいう", 1) == ["あ", "い", "う"]
    assert kinsoku.wrap("aあb", 1) == ["a", "あ", "b"]


def test_pad_does_not_cut():
    assert kinsoku.pad("あいう", 4) == "あいう"
    assert kinsoku.pad(kinsoku.truncate("あいう", 4), 4) == "あ… "


# --- tabs in pad / truncate (#41) ---------------------------------------------

@pytest.mark.parametrize("text", ["a\tb", "日本\tc", "\t", "ab\t\tc"])
@pytest.mark.parametrize("tabsize", [8, 4, 1])
def test_pad_expands_tabs(text, tabsize):
    out = kinsoku.pad(text, 20, tabsize=tabsize)
    assert "\t" not in out
    assert kinsoku.width(out) == 20
    assert out.rstrip(" ") == kinsoku._core._expand_tabs(text, tabsize, 1).rstrip(" ")


def test_pad_tab_width():
    assert kinsoku.pad("日本\tx", 10) == "日本    x "
    assert kinsoku.pad("日本\tx", 10, "right", tabsize=3) == "   日本  x"


def test_truncate_expands_tabs():
    assert kinsoku.truncate("日本\tx", 9) == "日本    x"
    assert kinsoku.truncate("日本\txyz", 9) == "日本    …"
    assert kinsoku.truncate("a\tb", 10, tabsize=4) == "a   b"
    out = kinsoku.truncate("あ\tいうえお\tかき", 12)
    assert "\t" not in out and kinsoku.width(out) <= 12


@pytest.mark.parametrize("tabsize", [8, 4, 2])
def test_truncate_tab_width_matches_width(tabsize):
    text = "日本\tabc\tあ"
    w = kinsoku.width(text, tabsize=tabsize)
    assert kinsoku.truncate(text, w, tabsize=tabsize) == kinsoku._core._expand_tabs(
        text, tabsize, 1
    )
    assert kinsoku.width(kinsoku.truncate(text, w - 1, tabsize=tabsize)) <= w - 1


def test_wrapper_uses_core_expand_tabs():
    import kinsoku.wrapper as wrapper_mod

    assert not hasattr(wrapper_mod, "_expandtabs")
    assert KinsokuWrapper(40).wrap("日本\tx") == ["日本    x"]
