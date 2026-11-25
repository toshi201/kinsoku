import pytest

from kinsoku import NO_END, NO_START, fill, pad, truncate, width, wrap
from kinsoku.cli import main


def assert_fits(lines, w):
    for line in lines:
        assert width(line) <= w, (line, width(line))


def assert_kinsoku(lines):
    for line in lines:
        if line:
            assert line[0] not in NO_START, lines
            assert line[-1] not in NO_END, lines


# --- width -----------------------------------------------------------------

@pytest.mark.parametrize("s,expected", [
    ("", 0),
    ("abc", 3),
    ("あいう", 6),
    ("ｱｲｳ", 3),          # half-width katakana
    ("Ａ", 2),            # full-width latin
    ("が", 2),            # precomposed
    ("が", 2),      # combining dakuten
    ("é", 1),       # combining acute
    ("👍", 2),
    ("​", 0),
])
def test_width(s, expected):
    assert width(s) == expected


def test_ambiguous_width():
    assert width("○△") == 2
    assert width("○△", ambiguous_width=2) == 4


# --- wrap ------------------------------------------------------------------

def test_plain_japanese_wraps_by_columns():
    lines = wrap("あいうえおかきくけこ", 6)
    assert lines == ["あいう", "えおか", "きくけ", "こ"]


def test_punctuation_never_starts_line():
    lines = wrap("あいう。えお", 6)
    assert lines == ["あい", "う。え", "お"]
    assert_kinsoku(lines)
    assert_fits(lines, 6)


def test_open_bracket_never_ends_line():
    lines = wrap("あい「うえ」", 6)
    assert_kinsoku(lines)
    assert_fits(lines, 6)
    assert "".join(lines) == "あい「うえ」"


def test_small_kana_and_long_vowel():
    lines = wrap("アイスクリームとチョコレート", 8)
    assert_kinsoku(lines)
    assert_fits(lines, 8)


def test_hanging_punctuation():
    text = "あいう。えお"
    assert wrap(text, 6, hanging=True)[0] == "あいう。"
    assert wrap(text, 6, hanging=False)[0] != "あいう。"


def test_latin_words_are_not_split():
    lines = wrap("hello world foo bar", 11)
    assert lines == ["hello world", "foo bar"]


def test_mixed_text():
    text = "Pythonの標準ライブラリtextwrapは、日本語の折り返しが苦手です。"
    lines = wrap(text, 20)
    assert_fits(lines, 20)
    assert_kinsoku(lines)
    assert "".join(lines) == text
    assert "Python" in lines[0]
    assert any("textwrap" in l for l in lines)


def test_long_word_is_broken():
    lines = wrap("a" * 25, 10)
    assert lines == ["a" * 10, "a" * 10, "a" * 5]


def test_long_word_kept_when_disabled():
    lines = wrap("x " + "a" * 25, 10, break_long_words=False)
    assert lines == ["x", "a" * 25]


def test_newlines_are_preserved():
    assert wrap("あい\nう", 10) == ["あい", "う"]
    assert wrap("a\n\nb", 10) == ["a", "", "b"]


def test_empty():
    assert wrap("", 10) == [""]


def test_trailing_spaces_stripped():
    assert wrap("aaa bbb ccc", 7) == ["aaa bbb", "ccc"]


def test_ideographic_space_is_breakable():
    lines = wrap("あいう　えおか", 6)
    assert lines == ["あいう", "えおか"]


def test_invalid_width():
    with pytest.raises(ValueError):
        wrap("a", 0)


def test_width_one_does_not_loop():
    lines = wrap("あいう", 1)
    assert "".join(lines) == "あいう"


def test_fill():
    assert fill("あいうえ", 4) == "あい\nうえ"


@pytest.mark.parametrize("w", range(2, 30))
def test_invariants_on_long_text(w):
    text = ("吾輩は猫である。名前はまだ無い。どこで生れたかとんと見当がつかぬ。"
            "何でも薄暗いじめじめした所で「ニャーニャー」泣いていた事だけは記憶している。")
    lines = wrap(text, w)
    assert "".join(lines) == text
    assert_fits(lines, w)
    # the widest unbreakable unit (「ニャー) is 8 columns; at or above that
    # width kinsoku must be fully respected, below it it is best-effort.
    if w >= 8:
        assert_kinsoku(lines)


# --- truncate / pad ----------------------------------------------------------

def test_truncate():
    assert truncate("あいうえお", 6) == "あい…"
    assert truncate("あいう", 6) == "あいう"
    assert width(truncate("あいうえお", 5)) <= 5


def test_pad():
    assert pad("あ", 4) == "あ  "
    assert pad("あ", 4, "right") == "  あ"
    assert pad("あ", 5, "center") == " あ  "
    assert pad("あいう", 4) == "あいう"


# --- cli -------------------------------------------------------------------

def test_cli(tmp_path, capsys):
    f = tmp_path / "in.txt"
    f.write_text("あいうえおかきくけこ\n", encoding="utf-8")
    assert main(["-w", "6", str(f)]) == 0
    assert capsys.readouterr().out == "あいう\nえおか\nきくけ\nこ\n"


def test_cli_width_of(tmp_path, capsys):
    f = tmp_path / "in.txt"
    f.write_text("あa\n", encoding="utf-8")
    main(["--width-of", str(f)])
    assert capsys.readouterr().out == "3\n"
