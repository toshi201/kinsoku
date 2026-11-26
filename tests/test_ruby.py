import pytest

from kinsoku import NO_START, fill, ruby_to_html, shorten, strip_ruby, width, wrap
from kinsoku.cli import main


def ruby_width(line, mode):
    """Display width of a wrapped line as kinsoku counts it."""
    return width(strip_ruby(line)) if mode == "base" else width(line)


TEXT = "彼は｜東京駅《とうきょうえき》へ向かった。漢字《かんじ》を書く。"
UNITS = ["｜東京駅《とうきょうえき》", "漢字《かんじ》"]


# --- wrap ------------------------------------------------------------------


@pytest.mark.parametrize("mode", ["base", "full"])
# below 4 columns even plain "た。" cannot be kept together
@pytest.mark.parametrize("w", range(4, 40))
def test_ruby_never_split(mode, w):
    # break_long_words=False: a ruby unit is never split; only a lone
    # over-wide one may overflow
    lines = wrap(TEXT, w, ruby=True, ruby_width=mode, break_long_words=False)
    assert "".join(lines) == TEXT
    for unit in UNITS:
        assert any(unit in line for line in lines), (unit, lines)
    for line in lines:
        assert line[0] not in NO_START, lines
        if ruby_width(line, mode) > w:
            assert any(line.startswith(u) for u in UNITS), lines


@pytest.mark.parametrize("mode", ["base", "full"])
@pytest.mark.parametrize("w", range(4, 40))
def test_ruby_kept_when_it_fits(mode, w):
    # break_long_words=True (default): a ruby unit that fits on a line is
    # kept whole; a wider one loses its ruby, and no line overflows (#51)
    lines = wrap(TEXT, w, ruby=True, ruby_width=mode)
    joined = "".join(lines)
    for unit in UNITS:
        if ruby_width(unit, mode) <= w:
            assert any(unit in line for line in lines), (unit, lines)
        else:
            assert unit not in joined
    assert strip_ruby(joined) == strip_ruby(TEXT)
    for line in lines:
        assert line[0] not in NO_START, lines
        assert ruby_width(line, mode) <= w, lines


def test_default_is_off():
    # without ruby=True the notation is ordinary text and may be broken
    lines = wrap("あ漢字《かんじ》", 6)
    assert "漢字《かんじ》" not in lines
    assert wrap("あ漢字《かんじ》", 6) == wrap("あ漢字《かんじ》", 6, ruby=False)


def test_width_full_counts_notation():
    # 漢字《かんじ》 is 14 columns as displayed
    assert wrap("あ漢字《かんじ》", 16, ruby=True) == ["あ漢字《かんじ》"]
    assert wrap("あ漢字《かんじ》", 15, ruby=True) == ["あ", "漢字《かんじ》"]


def test_width_base_counts_only_base():
    # only 漢字 (4 columns) counts
    assert wrap("あ漢字《かんじ》い", 8, ruby=True, ruby_width="base") == ["あ漢字《かんじ》い"]
    assert wrap("あ漢字《かんじ》い", 6, ruby=True, ruby_width="base") == [
        "あ漢字《かんじ》",
        "い",
    ]


def test_explicit_base_with_fullwidth_bar():
    lines = wrap("これは｜東京《とうきょう》です", 8, ruby=True, ruby_width="base")
    assert lines == ["これは", "｜東京《とうきょう》です"]
    # the ｜ marker takes no width in base mode, and its base may be kana
    lines = wrap("あ｜かな《カナ》", 6, ruby=True, ruby_width="base")
    assert lines == ["あ｜かな《カナ》"]


def test_explicit_base_with_ascii_bar_and_latin():
    lines = wrap("foo |Python《パイソン》 bar", 8, ruby=True, ruby_width="base")
    assert lines == ["foo", "|Python《パイソン》", "bar"]
    # the latin base glues to an adjacent word like any latin text
    assert wrap("ab|cd《x》ef gh", 6, ruby=True, ruby_width="base") == [
        "ab|cd《x》ef",
        "gh",
    ]


def test_implicit_base_is_preceding_kanji_run():
    # only 東京 (kanji) is the base, not ひらがな before it
    lines = wrap("ひら東京《とうきょう》", 4, ruby=True, ruby_width="base")
    assert lines == ["ひら", "東京《とうきょう》"]
    # 々〆ヶ〇 are part of the kanji run
    assert strip_ruby("人々《ひとびと》") == "人々"
    assert wrap("あ人々《ひとびと》", 4, ruby=True, ruby_width="base") == [
        "あ",
        "人々《ひとびと》",
    ]


def test_kinsoku_after_ruby():
    # 。 after 》 must not start a line: it is pushed out together
    lines = wrap("あいう漢字《かんじ》。", 8, ruby=True, ruby_width="base")
    assert lines == ["あいう", "漢字《かんじ》。"]
    # the ruby unit fits alone but not with its 。: with break_long_words
    # (the default) width wins and the ruby is dropped (#63) ...
    assert wrap("あ漢字《かんじ》。", 14, ruby=True) == ["あ漢字。"]
    # ... without it, kinsoku wins and the line overflows
    lines = wrap("あ漢字《かんじ》。", 14, ruby=True, break_long_words=False)
    assert lines == ["あ", "漢字《かんじ》。"]


