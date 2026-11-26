"""Whitespace and escapes around line breaks (#16, #21, #29, #34)."""

import subprocess
import sys

import pytest

import kinsoku
from kinsoku import KinsokuWrapper, fill, strip_ansi, width, wrap
from kinsoku.cli import main


# --- #21: leading whitespace of a paragraph is kept --------------------------


def test_fullwidth_indent_kept():
    assert wrap("　吾輩は猫である。名前はまだ無い。", 10) == [
        "　吾輩は猫",
        "である。名",
        "前はまだ無",
        "い。",
    ]


def test_halfwidth_indent_kept():
    assert wrap("    code block line", 40) == ["    code block line"]
    assert wrap("  ab cd", 40) == ["  ab cd"]  # like textwrap


def test_indent_only_on_first_line_of_each_paragraph():
    assert wrap("　あいうえお かきくけこ\n  さしす", 12) == [
        "　あいうえお",
        "かきくけこ",
        "  さしす",
    ]


def test_spaces_at_breaks_still_dropped():
    assert wrap("  aaaa bbbb", 7) == ["  aaaa", "bbbb"]
    assert wrap("ab   cd", 3) == ["ab", "cd"]


def test_indent_and_initial_indent_add_up():
    # the source indent is content; initial_indent is added in front of it
    assert wrap("　本文", 10, initial_indent="　") == ["　　本文"]


def test_indent_dropped_when_first_word_does_not_fit_after_it():
    # textwrap behaves the same way
    assert wrap("      abcdefgh", 8) == ["abcdefgh"]
    assert wrap("   abcdefghijkl", 8, break_long_words=False) == ["abcdefghijkl"]


def test_long_word_after_indent_is_split_into_remaining_space():
    assert wrap("   abcdefghijkl", 8) == ["   abcde", "fghijkl"]


def test_whitespace_only_paragraph_is_empty():
    assert wrap("   ", 5) == [""]
    assert wrap("　　", 5, initial_indent=" ") == [""]


def test_indent_with_max_lines():
    assert wrap("  abcdef ghi", 10, max_lines=1) == ["  abcdef…"]


def test_indent_with_ansi_reflow():
    assert wrap("　\x1b[31mあいう\x1b[0m", 6, ansi_reflow=True) == [
        "　\x1b[31mあい\x1b[0m",
        "\x1b[31mう\x1b[0m",
    ]


def test_wrapper_no_double_indent():
    assert KinsokuWrapper(width=10).wrap("　吾輩は猫である。") == ["　吾輩は猫", "である。"]
    assert KinsokuWrapper(width=10).wrap("  吾輩は猫である。") == ["  吾輩は猫", "である。"]
    w = KinsokuWrapper(width=10, replace_whitespace=False)
    assert w.wrap("　あ\n  い") == ["　あ", "  い"]


def test_rewrap_no_double_indent():
    out = kinsoku.rewrap("　本文です。本文です。\n", 8, indent_marks_paragraph=True)
    assert out == "　本文で\nす。本文\nです。\n"


def test_cli_keeps_indent(capsys, monkeypatch):
    import io

    monkeypatch.setattr(sys, "stdin", io.StringIO("第一章\n\n　本文です。\n"))
    assert main(["-w", "10"]) == 0
    assert capsys.readouterr().out == "第一章\n\n　本文で\nす。\n"


# --- #16: escapes attached to dropped whitespace are kept --------------------


def test_escape_on_dropped_space_kept_on_previous_line():
    assert wrap("ab \x1b[0mcd", 2) == ["ab\x1b[0m", "cd"]


def test_escape_on_dropped_space_kept_with_ansi_reflow():
    assert wrap("ab \x1b[0mcd", 2, ansi_reflow=True) == ["ab\x1b[0m", "cd"]


def test_all_escapes_survive_breaks():
    text = "\x1b[31mred\x1b[0m \x1b[32mgreen\x1b[0m"
    lines = wrap(text, 5)
    # the escapes ride on the dropped space and end the first line
    assert lines == ["\x1b[31mred\x1b[0m\x1b[32m", "green\x1b[0m"]
    assert "".join(lines) == text.replace(" ", "")


def test_escape_on_leading_space_of_next_line_kept():
    assert wrap("ab \x1b[31m cd", 3) == ["ab\x1b[31m", "cd"]
    assert "".join(wrap("aa \x1b[1m　\x1b[22mbb", 2)).count("\x1b") == 2


# --- #29: tabs ----------------------------------------------------------------


def test_width_expands_tabs():
    assert width("a\tb") == 9
    assert width("あい\tう") == 10
    assert width("\t") == 8
    assert width("a\tb", tabsize=4) == 5
    assert width("ab\nc\td") == 2 + 9  # newline resets the column


def test_width_tab_after_escape():
    assert width("\x1b[31ma\x1b[0m\tb") == 9


def test_wrap_expands_tabs_by_display_width():
    assert wrap("a\tb", 40) == ["a       b"]
    assert wrap("名前\t値\tメモ", 12) == ["名前    値", "メモ"]
    assert wrap("名前\t値", 40, tabsize=4) == ["名前    値"]
    assert wrap("日本\tx", 40, tabsize=4) == ["日本    x"]


def test_wrap_tabs_lines_fit():
    for line in wrap("key\tvalue\tあいうえお\tかきくけこ", 12):
        assert width(line) <= 12


def test_leading_tab_is_indent():
    assert wrap("\tindented", 40) == ["        indented"]


def test_tabsize_zero_removes_tabs():
    assert wrap("a\tb", 40, tabsize=0) == ["ab"]


def test_fill_passes_tabsize():
    assert fill("a\tb", 40, tabsize=2) == "a b"


def test_cli_tabs():
    run = lambda args, inp: (
        subprocess.run(
            [sys.executable, "-m", "kinsoku", *args],
            input=inp,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    )
    assert run(["--width-of"], "あい\tう\n") == "10\n"
    assert run(["--width-of", "--tabsize", "3"], "あい\tう\n") == "8\n"
    assert run(["-w", "40"], "a\tb\n") == "a       b\n"


# --- #34: escape-only paragraphs get no indent --------------------------------


def test_escape_only_paragraph_gets_no_indent():
    assert wrap("", 10, initial_indent="  ") == [""]
    assert wrap("\x1b[0m", 10, initial_indent="  ") == ["\x1b[0m"]
    assert wrap("赤い\n\x1b[0m", 10, initial_indent=" ") == [" 赤い", "\x1b[0m"]


def test_escape_and_space_only_paragraph_gets_no_indent():
    assert wrap(" \x1b[31m ", 10, initial_indent=">") == ["\x1b[31m"]


@pytest.mark.parametrize(
    "text",
    [
        "\x1b[0m",
        " \x1b[31m",
        "　\x1b[1mあいうえお かき\x1b[0m",
        "ab \x1b[0mcd",
        "\x1b[31m\tx",
        "a\n\x1b[0m\nb",
    ],
)
@pytest.mark.parametrize("w", [2, 3, 5, 10])
def test_ansi_transparent_examples(text, w):
    kw = dict(initial_indent=" ", subsequent_indent=" ")
    assert [strip_ansi(l) for l in wrap(text, w, **kw)] == wrap(strip_ansi(text), w, **kw)
