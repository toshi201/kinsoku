"""#50: max_lines drops latin words whole; #51: over-wide ruby units."""

import textwrap

import pytest

from kinsoku import KinsokuWrapper, shorten, strip_ansi, strip_ruby, width, wrap

# --- #50: placeholder drops whole words, like textwrap ----------------------

ASCII = [
    "one two three four five six seven",
    "The quick brown fox jumps over the lazy dog again and again.",
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod.",
    "a bb ccc dddd eeeee ffffff ggggggg hhhhhhhh",
    "Hello, world! (This is a test.) Done; ok? yes.",
]


def test_issue_examples():
    s = "one two three four five six seven"
    assert KinsokuWrapper(width=10, max_lines=2).wrap(s) == ["one two", "[...]"]
    assert KinsokuWrapper(width=10, max_lines=2, placeholder="...").wrap(s) == [
        "one two",
        "three...",
    ]
    assert wrap(s, 10, max_lines=2, placeholder="...") == ["one two", "three..."]


@pytest.mark.parametrize("text", ASCII)
@pytest.mark.parametrize("w", range(12, 40, 3))
@pytest.mark.parametrize("max_lines", [2, 3, 4])
@pytest.mark.parametrize("placeholder", [" [...]", "...", "…", " >>"])
def test_matches_textwrap(text, w, max_lines, placeholder):
    plain = textwrap.TextWrapper(width=w).wrap(text)
    # only where the wrapping itself agrees
    assert KinsokuWrapper(width=w).wrap(text) == plain
    kw = dict(width=w, max_lines=max_lines, placeholder=placeholder)
    assert KinsokuWrapper(**kw).wrap(text) == textwrap.TextWrapper(**kw).wrap(text)


@pytest.mark.parametrize(
    "kw",
    [
        dict(width=12, max_lines=2, subsequent_indent="> "),
        dict(width=15, max_lines=2, initial_indent="* ", subsequent_indent="  "),
        dict(width=20, max_lines=3, initial_indent="- ", placeholder="..."),
    ],
)
def test_matches_textwrap_with_indents(kw):
    for text in ASCII:
        assert KinsokuWrapper(**kw).wrap(text) == textwrap.TextWrapper(**kw).wrap(text)


def test_placeholder_on_previous_line():
    # nothing of the last line fits: the previous line takes the placeholder
    assert wrap("ab cdefghi jkl", 8, max_lines=2, placeholder="..") == ["ab.."]
    assert wrap("abcdef ghijklm nop", 8, max_lines=2, placeholder="..") == [
        "abcdef..",
    ]


def test_cjk_still_cut_by_character():
    assert wrap("あいうえおかきくけこさしすせそ", 10, max_lines=2) == [
        "あいうえお",
        "かきくけ…",
    ]
    # latin words inside Japanese text are dropped whole
    assert shorten("これはPythonです", 12) == "これは…"


def test_long_word_cut_by_character():
    # a word that fills a line by itself is cut rather than dropped
    assert wrap("ab abcdefghijklmnopqrstuvwxyz", 10, max_lines=2) == [
        "ab",
        "abcdefghi…",
    ]
    assert wrap("abcdefghijklmnop qr", 10, max_lines=1, break_long_words=False) == ["abcdefghi…"]


def test_first_word_never_vanishes():
    # textwrap.shorten gives "[...]" here; kinsoku keeps some text
    assert shorten("Hello, world!", 8, placeholder="...") == "Hello..."
    assert KinsokuWrapper(width=8, max_lines=1, placeholder="...").wrap("Hello, world!") == [
        "Hello..."
    ]