def test_kinsoku_before_ruby():
    # 「 must not end a line: it travels with the ruby unit
    lines = wrap("あいう「漢字《かんじ》」", 8, ruby=True, ruby_width="base")
    assert lines == ["あいう", "「漢字《かんじ》」"]


def test_hanging_with_ruby():
    lines = wrap("あ漢字《かんじ》。い", 6, ruby=True, ruby_width="base", hanging=True)
    assert lines == ["あ漢字《かんじ》。", "い"]


def test_fill_and_shorten_accept_ruby():
    assert fill("あいう漢字《かんじ》", 8, ruby=True, ruby_width="base") == (
        "あいう\n漢字《かんじ》"
    )
    # the placeholder never cuts into a ruby unit
    s = shorten("あ漢字《かんじ》いうえお", 8, ruby=True, ruby_width="base")
    assert s == "あ漢字《かんじ》…"
    s = shorten("あいう漢字《かんじ》えお", 8, ruby=True, ruby_width="base")
    assert s == "あいう…"


def test_invalid_ruby_width():
    with pytest.raises(ValueError):
        wrap("漢字《かんじ》", 10, ruby=True, ruby_width="half")


def test_not_ruby():
    # 《》 without a kanji base or explicit marker is ordinary text
    assert wrap("あ《い》", 4, ruby=True) == wrap("あ《い》", 4)
    assert strip_ruby("《書名》") == "《書名》"


# --- strip_ruby / ruby_to_html ---------------------------------------------


def test_strip_ruby():
    assert strip_ruby(TEXT) == "彼は東京駅へ向かった。漢字を書く。"
    assert strip_ruby("a|b《c》d") == "abd"
    assert strip_ruby("ルビなし") == "ルビなし"


def test_ruby_to_html():
    assert ruby_to_html("漢字《かんじ》") == "<ruby>漢字<rt>かんじ</rt></ruby>"
    assert ruby_to_html("｜東京《とうきょう》へ") == ("<ruby>東京<rt>とうきょう</rt></ruby>へ")


def test_ruby_to_html_escapes():
    assert ruby_to_html('<b>&｜A<B《x&"y》') == (
        "&lt;b&gt;&amp;<ruby>A&lt;B<rt>x&amp;&quot;y</rt></ruby>"
    )


# --- cli -------------------------------------------------------------------


def test_cli_ruby(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("あいう漢字《かんじ》", encoding="utf-8")
    main(["-w", "8", str(f)])
    assert "漢字《かんじ》" not in capsys.readouterr().out.splitlines()
    main(["-w", "14", "--ruby", str(f)])
    assert capsys.readouterr().out == "あいう\n漢字《かんじ》\n"
    main(["-w", "10", "--ruby", "--ruby-width", "base", str(f)])
    assert capsys.readouterr().out == "あいう漢字《かんじ》\n"


def test_escape_before_ruby_unit_moves_with_it():
    # regression: the escape used to be left at the end of the previous line
    from kinsoku import wrap

    assert wrap("あ\x1b[31m漢字《かんじ》\x1b[0mい", 14, ruby=True) == [
        "あ",
        "\x1b[31m漢字《かんじ》\x1b[0m",
        "い",
    ]
    assert wrap("い\x1b[1m｜漢字《かんじ》\x1b[0m", 16, ruby=True) == [
        "い",
        "\x1b[1m｜漢字《かんじ》\x1b[0m",
    ]


def test_ruby_with_ansi_reflow_and_rules():
    from kinsoku import wrap

    out = wrap("\x1b[31mあ漢字《かんじ》い\x1b[0m", 14, ruby=True, ansi_reflow=True)
    assert out == ["\x1b[31mあ\x1b[0m", "\x1b[31m漢字《かんじ》\x1b[0m", "\x1b[31mい\x1b[0m"]
    # 漢字《かんじ》ッ is one kinsoku block wider than 14: its ruby goes (#63)
    assert wrap("漢字《かんじ》ッう", 14, ruby=True) == ["漢字ッう"]
    assert wrap("漢字《かんじ》ッう", 14, ruby=True, break_long_words=False) == [
        "漢字《かんじ》ッ",
        "う",
    ]
    assert wrap("漢字《かんじ》ッう", 14, ruby=True, rules="loose") == [
        "漢字《かんじ》",
        "ッう",
    ]


def test_kinsoku_wrapper_passes_ruby_through_extra():
    from kinsoku import KinsokuWrapper

    w = KinsokuWrapper(14, ruby=True)
    assert w.wrap("あ漢字《かんじ》い") == ["あ", "漢字《かんじ》", "い"]
    assert KinsokuWrapper(14, ruby=True, ruby_width="base").wrap("あ漢字《かんじ》い") == [
        "あ漢字《かんじ》い"
    ]
    assert KinsokuWrapper(14).wrap("あ漢字《かんじ》い") != w.wrap("あ漢字《かんじ》い")
