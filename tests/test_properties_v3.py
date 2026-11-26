"""Property-based tests (hypothesis) for the features added after 0.2.0:
ruby, unwrap / rewrap, table, tategaki, ansi_reflow, and their combinations (#79).

The invariants of plain wrap / truncate / pad live in ``test_properties.py``.
Every property states what it guarantees and which inputs are exempt; the
exemptions follow the docstrings and the README.  Tests marked
``xfail(strict=True)`` reproduce bugs that are tracked in their own issue.

Skipped automatically when hypothesis is not installed
(``pip install .[test]`` installs it).
"""

import pytest

hypothesis = pytest.importorskip("hypothesis")

from hypothesis import assume, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from kinsoku import (  # noqa: E402
    HANGABLE,
    NO_END,
    NO_START,
    ansi_reflow,
    fill,
    rewrap,
    strip_ansi,
    strip_ruby,
    table,
    tategaki,
    unwrap,
    width,
    wrap,
)
from kinsoku._core import _AnsiState, _clusters  # noqa: E402
from kinsoku.tategaki import VERTICAL_FORMS  # noqa: E402

# The whole file must stay well under 30 s on CI.
SETTINGS = settings(deadline=None, max_examples=200)

# --- strategies ---------------------------------------------------------------

KANJI = "漢字東京魔法少女鬼猫日本語"
HIRAGANA = "あいうえおかきくけこさしすせそ"
JA_PUNCT = "、。「」（）！？ー"
LATIN = "abc12"
ESCAPES = [
    "\x1b[31m",
    "\x1b[1m",
    "\x1b[44m",
    "\x1b[38;5;2m",
    "\x1b[39m",
    "\x1b[0m",
    "\x1b]8;;http://example.com\x1b\\",
    "\x1b]8;;\x1b\\",
]
RULES = ["ja", "strict", "loose", "zh-hans", "zh-hant", "ko"]

# 青空文庫・なろう形式: implicit (kanji run + 《》) and explicit (｜ + 《》) ruby
_ruby_unit = st.one_of(
    st.builds(
        lambda b, r: f"{b}《{r}》",
        st.text(KANJI, min_size=1, max_size=4),
        st.text(HIRAGANA, min_size=1, max_size=6),
    ),
    st.builds(
        lambda b, r: f"｜{b}《{r}》",
        st.text(HIRAGANA + KANJI + "ab", min_size=1, max_size=4),
        st.text(HIRAGANA, min_size=1, max_size=6),
    ),
)
_char = st.sampled_from(list(HIRAGANA + KANJI + JA_PUNCT + LATIN + " "))


def ruby_texts(ansi=False, newlines=False):
    tokens = [_ruby_unit, _char]
    if ansi:
        tokens.append(st.sampled_from(ESCAPES))
    if newlines:
        tokens.append(st.just("\n"))
    return st.lists(st.one_of(*tokens), max_size=25).map("".join)


def _clusters_of(s):
    return list(_clusters(strip_ansi(s)))


def _hang_width(line, aw=1):
    """Width of the trailing hangable punctuation of ``line`` (ぶら下げ)."""
    plain = strip_ansi(line)
    return width(plain) - width(plain.rstrip("".join(HANGABLE)), aw)


def _closed(line):
    """No SGR attribute or OSC 8 link is still active at the end of ``line``."""
    state = _AnsiState()
    state.feed_text(line)
    return not state.active()


def _overflow_allowed(body, room, *, hanging, keep_all, aw=1):
    """Exemptions to "every line fits in ``width``" that wrap() documents.

    ``body`` is the line without its indent, ``room`` the width left for it.

    - a single grapheme cluster wider than ``room`` (``wrap("あ", 1)``)
    - ``hanging=True``: 、。,. may hang past the margin
    - ``keep_all=True``: only breaks at spaces, so a line without inner
      spaces is one unbreakable unit
    """
    if len(_clusters_of(body)) <= 1:
        return True
    if hanging and width(body, aw) - _hang_width(body, aw) <= room:
        return True
    return keep_all and not any(c in strip_ansi(body).strip(" 　") for c in " \t　")


# --- 1. ruby ------------------------------------------------------------------

