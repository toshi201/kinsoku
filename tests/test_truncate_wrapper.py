"""truncate closing ANSI state (#25) and KinsokuWrapper leading spaces (#31)."""
import textwrap

import pytest

import kinsoku
from kinsoku import KinsokuWrapper

ST = "\x1b\\"
BEL = "\x07"


# --- #25: truncate closes what is open at the cut ---------------------------

def test_truncate_closes_osc8_with_st():
    s = f"\x1b]8;;https://example.com{ST}リンクのテキストです\x1b]8;;{ST}"
    assert kinsoku.truncate(s, 8) == f"\x1b]8;;https://example.com{ST}リンク\x1b]8;;{ST}…"


def test_truncate_closes_osc8_with_bel():
    s = f"\x1b]8;id=1;https://example.com{BEL}リンクのテキストです\x1b]8;;{BEL}"
    assert kinsoku.truncate(s, 8) == (
        f"\x1b]8;id=1;https://example.com{BEL}リンク\x1b]8;;{BEL}…"
    )


def test_truncate_closes_sgr_and_link():
    s = f"\x1b[31m\x1b]8;;http://x{ST}abcdefgh\x1b]8;;{ST}\x1b[0m"
    assert kinsoku.truncate(s, 5) == f"\x1b[31m\x1b]8;;http://x{ST}abcd\x1b]8;;{ST}\x1b[0m…"


def test_truncate_closes_sgr_only():
    assert kinsoku.truncate("\x1b[1mあいうえお", 6) == "\x1b[1mあい\x1b[0m…"


def test_truncate_nothing_open_adds_nothing():
    # the color is already reset before the cut
    s = "\x1b[31mab\x1b[0mcdefgh"
    assert kinsoku.truncate(s, 5) == "\x1b[31mab\x1b[0mcd…"
    # a link closed before the cut
    s = f"\x1b]8;;http://x{ST}ab\x1b]8;;{ST}cdefgh"
    assert kinsoku.truncate(s, 5) == f"\x1b]8;;http://x{ST}ab\x1b]8;;{ST}cd…"


def test_truncate_open_after_cut_is_dropped():
    # the sequences after the cut are not kept, so nothing needs closing
    assert kinsoku.truncate("abcdef\x1b[31mgh\x1b[0m", 5) == "abcd…"


@pytest.mark.parametrize("text, w, expected", [
    ("あいうえお", 6, "あい…"),
    ("abcdef", 4, "abc…"),
    ("abc", 4, "abc"),
])
def test_truncate_plain_text_unchanged(text, w, expected):
    assert kinsoku.truncate(text, w) == expected


def test_truncate_fits_is_unchanged():
    s = f"\x1b]8;;http://x{ST}abc"  # fits: returned as is, even if open
    assert kinsoku.truncate(s, 5) == s


def test_wrap_max_lines_closes_link():
    s = f"\x1b]8;;http://x{ST}あいうえおかきくけこ\x1b]8;;{ST}"
    lines = kinsoku.wrap(s, 6, max_lines=1)
    assert lines == [f"\x1b]8;;http://x{ST}あい\x1b]8;;{ST}…"]


def test_wrap_max_lines_closes_state_from_earlier_line():
    lines = kinsoku.wrap("\x1b[31mあいう\nえおかきく", 6, max_lines=2)
    assert lines == ["\x1b[31mあいう", "えお\x1b[0m…"]


def test_wrap_max_lines_nothing_open():
    lines = kinsoku.wrap("\x1b[31mあ\x1b[0mいうえおかきく", 6, max_lines=1)
    assert lines == ["\x1b[31mあ\x1b[0mい…"]


# --- #31: KinsokuWrapper never splits the first word for its leading spaces -

def test_issue_31_example():
    w = KinsokuWrapper(width=10, initial_indent="> ")
    assert w.wrap("  indented text") == ["> indented", "text"]
    assert w.wrap("  indented text") == (
        textwrap.TextWrapper(width=10, initial_indent="> ").wrap("  indented text")
    )


def test_leading_spaces_kept_when_word_fits():
    assert KinsokuWrapper(width=12, initial_indent="> ").wrap("  indented") == [">   indented"]


def test_leading_spaces_kept_for_cjk():
    assert KinsokuWrapper(width=10).wrap("  日本語のテキスト") == ["  日本語の", "テキスト"]


ASCII_LEAD = [
    "  indented text",
    "  indented text that goes on and on",
    "    deeply indented paragraph here",
    " x",
    "   supercalifragilisticexpialidocious word",
    "  ab cd ef gh ij kl mn op",
    "      lots of leading space",
    "  exactlyten more",
]


@pytest.mark.parametrize("text", ASCII_LEAD)
@pytest.mark.parametrize("w", [10, 12, 15, 20, 30])
@pytest.mark.parametrize("ind", ["", "> ", "* ", "--- "])
def test_ascii_leading_spaces_match_textwrap(text, w, ind):
    kw = dict(width=w, initial_indent=ind, subsequent_indent="  ")
    assert KinsokuWrapper(**kw).wrap(text) == textwrap.TextWrapper(**kw).wrap(text)


@pytest.mark.parametrize("text", ASCII_LEAD)
@pytest.mark.parametrize("w", [8, 10, 15])
def test_ascii_leading_spaces_match_textwrap_no_break(text, w):
    kw = dict(width=w, initial_indent="> ", break_long_words=False)
    assert KinsokuWrapper(**kw).wrap(text) == textwrap.TextWrapper(**kw).wrap(text)


@pytest.mark.parametrize("text", ["  indented text", "      lots of leading space"])
def test_body_passed_to_wrap_has_no_leading_spaces(monkeypatch, text):
    # whether kinsoku.wrap keeps or drops leading spaces must not matter:
    # KinsokuWrapper hands it a body without them, so they are never doubled
    import kinsoku.wrapper as wrapper_mod

    seen = []
    real = wrapper_mod._wrap

    def spy(t, *a, **kw):
        seen.append(t)
        return real(t, *a, **kw)

    monkeypatch.setattr(wrapper_mod, "_wrap", spy)
    KinsokuWrapper(width=10, initial_indent="> ").wrap(text)
    assert seen and all(not t.startswith(" ") for t in seen)
