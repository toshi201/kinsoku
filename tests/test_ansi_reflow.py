from kinsoku import ansi_reflow, fill, shorten, strip_ansi, width, wrap
from kinsoku.cli import main

RED = "\x1b[31m"
RESET = "\x1b[0m"
ST = "\x1b\\"


def plain(lines):
    return [strip_ansi(l) for l in lines]


def test_default_is_off():
    text = RED + "あいうえおかき" + RESET
    assert wrap(text, 6) == ["\x1b[31mあいう", "えおか", "き\x1b[0m"]


def test_color_across_break():
    out = wrap(RED + "あいうえおかき" + RESET, 6, ansi_reflow=True)
    assert out == [
        "\x1b[31mあいう\x1b[0m",
        "\x1b[31mえおか\x1b[0m",
        "\x1b[31mき\x1b[0m",
    ]


def test_reset_mid_text():
    out = wrap(RED + "あいうえ" + RESET + "おかきく", 6, ansi_reflow=True)
    assert out == ["\x1b[31mあいう\x1b[0m", "\x1b[31mえ\x1b[0mおか", "きく"]


def test_unclosed_color_gets_reset():
    out = wrap(RED + "あいうえ", 6, ansi_reflow=True)
    assert out == ["\x1b[31mあいう\x1b[0m", "\x1b[31mえ\x1b[0m"]


def test_attribute_off_codes():
    text = "\x1b[1;3;4mabc \x1b[22mdef \x1b[23;24;7mghi \x1b[27mjkl"
    out = wrap(text, 3, ansi_reflow=True)
    assert out == [
        "\x1b[1;3;4mabc\x1b[22m\x1b[0m",
        "\x1b[3;4mdef\x1b[23;24;7m\x1b[0m",
        "\x1b[7mghi\x1b[27m",  # 27 turned the last attribute off: no reset
        "jkl",
    ]


def test_bold_and_dim_share_off_code():
    out = wrap("\x1b[1m\x1b[2mab \x1b[22mcd ef", 2, ansi_reflow=True)
    assert out == ["\x1b[1m\x1b[2mab\x1b[22m", "cd", "ef"]


def test_escape_before_break_space_is_kept():
    # the reset sits on the space that is trimmed at the break
    assert wrap(RED + "ab " + RESET + "cd", 2, ansi_reflow=True) == [
        "\x1b[31mab\x1b[0m", "cd",
    ]


def test_fg_bg_default_codes():
    out = wrap("\x1b[31;44mab \x1b[39mcd \x1b[49mef", 2, ansi_reflow=True)
    assert out == ["\x1b[31;44mab\x1b[39m\x1b[0m", "\x1b[44mcd\x1b[49m", "ef"]


def test_256_and_truecolor():
    text = "\x1b[38;5;196;48;2;10;20;30mabc def\x1b[39m ghi" + RESET
    out = wrap(text, 3, ansi_reflow=True)
    assert out == [
        "\x1b[38;5;196;48;2;10;20;30mabc\x1b[0m",
        "\x1b[38;5;196;48;2;10;20;30mdef\x1b[39m\x1b[0m",
        "\x1b[48;2;10;20;30mghi\x1b[0m",
    ]


def test_underline_color():
    out = wrap("\x1b[4;58;5;9mab cd \x1b[59mef", 2, ansi_reflow=True)
    assert out == [
        "\x1b[4;58;5;9mab\x1b[0m",
        "\x1b[4;58;5;9mcd\x1b[59m\x1b[0m",
        "\x1b[4mef\x1b[0m",
    ]


def test_bright_colors_and_latest_wins():
    out = wrap("\x1b[31m\x1b[92;103mab cd", 2, ansi_reflow=True)
    assert out[1] == "\x1b[92;103mcd\x1b[0m"


def test_empty_sgr_resets():
    out = wrap(RED + "ab\x1b[m cd", 2, ansi_reflow=True)
    assert out == ["\x1b[31mab\x1b[m", "cd"]


def test_osc8_link_across_break_st():
    link = "\x1b]8;id=1;https://example.com" + ST
    close = "\x1b]8;;" + ST
    out = wrap(link + "abc def" + close + " ghi", 3, ansi_reflow=True)
    assert out == [link + "abc" + close, link + "def" + close, "ghi"]


def test_osc8_link_across_break_bel():
    link = "\x1b]8;;https://example.com\x07"
    close = "\x1b]8;;\x07"
    out = wrap(link + "あいうえお" + close, 4, ansi_reflow=True)
    assert out == [link + "あい" + close, link + "うえ" + close, link + "お" + close]