# ruby=True, ruby_width="full", break_long_words=True: every line fits in
# ``width`` (#51, #59, #63: a ruby unit that does not fit, even together with
# the punctuation kinsoku glues to it, loses its ruby).  ruby_width="base":
# the same, measured on strip_ruby(line).  The ruby notation is never split
# across lines, and strip_ruby of the joined lines is the base text (minus
# the whitespace dropped at line breaks).
# Exempt: the wrap() exemptions in _overflow_allowed (a single cluster wider
# than the room left by the indent, ぶら下げ, keep_all).


@SETTINGS
@given(
    ruby_texts(),
    st.integers(1, 30),
    st.sampled_from(["full", "base"]),
    st.booleans(),
    st.booleans(),
    st.sampled_from(["", "　", "  "]),
)
def test_ruby_lines_fit_and_notation_kept(text, w, ruby_width, hanging, keep_all, indent):
    assume(w > width(indent))
    lines = wrap(
        text,
        w,
        ruby=True,
        ruby_width=ruby_width,
        hanging=hanging,
        keep_all=keep_all,
        initial_indent=indent,
    )
    for i, line in enumerate(lines):
        body, room = (line[len(indent) :], w - width(indent)) if i == 0 else (line, w)
        assert body.count("《") == body.count("》"), lines  # notation not cut
        measured = body if ruby_width == "full" else strip_ruby(body)
        if width(measured) > room:
            assert _overflow_allowed(measured, room, hanging=hanging, keep_all=keep_all), (
                text,
                w,
                lines,
            )

    def squash(s):
        return strip_ruby(s).replace(" ", "").replace("　", "")

    assert squash("".join(lines)) == squash(text)


# ruby=True, break_long_words=False: the notation is kept whole even when it
# overflows ("kinsoku wins"), so the line may be wider than ``width`` only if
# it holds a ruby unit, or is one unbreakable unit by the usual rules.


@SETTINGS
@given(ruby_texts(), st.integers(1, 30))
def test_ruby_no_break_long_words_keeps_notation(text, w):
    lines = wrap(text, w, ruby=True, break_long_words=False)
    for line in lines:
        assert line.count("《") == line.count("》"), lines
        if width(line) > w and "《" not in line:
            # otherwise only a unit without a break opportunity may overflow
            assert _overflow_allowed(line, w, hanging=False, keep_all=False) or " " not in line
    assert strip_ruby("".join(lines)).replace(" ", "") == strip_ruby(text).replace(" ", "")


# --- 2. unwrap / rewrap -------------------------------------------------------

_WIDE_PUNCT = "".join(sorted(c for c in NO_START | NO_END if width(c) == 2))
# 和文だけの段落.  Excluded on purpose:
# - "・": a line starting with it is a list item and starts a new paragraph
#   (unwrap docstring), so fill -> unwrap cannot restore it
# - "　" and other whitespace: wrap() drops whitespace at a line break
# - a paragraph made only of …‥― (ambiguous punctuation shared with
#   English): unwrap decides the junction from the nearest other visible
#   character, and with none it cannot tell Japanese from English
_JA_ONLY = (
    "".join(chr(c) for c in range(0x3041, 0x3097))
    + "".join(chr(c) for c in range(0x30A1, 0x30FB) if chr(c) != "・")
    + "ー々〆"
    + KANJI
    + _WIDE_PUNCT.replace("・", "")
    + "…‥―"
)


@SETTINGS
@given(
    st.text(_JA_ONLY, min_size=1, max_size=60),
    st.integers(1, 30),
    st.booleans(),
    st.booleans(),
    st.sampled_from(["ja", "strict", "loose"]),
)
def test_unwrap_fill_roundtrip_japanese(para, w, hanging, break_long_words, rules):
    # A Japanese-only paragraph survives fill -> unwrap unchanged: no space
    # is put between wide characters (#49).
    assume(any(c not in "…‥―" for c in para))
    filled = fill(para, w, hanging=hanging, break_long_words=break_long_words, rules=rules)
    assert unwrap(filled) == para, filled


_PARA_TEXT = st.lists(
    st.text(HIRAGANA + KANJI + "ab 、。「」", max_size=20).map(lambda s: s.lstrip(" ")),
    max_size=5,
).map("\n".join)


# rewrap: every output line fits in ``width``, and the visible text (minus
# whitespace) is that of unwrap(text).  Exempt: the wrap() exemptions; and
# paragraphs that start with whitespace, see the xfail test below (#82).


