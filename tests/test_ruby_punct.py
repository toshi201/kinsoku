"""#63: ruby units glued to punctuation / brackets by kinsoku.

With ``break_long_words=True`` width wins: a kinsoku block with ruby that
fits on no line loses its ruby (widest first) and is wrapped like ordinary
text.  With ``break_long_words=False`` kinsoku wins and the line overflows.
"""

import pytest

from kinsoku import (
    KinsokuWrapper,
    fill,
    rewrap,
    shorten,
    strip_ansi,
    strip_ruby,
    table,
    width,
    wrap,
)
from kinsoku._core import NO_END

TEXTS = [
    "「鬼《おに》」と言った",
    "彼は「鬼《おに》」と呼ばれた",
    "「｜魔法少女《まほうしょうじょ》」と言った",
    "「｜吾輩《わがはい》」は猫である。",
    "漢字《かんじ》。それから漢字《かんじ》、",
    "彼女は「｜魔法少女《マジカルガール》」になった。",
    "（｜東京《とうきょう》）「漢字《かんじ》」――「鬼《おに》」。",
    "\x1b[31m「鬼《おに》」\x1b[0mと言った",
]
WIDTHS = range(6, 34)


def _body(lines):
    return "".join(strip_ruby(strip_ansi(x)) for x in lines).replace("…", "")


def _no_lone_open(lines):
    for x in lines:
        v = strip_ansi(x)
        assert not (v and all(c in NO_END for c in v)), lines


# --- the issue's examples ----------------------------------------------------


def test_issue_shorten():
    s = shorten("「鬼《おに》」と言った", 10, ruby=True)
    assert s != "…"
    assert width(s) <= 10
    assert s == "「鬼」と…"


def test_issue_lone_open_bracket():
    lines = wrap("彼は「鬼《おに》」と呼ばれた", 10, ruby=True)
    assert lines == ["彼は「鬼」", "と呼ばれた"]


def test_issue_max_lines_long_ruby():
    lines = wrap("「｜魔法少女《まほうしょうじょ》」と言った", 30, ruby=True, max_lines=1)
    assert lines != ["…"]
    assert all(width(x) <= 30 for x in lines)


def test_issue_table():
    out = table([["彼は「鬼《おに》」と呼ばれた", "x"]], max_col_width=10, ruby=True, style="grid")
    assert out.splitlines()[0] == "┌────────────┬───┐"
    assert "「" + " " not in out  # no lone 「 cell line
    assert all(width(x) <= 18 for x in out.splitlines())


# --- policy --------------------------------------------------------------------


def test_push_out_first():
    # the block fits on the next line with its ruby: kinsoku push-out
    assert wrap("あいう「鬼《おに》」", 14, ruby=True) == ["あいう", "「鬼《おに》」"]


def test_widest_ruby_goes_first():
    # dropping the long ruby alone is enough; the short one stays
    text = "｜魔法《まほうまほう》・鬼《おに》。"
    w = width("魔法・鬼《おに》。")
    assert wrap(text, w, ruby=True) == ["魔法・鬼《おに》。"]


def test_break_long_words_false_keeps_kinsoku():
    assert wrap("彼は「鬼《おに》」と呼ばれた", 10, ruby=True, break_long_words=False) == [
        "彼は",
        "「鬼《おに》」",
        "と呼ばれた",
    ]
    s = shorten("「鬼《おに》」と言った", 10, ruby=True, break_long_words=False)
    assert s != "…" and width(s) <= 10


def test_ruby_width_base():
    assert wrap("「漢字《かんじ》」", 4, ruby=True, ruby_width="base") == ["「漢", "字」"]


# --- every path: no overflow, never only the placeholder ---------------------


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("w", WIDTHS)
def test_wrap_fits(text, w):
    lines = wrap(text, w, ruby=True)
    assert all(width(x) <= w for x in lines), lines
    assert _body(lines) == strip_ruby(strip_ansi(text))
    _no_lone_open(lines)
    assert fill(text, w, ruby=True) == "\n".join(lines)


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("w", WIDTHS)
def test_wrap_fits_hanging_and_indent(text, w):
    lines = wrap(text, w, ruby=True, initial_indent="　", subsequent_indent="  ")
    assert all(width(x) <= w for x in lines), lines
    lines = wrap(text, w, ruby=True, hanging=True)
    assert all(width(x) <= w + 2 for x in lines), lines


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("w", WIDTHS)
def test_shorten_keeps_text(text, w):
    s = shorten(text, w, ruby=True)
    assert width(s) <= w
    assert _body([s]), s


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("w", WIDTHS)
@pytest.mark.parametrize("n", [1, 2])
def test_max_lines(text, w, n):
    lines = wrap(text, w, ruby=True, max_lines=n)
    assert all(width(x) <= w for x in lines), lines
    assert _body(lines), lines
    lines = wrap(text, w, ruby=True, max_lines=n, ansi_reflow=True)
    assert all(width(x) <= w for x in lines), lines
    assert _body(lines), lines


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("w", WIDTHS)
def test_table_cells(text, w):
    out = table([[text, "x"]], max_col_width=w, ruby=True, style="grid")
    rows = out.splitlines()
    assert len({width(r) for r in rows}) == 1
    assert width(rows[0]) <= w + 8  # "│ " cell " │ x │"


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("w", WIDTHS)
def test_rewrap(text, w):
    out = rewrap(text, w, ruby=True).splitlines()
    assert all(width(x) <= w for x in out), out
    out = rewrap(text, w, ruby=True, max_lines=1).splitlines()
    assert all(width(x) <= w for x in out) and _body(out), out


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("w", WIDTHS)
def test_kinsoku_wrapper(text, w):
    lines = KinsokuWrapper(w, ruby=True).wrap(text)
    assert all(width(x) <= w for x in lines), lines
    _no_lone_open(lines)
    lines = KinsokuWrapper(w, max_lines=1, ruby=True).wrap(text)
    assert all(width(x) <= w for x in lines) and _body(lines), lines
