import pytest

from kinsoku import fill, rewrap, strip_ansi, unwrap, width, wrap
from kinsoku.cli import main


# --- joining ----------------------------------------------------------------

def test_japanese_lines_join_without_space():
    assert unwrap("吾輩は猫で\nある。名前\nはまだ無い。") == "吾輩は猫である。名前はまだ無い。"


def test_english_lines_join_with_one_space():
    text = "The quick brown   \n  fox jumps over\n\tthe lazy dog."
    assert unwrap(text) == "The quick brown fox jumps over the lazy dog."


@pytest.mark.parametrize("text,expected", [
    ("日本語の\nPython", "日本語のPython"),     # #49: no space by default
    ("Python\nを使う", "Pythonを使う"),
    ("使う。\nThen", "使う。Then"),
    ("「\nabc」", "「abc」"),
    ("abc\n」です", "abc」です"),
    ("（\nfoo）", "（foo）"),
    ("v1.0\n2.0", "v1.0 2.0"),
    ("あ\n　い", "あ　い"),                 # U+3000 kept, no extra space
    ("待って…\nそして", "待って…そして"),   # … follows the CJK side
    ("wait…\nthen", "wait… then"),
    ("ｱｲｳ\nｴｵ", "ｱｲｳｴｵ"),                 # half-width katakana
])
def test_mixed_junctions(text, expected):
    assert unwrap(text) == expected


def test_single_line_and_empty():
    assert unwrap("") == ""
    assert unwrap("abc") == "abc"
    assert unwrap("abc\n") == "abc\n"


# --- paragraphs ---------------------------------------------------------------

def test_blank_lines_are_preserved_exactly():
    text = "あいう\nえお\n\n  \nかき\nくけ\n\n\nfoo\nbar\n"
    assert unwrap(text) == "あいうえお\n\n  \nかきくけ\n\n\nfoo bar\n"


def test_crlf():
    assert unwrap("あい\r\nうえ\r\n\r\nfoo\r\nbar\r\n") == "あいうえ\r\n\r\nfoo bar\r\n"


def test_fullwidth_indent_marks_paragraph():
    text = "　一段落目の\n文です。\n　二段落目\nです。\n"
    assert unwrap(text, indent_marks_paragraph=True) == (
        "　一段落目の文です。\n　二段落目です。\n"
    )
    # off by default: indented lines are continuation lines
    assert unwrap(text) == "　一段落目の文です。　二段落目です。\n"


def test_halfwidth_indent_marks_paragraph():
    text = "    First para\ngoes on.\n    Second\npara."
    assert unwrap(text, indent_marks_paragraph=True) == "    First para goes on.\n    Second para."
    assert unwrap(text) == "    First para goes on. Second para."


# --- hyphen and list items ----------------------------------------------------------

def test_hyphen_after_latin_letter_is_kept_and_joined():
    assert unwrap("a well-\nknown fact") == "a well-known fact"
    assert unwrap("e-\nmail") == "e-mail"


def test_hyphen_not_after_letter_uses_normal_rule():
    assert unwrap("2020 -\n2021") == "2020 - 2021"
    assert unwrap("1-\n2") == "1- 2"


def test_list_items_start_new_paragraphs():
    text = "Items:\n- apple\n* banana\n  split\n1. one\n2) two\n・りんご\n・みかん\nの話"
    assert unwrap(text) == (
        "Items:\n- apple\n* banana split\n1. one\n2) two\n・りんご\n・みかんの話"
    )


# --- ANSI ---------------------------------------------------------------------

def test_ansi_at_junction_is_kept_and_ignored_for_classification():
    assert unwrap("\x1b[31m赤い\x1b[0m\nです") == "\x1b[31m赤い\x1b[0mです"
    assert unwrap("あい\n\x1b[1mうえ\x1b[0m") == "あい\x1b[1mうえ\x1b[0m"
    assert unwrap("\x1b[31mfoo   \x1b[0m\n  bar") == "\x1b[31mfoo\x1b[0m bar"
    assert unwrap("\x1b[31m\x1b[0m\n") == "\x1b[31m\x1b[0m\n"  # blank


# --- round trip -----------------------------------------------------------------

PARAGRAPHS = [
    "吾輩は猫である。名前はまだ無い。どこで生れたかとんと見当がつかぬ。"
    "何でも薄暗いじめじめした所で「ニャーニャー」泣いていた事だけは記憶している。",
    "親譲りの無鉄砲で小供の時から損ばかりしている。小学校に居る時分学校の二階から"
    "飛び降りて一週間ほど腰を抜かした事がある。なぜそんな無闇をしたと聞く人があるかも知れぬ。",
    "ちょっと待って……（本当に？）『そうだ』と言った。ＡＢＣ１２３、ｶﾀｶﾅも混ぜる。",
]