def test_link_and_color_together():
    link = "\x1b]8;;u" + ST
    out = wrap(RED + link + "ab cd", 2, ansi_reflow=True)
    assert out[0] == RED + link + "ab" + "\x1b]8;;" + ST + RESET
    assert out[1] == RED + link + "cd" + "\x1b]8;;" + ST + RESET


def test_indent_stays_outside_style():
    out = wrap(
        RED + "あいうえおか" + RESET, 6,
        initial_indent="> ", subsequent_indent="  ", ansi_reflow=True,
    )
    assert out == [
        "> \x1b[31mあい\x1b[0m",
        "  \x1b[31mうえ\x1b[0m",
        "  \x1b[31mおか\x1b[0m",
    ]
    assert all(width(l) <= 6 for l in out)


def test_state_carries_across_paragraphs():
    out = wrap(RED + "ab\n\ncd" + RESET, 5, ansi_reflow=True)
    assert out == ["\x1b[31mab\x1b[0m", "", "\x1b[31mcd\x1b[0m"]


def test_no_styling_unchanged():
    text = "吾輩は猫である。名前はまだ無い。どこで生れたかとんと見当がつかぬ。"
    for kw in ({}, {"initial_indent": "　"}, {"max_lines": 2}, {"hanging": True}):
        assert wrap(text, 10, ansi_reflow=True, **kw) == wrap(text, 10, **kw)


def test_non_sgr_escapes_unchanged():
    text = "\x1b[2Kあいうえお"
    assert wrap(text, 4, ansi_reflow=True) == wrap(text, 4)


def test_max_lines():
    out = wrap(RED + "あいうえおかきくけこ" + RESET, 6, max_lines=2, ansi_reflow=True)
    assert out == ["\x1b[31mあいう\x1b[0m", "\x1b[31mえお\x1b[0m…"]
    assert all(width(l) <= 6 for l in out)


def test_max_lines_closes_link():
    link = "\x1b]8;;u" + ST
    out = wrap(link + "abc def ghi", 3, max_lines=2, ansi_reflow=True)
    assert out[1] == link + "de" + "\x1b]8;;" + ST + "…"


def test_max_lines_with_indent_and_no_style_on_last():
    out = wrap(
        RED + "あい" + RESET + "うえおかきく", 6,
        subsequent_indent="  ", max_lines=2, ansi_reflow=True,
    )
    assert out == ["\x1b[31mあい\x1b[0mう", "  え…"]


def test_fill_and_shorten_passthrough():
    text = RED + "あいうえおか"
    assert fill(text, 6, ansi_reflow=True) == "\x1b[31mあいう\x1b[0m\n\x1b[31mえおか\x1b[0m"
    assert shorten(text, 6, ansi_reflow=True) == "\x1b[31mあい\x1b[0m…"


def test_ansi_reflow_helper():
    lines = ["\x1b[1;31mab", "cd\x1b[0m", "ef"]
    assert ansi_reflow(lines) == ["\x1b[1;31mab\x1b[0m", "\x1b[1;31mcd\x1b[0m", "ef"]
    assert ansi_reflow(["plain", "text"]) == ["plain", "text"]


def test_cli_ansi_reflow(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text(RED + "あいうえおか" + RESET + "\n", encoding="utf-8")
    assert main(["-w", "6", "--ansi-reflow", str(f)]) == 0
    assert capsys.readouterr().out == "\x1b[31mあいう\x1b[0m\n\x1b[31mえおか\x1b[0m\n"


def test_kinsoku_wrapper_passes_ansi_reflow_through_extra():
    from kinsoku import KinsokuWrapper

    w = KinsokuWrapper(6, ansi_reflow=True)
    assert w.wrap("\x1b[31mあいうえおか\x1b[0m") == [
        "\x1b[31mあいう\x1b[0m",
        "\x1b[31mえおか\x1b[0m",
    ]
    assert KinsokuWrapper(6).wrap("\x1b[31mあいうえおか\x1b[0m") == [
        "\x1b[31mあいう",
        "えおか\x1b[0m",
    ]


def test_ansi_reflow_combines_with_rules():
    from kinsoku import wrap

    out = wrap("\x1b[31mあいッう\x1b[0m", 4, ansi_reflow=True, rules="loose")
    assert out == ["\x1b[31mあい\x1b[0m", "\x1b[31mッう\x1b[0m"]
