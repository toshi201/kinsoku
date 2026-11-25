"""Property-based tests (hypothesis) for the invariants of wrap/truncate/pad.

Skipped automatically when hypothesis is not installed
(``pip install .[test]`` installs it).
"""

import re

import pytest

hypothesis = pytest.importorskip("hypothesis")

from hypothesis import assume, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from kinsoku import NO_END, NO_START, pad, strip_ansi, truncate, width, wrap  # noqa: E402
from kinsoku._core import HANGABLE, _clusters  # noqa: E402

SETTINGS = settings(deadline=None, max_examples=150)

# --- strategies ---------------------------------------------------------------

ASCII = "abcdefghijklmnopqrstuvwxyzABCXYZ0123456789" + "     " + ",.!?;:()'-%"
HIRAGANA = "".join(chr(c) for c in range(0x3041, 0x3097))  # incl. small kana
KATAKANA = "".join(chr(c) for c in range(0x30A1, 0x30FB)) + "ー"
KANJI = "漢字日本語文章処理吾輩猫名前見当生"
JP_PUNCT = "".join(sorted(NO_START | NO_END))
SPACES = " 　"
EMOJI = ["👍", "😀", "🎉", "👨‍👩‍👧", "❤️"]
COMBINING = ["́", "̈", "゙"]
ANSI = ["\x1b[31m", "\x1b[0m"]

_plain_token = st.one_of(
    st.sampled_from(ASCII),
    st.sampled_from(HIRAGANA),
    st.sampled_from(KATAKANA),
    st.sampled_from(KANJI),
    st.sampled_from(JP_PUNCT),
    st.sampled_from(SPACES),
    st.sampled_from(EMOJI),
    st.sampled_from(COMBINING),
)


def texts(ansi=False, newlines=True):
    tokens = [_plain_token]
    if ansi:
        tokens.append(st.sampled_from(ANSI))
    if newlines:
        tokens.append(st.just("\n"))
    return st.lists(st.one_of(*tokens), max_size=60).map("".join)


INDENTS = st.sampled_from(["", " ", "  ", "　"])


@st.composite
def wrap_kwargs(draw):
    ii = draw(INDENTS)
    si = draw(INDENTS)
    min_w = max(width(ii), width(si)) + 1
    w = draw(st.integers(min_value=min_w, max_value=80))
    return dict(
        width=w,
        initial_indent=ii,
        subsequent_indent=si,
        hanging=draw(st.booleans()),
        break_long_words=draw(st.booleans()),
        keep_all=draw(st.booleans()),
        ambiguous_width=draw(st.sampled_from([1, 2])),
    )


# Whitespace, together with zero-width marks attached to it (e.g. " \u0301"),
# forms one whitespace cluster that wrap() may drop at a line break.
_WS_RE = re.compile(r"[ \t\u3000][\u0300-\u036f\u3099\u309a\u200d\ufe0f]*")


def _content(s):
    return _WS_RE.sub("", strip_ansi(s))


def _strip_indent(line, kw, first):
    ind = kw["initial_indent"] if first else kw["subsequent_indent"]
    assert line.startswith(ind)
    return line[len(ind):]


def _paragraph_lines(text, kw):
    """Yield (content, is_first_line_of_paragraph) for every output line."""
    for para in text.splitlines() or [""]:
        lines = wrap(para, **kw)
        for i, line in enumerate(lines):
            yield _strip_indent(line, kw, i == 0) if line else line, i == 0


# --- 1. never raises ----------------------------------------------------------

@SETTINGS
@given(texts(ansi=True), wrap_kwargs(),
       st.one_of(st.none(), st.integers(1, 5)))
def test_never_raises(text, kw, max_lines):
    # "…" is 2 columns with ambiguous_width=2: wider than width=1 is a
    # documented ValueError, i.e. not a valid argument combination.
    assume(max_lines is None or width("…", kw["ambiguous_width"]) <= kw["width"])
    lines = wrap(text, max_lines=max_lines, **kw)
    assert isinstance(lines, list) and all(isinstance(l, str) for l in lines)
    assert lines


# --- 2. width -----------------------------------------------------------------

def _hang_width(content, aw):
    h = 0
    for ch in reversed(strip_ansi(content)):
        if ch not in HANGABLE:
            break
        h += width(ch, aw)
    return h