@SETTINGS
@given(_PARA_TEXT, st.integers(1, 30), st.booleans(), st.booleans())
def test_rewrap_lines_fit(text, w, hanging, keep_all):
    out = rewrap(text, w, hanging=hanging, keep_all=keep_all)
    for line in out.splitlines():
        if width(line) > w:
            assert _overflow_allowed(line, w, hanging=hanging, keep_all=keep_all), (text, out)

    def squash(s):
        return "".join(s.split())

    assert squash(out) == squash(unwrap(text))


@pytest.mark.xfail(strict=True, reason="#82")
def test_rewrap_leading_space_wider_than_width():
    # wrap() drops a paragraph's leading whitespace when not even the first
    # word fits after it; rewrap() moves it into initial_indent instead and
    # raises "indent is as wide as or wider than width".
    assert wrap(" あ", 1) == ["あ"]
    assert rewrap(" あ", 1) == "あ"


@pytest.mark.xfail(strict=True, reason="#82")
def test_rewrap_leading_space_overflows():
    # the same cause: the kept indent pushes the line past ``width``
    assert wrap(" 、", 2) == ["、"]
    assert width(rewrap(" 、", 2)) <= 2


# --- 3. table -----------------------------------------------------------------

_cell = st.lists(
    st.sampled_from(
        list(HIRAGANA + KANJI + "abc 、。「」\n")
        + ["\x1b[31m", "\x1b[0m", "\x1b]8;;u\x1b\\", "\x1b]8;;\x1b\\", "👍", "∀"]
    ),
    max_size=12,
).map("".join)
_rows = st.lists(st.lists(_cell, min_size=1, max_size=4), min_size=1, max_size=4)


# Every rendered line of a simple / grid / plain table has the same display
# width (also with a ``width`` budget, max_col_width and wrap options), and
# the visible characters of every cell appear in the table, in order, in
# the cell's column.  No exemptions (markdown is not padded per line, so it
# is not checked).


@SETTINGS
@given(
    _rows,
    st.booleans(),
    st.sampled_from(["simple", "grid", "plain"]),
    st.one_of(st.none(), st.integers(1, 40)),
    st.one_of(st.none(), st.integers(1, 10)),
    st.sampled_from([1, 2]),
    st.booleans(),
    st.booleans(),
    st.booleans(),
)
def test_table_lines_same_width(rows, header, style, w, mcw, aw, hanging, keep_all, bl):
    headers, body = (rows[0], rows[1:]) if header else (None, rows)
    out = table(
        body,
        headers,
        style=style,
        width=w,
        max_col_width=mcw,
        ambiguous_width=aw,
        hanging=hanging,
        keep_all=keep_all,
        break_long_words=bl,
    )
    lines = out.split("\n")
    assert len({width(line, aw) for line in lines}) == 1, lines
    # every visible character of every cell survives (cells of one row are
    # interleaved line by line, so this is a multiset check)
    flat = "".join("".join(strip_ansi(c).split()) for r in rows for c in r)
    got = "".join(strip_ansi(out).split())
    for ch in set(flat):
        assert got.count(ch) >= flat.count(ch), (rows, out)


@SETTINGS
@given(_rows, st.sampled_from(["simple", "grid", "plain"]), st.integers(1, 40))
def test_table_ansi_closed_per_line(rows, style, w):
    # Styled cells are closed at every line end, so colors and OSC 8 links
    # never bleed into padding, borders or the next cell (#46).
    for line in table(rows, style=style, width=w).split("\n"):
        assert _closed(line), line


# --- 4. tategaki --------------------------------------------------------------

_TATE_CHARS = list(HIRAGANA + KANJI + JA_PUNCT + "「」『』…—―～〜ab12 \t\n") + [
    "👍",
    "👨‍👩‍👧",
    "🇯🇵",
    "ｶﾞ",
    "ｱ",
    "가",
    "\x1b[31m",
]


def _read_columns(out, gap):
    """The cells of ``tategaki`` output, column by column, right to left."""
    rows = out.split("\n")
    total = width(rows[0])
    ncols = (total + gap) // (2 + gap)
    cells = []
    for c in range(ncols):
        start = total - (c + 1) * 2 - c * gap
        for row in rows:
            pos, cell = 0, ""
            for cl in _clusters(row):
                if start <= pos < start + 2:
                    cell += cl
                pos += width(cl)
            cells.append(cell)
    return cells