@pytest.mark.parametrize("p", PARAGRAPHS)
@pytest.mark.parametrize("w", list(range(4, 41)) + [60, 80])
@pytest.mark.parametrize("hanging", [False, True])
def test_round_trip(p, w, hanging):
    wrapped = fill(p, w, hanging=hanging)
    assert unwrap(wrapped) == p


def test_round_trip_multi_paragraph():
    text = "\n\n".join(PARAGRAPHS)
    for w in (10, 17, 30):
        assert unwrap(fill(text, w)) == text


# --- rewrap -------------------------------------------------------------------

def test_rewrap_japanese():
    text = "吾輩は猫で\nある。名前\nはまだ無い。\n"
    assert rewrap(text, 8) == "吾輩は猫\nである。\n名前はま\nだ無い。\n"
    assert rewrap(text, 8) == fill("吾輩は猫である。名前はまだ無い。", 8) + "\n"


def test_rewrap_keeps_blank_lines_and_indent():
    text = "　一段落目の\n文です。\n　二段落目\nです。\n\n  \nabc def\nghi"
    assert rewrap(text, 10, indent_marks_paragraph=True) == (
        "　一段落目\nの文です。\n　二段落目\nです。\n\n  \nabc def\nghi"
    )


def test_rewrap_passes_wrap_options():
    text = "あいう\nえお。"
    assert rewrap(text, 6, hanging=True) == "あいう\nえお。"
    assert rewrap(text, 8, subsequent_indent="  ") == "あいうえ\n  お。"


def test_rewrap_max_lines_applies_to_whole_text():
    text = "あいうえお\nかきくけこ\n\nさしすせそ\n"
    assert rewrap(text, 6, max_lines=2) == "あいう\nえお…\n"
    assert rewrap("あいうえお\n\nさしすせそ", 10, max_lines=2) == "あいうえお\n…"
    assert rewrap("あいう\n\nえお", 10, max_lines=3) == "あいう\n\nえお"


def test_rewrap_crlf_and_errors():
    assert rewrap("foo\r\nbar\r\n\r\nbaz\r\n", 3) == "foo\r\nbar\r\n\r\nbaz\r\n"
    with pytest.raises(ValueError):
        rewrap("abc", 0)
    with pytest.raises(ValueError):
        rewrap("", 5, max_lines=0)


@pytest.mark.parametrize("w", [5, 9, 13, 25])
def test_rewrap_fits(w):
    text = "\n".join(wrap(PARAGRAPHS[0] + " Mixed with English words.", 7))
    for line in rewrap(text, w).splitlines():
        assert width(strip_ansi(line)) <= w


# --- CLI ----------------------------------------------------------------------

def test_cli_unwrap(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("吾輩は猫で\nある。\n\nThe quick\nbrown fox", encoding="utf-8")
    assert main(["--unwrap", str(f)]) == 0
    assert capsys.readouterr().out == "吾輩は猫である。\n\nThe quick brown fox\n"


def test_cli_rewrap(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("吾輩は猫で\nある。名前\nはまだ無い。\n\n　次の\n段落\n", encoding="utf-8")
    assert main(["--rewrap", "-w", "8", "--hanging", str(f)]) == 0
    assert capsys.readouterr().out == "吾輩は猫\nである。\n名前はま\nだ無い。\n\n　次の段\n落\n"


def test_cli_indent_marks_paragraph(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("　一つ\n目\n　二つ\n目\n", encoding="utf-8")
    assert main(["--unwrap", "--indent-marks-paragraph", str(f)]) == 0
    assert capsys.readouterr().out == "　一つ目\n　二つ目\n"


def test_cli_unwrap_and_rewrap_conflict(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("a", encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["--unwrap", "--rewrap", str(f)])


def test_rewrap_passes_rules_and_ansi_reflow():
    from kinsoku import rewrap

    assert rewrap("あい\nッう", 4) == "あ\nいッ\nう"
    assert rewrap("あい\nッう", 4, rules="loose") == "あい\nッう"
    assert rewrap("\x1b[31mあいう\nえおか\x1b[0m", 6, ansi_reflow=True) == (
        "\x1b[31mあいう\x1b[0m\n\x1b[31mえおか\x1b[0m"
    )


def test_cli_rewrap_rules(tmp_path, capsys):
    from kinsoku.cli import main

    f = tmp_path / "in.txt"
    f.write_text("あい\nッう\n", encoding="utf-8")
    assert main(["--rewrap", "-w", "4", "--rules", "loose", str(f)]) == 0
    assert capsys.readouterr().out == "あい\nッう\n"