@SETTINGS
@given(texts(ansi=True), wrap_kwargs())
def test_lines_fit_width(text, kw):
    w, aw = kw["width"], kw["ambiguous_width"]
    for content, first in _paragraph_lines(text, kw):
        indent = kw["initial_indent"] if first else kw["subsequent_indent"]
        lw = width(indent + content if content else "", aw)
        if lw <= w:
            continue
        plain = strip_ansi(content)
        if len(list(_clusters(plain))) == 1:
            continue  # a single cluster wider than the available width
        if kw["hanging"] and lw - _hang_width(content, aw) <= w:
            continue  # ぶら下げ
        if not kw["break_long_words"] and not any(c in plain for c in " \t　"):
            continue  # one unbreakable unit on its own line
        raise AssertionError((content, lw, kw))


# --- 3. content preservation -------------------------------------------------

@SETTINGS
@given(texts(ansi=True), wrap_kwargs())
def test_content_preserved(text, kw):
    # Lines (indents removed) joined == input minus newlines minus whitespace.
    expected = "".join(_content(p) for p in text.splitlines())
    got = "".join(_content(c) for c, _ in _paragraph_lines(text, kw))
    assert got == expected
    assert len(wrap(text, **kw)) >= len(text.splitlines())


# --- 4. kinsoku ---------------------------------------------------------------

ORDINARY = "あいうえおかきくけこさしすせそ漢字日本語文章処理"
SPECIAL = "".join(sorted((NO_START | NO_END) - set(" ")))


@st.composite
def kinsoku_texts(draw):
    # Every NO_START / NO_END char is isolated between ordinary wide chars,
    # so the text never forces a violation.
    n = draw(st.integers(1, 40))
    out = [draw(st.sampled_from(ORDINARY))]
    for _ in range(n):
        if draw(st.booleans()):
            out.append(draw(st.sampled_from(SPECIAL)))
        out.append(draw(st.sampled_from(ORDINARY)))
    return "".join(out)


@SETTINGS
@given(kinsoku_texts(), st.integers(10, 80), st.booleans(), st.booleans(),
       st.sampled_from([1, 2]))
def test_kinsoku_respected(text, w, hanging, break_long_words, aw):
    lines = wrap(text, w, hanging=hanging, break_long_words=break_long_words,
                 ambiguous_width=aw)
    assert "".join(lines) == text
    for line in lines:
        assert line[0] not in NO_START, lines
        assert line[-1] not in NO_END, lines


# --- 5. ANSI transparency -----------------------------------------------------

@SETTINGS
@given(texts(ansi=True), wrap_kwargs())
def test_ansi_transparent(text, kw):
    # Paragraphs consisting only of escape sequences are covered by the
    # xfail regression test below (#34).
    assume(not any(p and not strip_ansi(p) for p in text.splitlines()))
    assert [strip_ansi(l) for l in wrap(text, **kw)] == wrap(strip_ansi(text), **kw)


# --- 6. truncate / pad --------------------------------------------------------

@SETTINGS
@given(texts(ansi=True, newlines=False), st.integers(1, 80),
       st.sampled_from(["…", "...", ""]), st.sampled_from([1, 2]))
def test_truncate_fits(text, limit, placeholder, aw):
    if width(placeholder, aw) > limit:
        return
    out = truncate(text, limit, placeholder, ambiguous_width=aw)
    assert width(out, aw) <= limit
    if width(text, aw) <= limit:
        assert out == text
    else:
        assert out.endswith(placeholder)


@SETTINGS
@given(texts(ansi=True, newlines=False), st.integers(0, 80),
       st.sampled_from(["left", "right", "center"]), st.sampled_from([1, 2]))
def test_pad_width(text, limit, align, aw):
    out = pad(text, limit, align, ambiguous_width=aw)
    assert width(out, aw) == max(limit, width(text, aw))
    assert strip_ansi(out).strip(" ") == strip_ansi(text).strip(" ")


# --- 7. max_lines -------------------------------------------------------------

@SETTINGS
@given(texts(ansi=True), wrap_kwargs(), st.integers(1, 5))
def test_max_lines(text, kw, max_lines):
    assume(width("…", kw["ambiguous_width"]) <= kw["width"])
    lines = wrap(text, max_lines=max_lines, **kw)
    assert 1 <= len(lines) <= max_lines
    full = wrap(text, **kw)
    if len(full) <= max_lines:
        assert lines == full
    else:
        assert lines[:-1] == full[: max_lines - 1]
        assert strip_ansi(lines[-1]).endswith("…")


# --- regression tests for bugs found by the properties above -----------------

@pytest.mark.xfail(strict=True, reason="#34")
def test_escape_only_paragraph_gets_no_indent():
    # A paragraph made only of ANSI escapes is visually empty, like "".
    assert wrap("", 10, initial_indent="  ") == [""]
    assert wrap("\x1b[0m", 10, initial_indent="  ") == ["\x1b[0m"]