# Every output row has the same display width, and no character is lost:
# reading the cells column by column gives the input with the vertical forms
# applied (ASCII made full-width with halfwidth="fullwidth"), minus
# whitespace, newlines, ANSI escapes and padding.  No exemptions.


@SETTINGS
@given(
    st.lists(st.sampled_from(_TATE_CHARS), max_size=30).map("".join),
    st.integers(1, 6),
    st.integers(0, 2),
    st.booleans(),
)
def test_tategaki_rows_same_width_and_chars_kept(text, height, gap, hanging):
    out = tategaki(text, height, gap=gap, hanging=hanging)
    if not out:
        assert not strip_ansi(text).splitlines()
        return
    assert len({width(r) for r in out.split("\n")}) == 1, out

    def expected_cell(cl):
        if len(cl) == 1 and 0x21 <= ord(cl) <= 0x7E:
            cl = chr(ord(cl) + 0xFEE0)
        return VERTICAL_FORMS.get(cl, cl)

    # half-width katakana becomes full-width, with its sound mark
    plain = strip_ansi(text).replace("ｶﾞ", "ガ").replace("ｱ", "ア")
    expected = "".join(
        expected_cell(cl)
        for line in plain.splitlines()
        for cl in _clusters(line)
        if not cl.isspace()
    )
    got = "".join("".join(_read_columns(out, gap)).split())
    assert got == expected, (text, out)


@st.composite
def _tategaki_kinsoku_texts(draw):
    # Ordinary chars with isolated special chars of one kind only (all
    # NO_START or all NO_END), so a column break that respects kinsoku
    # always exists.
    specials = draw(st.sampled_from(["、。」）ー", "「（"]))
    out = [draw(st.sampled_from(HIRAGANA + KANJI))]
    for _ in range(draw(st.integers(0, 30))):
        if draw(st.booleans()):
            out.append(draw(st.sampled_from(specials)))
        out.append(draw(st.sampled_from(HIRAGANA + KANJI)))
    return "".join(out)


@SETTINGS
@given(_tategaki_kinsoku_texts(), st.integers(2, 6))
def test_tategaki_kinsoku(text, height):
    # Kinsoku on the original chars (追い出し, hanging=False): no column
    # starts with a NO_START char or ends with a NO_END char.  Exempt: texts
    # where no split satisfies both rules ("best effort"), which the
    # generator avoids.
    out = tategaki(text, height, hanging=False)
    if not out:
        return
    inv = {v: k for k, v in reversed(VERTICAL_FORMS.items())}
    cells = _read_columns(out, 1)
    for c in range(0, len(cells), height):
        col = [inv.get(x, x) for x in cells[c : c + height] if x.strip()]
        if not col:
            continue
        if c:
            assert col[0] not in NO_START, out
        if c + height < len(cells):
            assert col[-1] not in NO_END, out


# --- 5. ansi_reflow -----------------------------------------------------------

_ansi_text = st.lists(st.sampled_from(list("あいうabc 、。\n") + ESCAPES), max_size=30).map("".join)


# wrap(..., ansi_reflow=True) only adds escapes: strip_ansi of every line is
# the same as without ansi_reflow (also with indents and max_lines), and no
# line ends with SGR attributes or an OSC 8 link still open.  No exemptions.


@SETTINGS
@given(
    _ansi_text,
    st.integers(3, 20),
    st.one_of(st.none(), st.integers(1, 4)),
    st.sampled_from(["", "  ", "　"]),
)
def test_ansi_reflow_transparent_and_closed(text, w, max_lines, indent):
    kw = dict(max_lines=max_lines, initial_indent=indent, subsequent_indent=indent)
    on = wrap(text, w, ansi_reflow=True, **kw)
    off = wrap(text, w, **kw)
    assert [strip_ansi(x) for x in on] == [strip_ansi(x) for x in off]
    for line in on:
        assert _closed(line), on


@SETTINGS
@given(st.lists(st.lists(st.sampled_from(list("あab ") + ESCAPES), max_size=10).map("".join)))
def test_ansi_reflow_function(lines):
    # The standalone ansi_reflow(lines): same visible text, every line closed,
    # and lines that never had active styling are unchanged.
    out = ansi_reflow(lines)
    assert [strip_ansi(x) for x in out] == [strip_ansi(x) for x in lines]
    assert all(_closed(x) for x in out)
    state = _AnsiState()
    for before, after in zip(lines, out, strict=True):
        if not state.active() and "\x1b" not in before:
            assert after == before
        state.feed_text(before)


