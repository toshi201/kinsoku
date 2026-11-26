"""Regression tests for #46 (table + OSC 8 links) and #49 (unwrap CJK/latin)."""

import pytest

import kinsoku
from kinsoku import fill, rewrap, table, unwrap
from kinsoku.cli import main

L = "\x1b]8;;https://example.com\x1b\\"
LE = "\x1b]8;;\x1b\\"


# --- #46: OSC 8 links in wrapped table cells -----------------------------------


@pytest.mark.parametrize("style", ["grid", "simple", "plain"])
def test_wrapped_link_is_closed_on_every_line(style):
    out = table(
        [[L + "リンク付きの長い説明文" + LE, "隣のセル"]],
        ["リンク", "メモ"],
        max_col_width=8,
        style=style,
    )
    link_lines = [ln for ln in out.splitlines() if L in ln]
    assert len(link_lines) == 3
    for ln in link_lines:
        # opened once and closed once, before any neighbour cell or border
        assert ln.count(L) == 1 and ln.count(LE) == 1
        after = ln[ln.index(LE) + len(LE) :]
        assert after.strip(" │|") in ("", "隣のセル", "メモ")
    assert link_lines[0].index(LE) < link_lines[0].index("隣のセル")


def test_wrapped_link_grid_exact():
    out = table(
        [[L + "リンク付きの長い説明文" + LE, "隣のセル"]],
        ["リンク", "メモ"],
        max_col_width=8,
        style="grid",
    )
    assert out.splitlines()[3:6] == [
        "│ " + L + "リンク付" + LE + " │ 隣のセル │",
        "│ " + L + "きの長い" + LE + " │          │",
        "│ " + L + "説明文" + LE + "   │          │",
    ]


def test_link_with_color_closed_and_reopened():
    cell = "\x1b[31m" + L + "赤いリンクの長い説明" + LE + "\x1b[0m"
    lines = table([[cell]], max_col_width=6, style="plain").splitlines()
    assert len(lines) > 1
    for ln in lines:
        assert ln.startswith("\x1b[31m" + L)
        assert LE in ln and "\x1b[0m" in ln
        assert ln.index(LE) < ln.rindex("\x1b[0m")


def test_color_only_output_unchanged():
    # #46 must not change how colored cells are rendered
    out = table([["\x1b[31m赤い長いセルです\x1b[0m", "x"]], max_col_width=6)
    assert out.splitlines() == [
        "\x1b[31m赤い長\x1b[0m  x",
        "\x1b[31mいセル\x1b[0m   ",
        "\x1b[31mです\x1b[0m     ",
    ]


def test_unwrapped_link_cell_untouched():
    cell = L + "短い" + LE
    out = table([[cell, "b"]], style="plain")
    assert out == cell + "  b"


def test_link_width_unchanged():
    out = table([[L + "リンク付きの長い説明文" + LE, "隣"]], max_col_width=8, style="grid")
    widths = {kinsoku.width(ln) for ln in out.splitlines()}
    assert len(widths) == 1


# --- #49: unwrap at CJK/latin junctions ------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("日本語と\nEnglish\nの混在", "日本語とEnglishの混在"),
        ("Python\nを使う", "Pythonを使う"),
        ("合計は\n12,345円", "合計は12,345円"),
        ("2026年\n11月", "2026年11月"),
        ("ｶﾀｶﾅ\nabc", "ｶﾀｶﾅabc"),
        ("The quick\nbrown fox", "The quick brown fox"),  # latin: unchanged
        ("v1.0\n2.0", "v1.0 2.0"),
        ("한국어\nPython", "한국어 Python"),  # Hangul keeps the space
        ("Python\n한국어", "Python 한국어"),
        ("日本語\n한국어", "日本語한국어"),  # both wide: as before
    ],
)
def test_default_no_space_between_cjk_and_latin(text, expected):
    assert unwrap(text) == expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("日本語と\nEnglish\nの混在", "日本語と English の混在"),
        ("Python\nを使う", "Python を使う"),
        ("The quick\nbrown fox", "The quick brown fox"),
        ("吾輩は\n猫である", "吾輩は猫である"),
        ("使う。\nThen", "使う。Then"),
    ],
)
def test_cjk_latin_space_option(text, expected):
    assert unwrap(text, cjk_latin_space=True) == expected


def test_issue_examples():
    s = "日本語とEnglishの混在です。Python 3.12 を使います。"
    assert unwrap(fill(s, 8)) == s
    s2 = "値は1,000円です。合計は12,345円。"
    assert unwrap(fill(s2, 12)) == s2


MIXED = [
    "これはPythonで2026年11月に書いた文章です。kinsokuというライブラリを使い、80桁で折り返します。",
    "値は1,000円です。合計は12,345円。日本語とEnglishの混在です。",
    "Hello Worldと表示するプログラムをC言語で書いた。iPhone 15とPixel 9を比べる。",
    "第3章ではHTTP/2とTLS1.3を扱う。APIキーはenv変数に入れる。",
]


@pytest.mark.parametrize("p", MIXED)
@pytest.mark.parametrize("w", list(range(8, 41)) + [60, 80])
@pytest.mark.parametrize("hanging", [False, True])
def test_round_trip_mixed(p, w, hanging):
    assert unwrap(fill(p, w, hanging=hanging)) == p


@pytest.mark.parametrize("p", MIXED)
def test_rewrap_is_stable(p):
    once = rewrap(fill(p, 9), 13)
    assert rewrap(once, 9) == fill(p, 9)
    assert unwrap(rewrap(rewrap(p, 11), 17)) == p


def test_rewrap_cjk_latin_space_option():
    assert rewrap("Python\nを使う", 40, cjk_latin_space=True) == "Python を使う"
    assert rewrap("Python\nを使う", 40) == "Pythonを使う"


def test_cli_cjk_latin_space(tmp_path, capsys):
    f = tmp_path / "in.txt"
    f.write_text("日本語と\nEnglish\nの混在\n", encoding="utf-8")
    assert main(["--unwrap", str(f)]) == 0
    assert capsys.readouterr().out == "日本語とEnglishの混在\n"
    assert main(["--unwrap", "--cjk-latin-space", str(f)]) == 0
    assert capsys.readouterr().out == "日本語と English の混在\n"
    assert main(["--rewrap", "-w", "40", "--cjk-latin-space", str(f)]) == 0
    assert capsys.readouterr().out == "日本語と English の混在\n"
