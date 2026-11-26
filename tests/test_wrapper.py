import textwrap

import pytest

import kinsoku
from kinsoku import KinsokuWrapper, width

TEXT = "吾輩は猫である。名前はまだ無い。どこで生れたかとんと見当がつかぬ。"


def test_exports():
    assert kinsoku.KinsokuWrapper is KinsokuWrapper
    assert kinsoku.dedent is textwrap.dedent
    assert kinsoku.indent is textwrap.indent
    assert kinsoku.indent("a\n\nb", "> ") == "> a\n\n> b"
    assert kinsoku.indent("a\nb", "> ", lambda l: l.startswith("b")) == "a\n> b"
    assert kinsoku.dedent("  a\n  b") == "a\nb"


def test_is_textwrapper():
    assert isinstance(KinsokuWrapper(), textwrap.TextWrapper)


def test_defaults_match_textwrap():
    k, t = KinsokuWrapper(), textwrap.TextWrapper()
    for name in (
        "width",
        "initial_indent",
        "subsequent_indent",
        "expand_tabs",
        "replace_whitespace",
        "fix_sentence_endings",
        "break_long_words",
        "drop_whitespace",
        "break_on_hyphens",
        "tabsize",
        "max_lines",
        "placeholder",
    ):
        assert getattr(k, name) == getattr(t, name), name
    assert k.hanging is False and k.keep_all is False and k.ambiguous_width == 1


def test_accepts_all_textwrap_args_positionally():
    w = KinsokuWrapper(
        20, "> ", "  ", True, True, True, True, False, False, 4, max_lines=3, placeholder="…"
    )
    assert (w.width, w.tabsize, w.max_lines) == (20, 4, 3)


@pytest.mark.parametrize("w", [6, 10, 20, 33])
def test_same_as_wrap(w):
    assert KinsokuWrapper(width=w).wrap(TEXT) == kinsoku.wrap(TEXT, w)
    assert KinsokuWrapper(width=w).fill(TEXT) == kinsoku.fill(TEXT, w)


def test_same_as_wrap_with_options():
    text = "あいう。えお\nかきくけこさしす"
    opts = dict(initial_indent="　", subsequent_indent="", hanging=True)
    w = KinsokuWrapper(6, replace_whitespace=False, **opts)
    assert w.wrap(text) == kinsoku.wrap(text, 6, **opts)


def test_replace_whitespace_joins_paragraphs():
    text = "あいう\nえお"
    assert KinsokuWrapper(20).wrap(text) == ["あいう えお"]
    assert KinsokuWrapper(20, replace_whitespace=False).wrap(text) == ["あいう", "えお"]


def test_mutable_attributes():
    w = KinsokuWrapper(width=40)
    assert w.wrap(TEXT) == kinsoku.wrap(TEXT, 40)
    w.width = 10
    w.hanging = True
    assert w.wrap(TEXT) == kinsoku.wrap(TEXT, 10, hanging=True)
    w.max_lines = 2
    w.placeholder = "…"
    assert w.wrap(TEXT) == kinsoku.wrap(TEXT, 10, hanging=True, max_lines=2)


def test_empty_and_whitespace():
    assert KinsokuWrapper().wrap("") == []
    assert KinsokuWrapper().wrap("  \n\t ") == []
    assert KinsokuWrapper().fill("") == ""


def test_expand_tabs_by_display_width():
    w = KinsokuWrapper(width=40, tabsize=8)
    # "日本" is 4 columns wide, so the tab advances to column 8.
    assert w.wrap("日本\tabc") == ["日本    abc"]
    assert width(w.wrap("日本語の\tx")[0]) == 17  # 8 cols -> next stop 16
    assert w.wrap("ab\tc") == ["ab\tc".expandtabs()]
    assert KinsokuWrapper(40, tabsize=4).wrap("あ\tb") == ["あ  b"]


def test_expand_tabs_per_line():
    w = KinsokuWrapper(40, replace_whitespace=False)
    assert w.wrap("日本\tx\nあ\ty") == ["日本    x", "あ      y"]


def test_expand_tabs_false():
    w = KinsokuWrapper(40, expand_tabs=False, replace_whitespace=False)
    # kinsoku.wrap() itself expands remaining tabs by display width (#29)
    assert w.wrap("a\tb") == ["a       b"]
    # with replace_whitespace each tab becomes a single space (like textwrap)
    assert KinsokuWrapper(40, expand_tabs=False).wrap("a\tb") == ["a b"]


@pytest.mark.parametrize(
    "text",
    [
        "The quick brown fox jumps over the lazy dog.",
        "Hello world, this is a simple test of the wrapper.",
        "a\tb\tc d e f g h i j k l m n",
        "line one\nline two\nline three is longer",
        "  leading spaces are kept",
        "supercalifragilisticexpialidocious is long",
    ],
)
@pytest.mark.parametrize("w", [10, 15, 20, 40])
def test_ascii_matches_textwrap(text, w):
    assert KinsokuWrapper(width=w).wrap(text) == textwrap.TextWrapper(width=w).wrap(text)


def test_ascii_indents_match_textwrap():
    text = "The quick brown fox jumps over the lazy dog again and again."
    kw = dict(width=20, initial_indent="* ", subsequent_indent="  ")
    assert KinsokuWrapper(**kw).wrap(text) == textwrap.TextWrapper(**kw).wrap(text)


def test_max_lines_placeholder():
    w = KinsokuWrapper(width=10, max_lines=2, placeholder="…")
    lines = w.wrap(TEXT)
    assert lines == kinsoku.wrap(TEXT, 10, max_lines=2)
    assert len(lines) == 2 and lines[-1].endswith("…")
    # textwrap's default placeholder
    lines = KinsokuWrapper(width=12, max_lines=2).wrap(TEXT)
    assert lines[-1].endswith(" [...]")
    assert all(width(l) <= 12 for l in lines)


def test_kinsoku_specific_options():
    w = KinsokuWrapper(12, keep_all=True)
    assert w.wrap("대한민국의 수도는 서울입니다") == ["대한민국의", "수도는", "서울입니다"]
    assert KinsokuWrapper(6, ambiguous_width=2).wrap("○○○○") == ["○○○", "○"]


def test_extra_kwargs_forwarded(monkeypatch):
    import kinsoku.wrapper as mod

    seen = {}

    def fake_wrap(text, width, **kwargs):
        seen.update(kwargs)
        return [text]

    monkeypatch.setattr(mod, "_wrap", fake_wrap)
    w = KinsokuWrapper(10, rules="strict", ruby=True)
    assert w.extra == {"rules": "strict", "ruby": True}
    w.wrap("abc")
    assert seen["rules"] == "strict" and seen["ruby"] is True


def test_unknown_extra_kwarg_raises_on_wrap():
    with pytest.raises(TypeError):
        KinsokuWrapper(10, no_such_option=1).wrap("abc")


def test_ignored_options_accepted():
    w = KinsokuWrapper(10, fix_sentence_endings=True, break_on_hyphens=False, drop_whitespace=False)
    assert w.wrap("あいうえおかきくけこ") == kinsoku.wrap("あいうえおかきくけこ", 10)


def test_invalid_width():
    with pytest.raises(ValueError):
        KinsokuWrapper(width=0).wrap("abc")