# --- 6. combinations ----------------------------------------------------------

# rules × keep_all × hanging × break_long_words × ruby × ruby_width ×
# ansi_reflow × max_lines × indent × ambiguous_width:
# - no exception (for valid arguments: the indent is narrower than ``width``,
#   and "…" fits in ``width`` when max_lines is given, as documented)
# - at most max_lines lines
# - every line fits in ``width``.  Exempt: the wrap() exemptions in
#   _overflow_allowed; break_long_words=False (a unit may overflow, see
#   test_properties.py); ruby_width="base" (the notation is measured by its
#   base text only, so the displayed line is wider by design)
# - ansi_reflow=True only adds escapes and closes every line
# - the ruby notation is never split across lines
# - rewrap accepts the same options and keeps at most max_lines lines


@settings(deadline=None, max_examples=400)
@given(
    ruby_texts(ansi=True, newlines=True),
    st.integers(1, 30),
    st.sampled_from(RULES),
    st.booleans(),
    st.booleans(),
    st.booleans(),
    st.booleans(),
    st.sampled_from(["full", "base"]),
    st.booleans(),
    st.one_of(st.none(), st.integers(1, 4)),
    st.sampled_from(["", "　", " "]),
    st.sampled_from([1, 2]),
)
def test_combinations(text, w, rules, keep_all, hanging, bl, ruby, rw, reflow, ml, indent, aw):
    assume(w > width(indent, aw))
    assume(ml is None or width("…", aw) <= w)
    kw = dict(
        rules=rules,
        keep_all=keep_all,
        hanging=hanging,
        break_long_words=bl,
        ruby=ruby,
        ruby_width=rw,
        max_lines=ml,
        initial_indent=indent,
        ambiguous_width=aw,
    )
    lines = wrap(text, w, ansi_reflow=reflow, subsequent_indent=indent, **kw)
    assert lines
    if ml is not None:
        assert len(lines) <= ml
    if reflow:
        plain = wrap(text, w, subsequent_indent=indent, **kw)
        assert [strip_ansi(x) for x in lines] == [strip_ansi(x) for x in plain]
        assert all(_closed(x) for x in lines)
    for line in lines:
        visible = strip_ansi(line)
        if ruby:
            assert visible.count("《") == visible.count("》"), lines
        body = visible[len(indent) :] if visible.startswith(indent) else visible
        room = w - width(indent, aw) if visible.startswith(indent) else w
        if bl and not (ruby and rw == "base") and width(body, aw) > room:
            assert _overflow_allowed(body, room, hanging=hanging, keep_all=keep_all, aw=aw), (
                text,
                w,
                kw,
                lines,
            )

    # rewrap: paragraphs that start with whitespace hit #82
    if any(strip_ansi(p)[:1] in (" ", "　") for p in text.split("\n")):
        return
    out = rewrap(text, w, ansi_reflow=reflow, **kw)
    if ml is not None:
        assert len(out.splitlines()) <= ml


# --- 7. max_lines keeps some text ---------------------------------------------

# wrap(max_lines=...) documents: "the first word of the first line is cut by
# characters instead, so some text always remains".  So when the first
# paragraph has visible text and the width leaves room for one wide char
# plus "…", the result is never the placeholder alone.


@SETTINGS
@given(ruby_texts(ansi=True), st.integers(4, 30), st.booleans(), st.booleans())
def test_max_lines_keeps_text(text, w, ruby, reflow):
    first = strip_ansi(text).split("\n")[0].strip()
    assume(first and first[0] not in "「（")  # see the xfail test below (#83)
    if len(wrap(text, w, ruby=ruby)) <= 1:
        return
    out = wrap(text, w, max_lines=1, ruby=ruby, ansi_reflow=reflow)
    assert strip_ansi(out[0]) != "…", (text, w, out)


@pytest.mark.xfail(strict=True, reason="#83")
def test_max_lines_opening_bracket_first_line_not_lost():
    # The first line "（あ" fills width=4; making room for "…" leaves only
    # "（", which may not end a line, so everything is dropped.
    assert wrap("（あい", 4) == ["（あ", "い"]
    assert wrap("（あい", 4, max_lines=1) != ["…"]