def test_ansi_kept_and_closed():
    s = "\x1b[31mone two three four five\x1b[0m"
    out = wrap(s, 10, max_lines=2)
    assert [strip_ansi(l) for l in out] == ["one two", "three…"]
    assert out[-1].endswith("\x1b[0m…")
    out = wrap(s, 10, max_lines=2, ansi_reflow=True)
    assert out == ["\x1b[31mone two\x1b[0m", "\x1b[31mthree\x1b[0m…"]
    # placeholder moved to the previous (already closed) line
    out = wrap("\x1b[31mab cdefghi jkl\x1b[0m", 8, max_lines=2, placeholder="..", ansi_reflow=True)
    assert out == ["\x1b[31mab\x1b[0m.."]


@pytest.mark.parametrize("text", ASCII + ["あいう えお かきくけこ さしすせそたち"])
@pytest.mark.parametrize("w", range(6, 30))
@pytest.mark.parametrize("max_lines", [1, 2, 3])
def test_fits_and_ends_with_placeholder(text, w, max_lines):
    out = wrap(text, w, max_lines=max_lines)
    full = wrap(text, w)
    assert len(out) <= max_lines
    for line in out:
        assert width(line) <= w, out
    if len(full) > max_lines:
        assert out[-1].endswith("…")
        assert out[0] != "…", out  # some text is always kept


# --- #51: ruby notations wider than the line --------------------------------


def test_wide_ruby_is_split():
    s = "彼女は｜魔法少女《マジカルガール》になった。"
    lines = wrap(s, 20, ruby=True)
    assert lines == ["彼女は魔法少女になっ", "た。"]
    assert all(width(l) <= 20 for l in lines)
    assert wrap("｜昔《むかし》", 10, ruby=True) == ["昔"]


def test_ruby_kept_if_it_fits():
    s = "彼女は｜魔法少女《マジカルガール》になった。"
    lines = wrap(s, 30, ruby=True)
    assert "｜魔法少女《マジカルガール》" in "".join(lines)
    assert all(width(l) <= 30 for l in lines)


@pytest.mark.parametrize("mode", ["base", "full"])
@pytest.mark.parametrize("w", range(2, 40))
def test_no_line_overflows(mode, w):
    s = "彼女は｜魔法少女《マジカルガール》になった。吾輩《わがはい》は猫である。"
    lines = wrap(s, w, ruby=True, ruby_width=mode)
    measured = (lambda l: width(strip_ruby(l))) if mode == "base" else width
    # below 4 columns even plain "た。" cannot be kept together
    if w >= 4:
        assert all(measured(l) <= w for l in lines), lines
    assert strip_ruby("".join(lines)) == strip_ruby(s)


def test_break_long_words_false_overflows():
    s = "彼女は｜魔法少女《マジカルガール》になった。"
    assert wrap(s, 20, ruby=True, break_long_words=False) == [
        "彼女は",
        "｜魔法少女《マジカルガール》",
        "になった。",
    ]


def test_wide_ruby_keeps_escapes():
    s = "あ\x1b[31m｜魔法少女《マジカルガール》\x1b[0mい"
    lines = wrap(s, 12, ruby=True)
    assert "".join(lines) == "あ\x1b[31m魔法少女\x1b[0mい"


def test_text_survives_max_lines_and_shorten():
    s = "吾輩《わがはい》は猫である"
    assert wrap(s, 10, ruby=True, max_lines=1) == ["吾輩は猫…"]
    assert wrap("あ" + s, 10, ruby=True, max_lines=2) == ["あ吾輩は猫", "である"]
    assert wrap("あ" + s + "。", 8, ruby=True, max_lines=2) == ["あ吾輩は", "猫であ…"]
    assert shorten(s, 10, ruby=True) == "吾輩は猫…"
    # an overflowing unit (break_long_words=False) is reduced to its base
    assert shorten(s, 10, ruby=True, break_long_words=False) == "吾輩…"
    assert wrap(s, 10, ruby=True, max_lines=1, break_long_words=False) == ["吾輩…"]


def test_ruby_that_fits_is_not_cut_into():
    # unchanged: a ruby unit that fits is dropped whole before the placeholder
    s = shorten("あ漢字《かんじ》いうえお", 8, ruby=True, ruby_width="base")
    assert s == "あ漢字《かんじ》…"
