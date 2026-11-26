import unicodedata

import pytest

import kinsoku
from kinsoku import NO_START, tategaki, width
from kinsoku.cli import main
from kinsoku.tategaki import VERTICAL_FORMS

FS = "　"


def grid(out, gap=1):
    """Split output into columns (right to left) of 2-column cells."""
    rows = out.split("\n")
    step = 2 + gap
    ncols = (width(rows[0]) + gap) // step
    cols = []
    for c in range(ncols):
        cells = []
        for row in rows:
            # Rows may mix wide and narrow chars; walk by display width.
            pos, start, cell = 0, (ncols - 1 - c) * step, ""
            for ch in row:
                if start <= pos < start + 2 or (
                    pos == start + 2 and kinsoku.char_width(ch) == 0 and cell
                ):
                    cell += ch
                pos += kinsoku.char_width(ch)
            cells.append(cell)
        cols.append(cells)
    return cols


def column_text(col):
    return [c for c in col if c not in (FS, "  ")]


def assert_aligned(out):
    widths = {width(row) for row in out.split("\n")}
    assert len(widths) == 1, out


def test_exported():
    assert kinsoku.tategaki is tategaki
    assert "tategaki" in kinsoku.__all__


def test_right_to_left():
    out = tategaki("あいうえおか", 3)
    assert out == "え あ\nお い\nか う"
    cols = grid(out)
    assert cols[0] == ["あ", "い", "う"]
    assert cols[1] == ["え", "お", "か"]


def test_padding_and_equal_widths():
    out = tategaki("あいうえ", 3)
    assert out == "え あ\n" + FS + " い\n" + FS + " う"
    assert_aligned(out)


@pytest.mark.parametrize(
    "text",
    [
        "吾輩は猫である。名前はまだ無い。",
        "「ニャーニャー」泣いていた。\n2024年、ABC！",
        "éか゚abc\tdef\n\nx",
        "\x1b[31m赤い\x1b[0m文字……（注）",
    ],
)
@pytest.mark.parametrize("height", [1, 2, 3, 5, 8])
@pytest.mark.parametrize("halfwidth", ["fullwidth", "pair"])
@pytest.mark.parametrize("hanging", [True, False])
def test_rows_have_equal_width(text, height, halfwidth, hanging):
    out = tategaki(text, height, halfwidth=halfwidth, hanging=hanging)
    rows = out.split("\n")
    assert len(rows) in (height, height + 1)
    assert_aligned(out)
    if not hanging:
        assert len(rows) == height


def test_gap():
    assert tategaki("あいうえ", 2, gap=0) == "うあ\nえい"
    assert tategaki("あいうえ", 2, gap=3) == "う   あ\nえ   い"


def test_vertical_forms_are_valid():
    for dst in VERTICAL_FORMS.values():
        unicodedata.name(dst)  # raises if unassigned
    assert VERTICAL_FORMS["「"] == "﹁"
    assert unicodedata.name(VERTICAL_FORMS["。"]).startswith("PRESENTATION FORM FOR VERTICAL")


def test_mapping():
    out = tategaki("「あー」、（い）。…", 20, hanging=False)
    assert column_text(grid(out)[0]) == ["﹁", "あ", "｜", "﹂", "︑", "︵", "い", "︶", "︒", "︙"]
    assert tategaki("『』【】〔〕《》〈〉｛｝", 12).split("\n") == list("﹃﹄︻︼︹︺︽︾︿﹀︷︸")
    assert tategaki("，：；！？‥—―", 8).split("\n") == list("︐︓︔︕︖︰︱︱")
    assert tategaki("～〜", 2).split("\n") == ["≀ ", "≀ "]


def test_ansi_stripped():
    assert tategaki("\x1b[31mあ\x1b[0mい", 2) == "あ\nい"


def test_combining_attaches():
    out = tategaki("か゚き", 2)
    assert out == "か゚\nき"
    assert_aligned(out)


def test_newline_starts_new_column():
    out = tategaki("あい\nう", 3)
    cols = grid(out)
    assert column_text(cols[0]) == ["あ", "い"]
    assert column_text(cols[1]) == ["う"]
    # blank line -> blank column
    assert len(grid(tategaki("あ\n\nい", 2))) == 3
    assert tategaki("", 3) == ""


@pytest.mark.parametrize("hanging", [True, False])
def test_punctuation_not_at_column_top(hanging):
    text = "吾輩は猫である。名前はまだ無い。どこで生れたかとんと見当がつかぬ、「猫」と（小声で）泣いた。"  # noqa: E501 (全角文字の例文)
    for h in range(3, 9):
        out = tategaki(text, h, hanging=hanging)
        for col in grid(out):
            top = col[0]
            orig = [k for k, v in VERTICAL_FORMS.items() if v == top]
            assert top not in NO_START and not any(o in NO_START for o in orig), (h, out)


def test_hanging_uses_extra_row():
    out = tategaki("あいう。えお", 3, hanging=True)
    rows = out.split("\n")
    assert len(rows) == 4
    assert rows[3] == FS + " ︒"
    assert_aligned(out)


def test_oidashi_without_hanging():
    out = tategaki("あいう。えお", 3, hanging=False)
    cols = grid(out)
    assert cols[0] == ["あ", "い", FS]
    assert cols[1] == ["う", "︒", "え"]


def test_oidashi_for_non_hangable_even_when_hanging():
    out = tategaki("あいう」えお", 3, hanging=True)
    cols = grid(out)
    assert len(out.split("\n")) == 3
    assert cols[1][:2] == ["う", "﹂"]
    # 。 hangs, but 」 after it still pushes characters out
    out = tategaki("あいう。」えお", 3, hanging=True)
    for col in grid(out):
        assert col[0] not in ("︒", "﹂")


def test_no_end_not_at_column_bottom():
    out = tategaki("あい「うえお」", 3)
    cols = grid(out)
    assert cols[0] == ["あ", "い", FS]
    assert cols[1][0] == "﹁"
    for h in range(2, 7):
        for col in grid(tategaki("あいう（えお）かき『く』け【こ】", h, hanging=False))[:-1]:
            body = column_text(col)
            assert body[-1] not in ("︵", "﹃", "︻"), h


def test_halfwidth_fullwidth():
    assert tategaki("Ab1 !", 5).split("\n") == ["Ａ", "ｂ", "１", FS, "︕"]
    assert tategaki("(x)", 3).split("\n") == ["︵", "ｘ", "︶"]


def test_halfwidth_pair():
    out = tategaki("2024年12月3日", 7, halfwidth="pair")
    assert out.split("\n") == ["20", "24", "年", "12", "月", "3 ", "日"]
    out = tategaki("2024年12月3日", 3, halfwidth="pair")
    assert out == "日 12 20\n" + FS + " 月 24\n" + FS + " 3  年"
    assert_aligned(out)


def test_errors():
    with pytest.raises(ValueError):
        tategaki("あ", 0)
    with pytest.raises(ValueError):
        tategaki("あ", 3, halfwidth="rotate")
    with pytest.raises(ValueError):
        tategaki("あ", 3, gap=-1)


def test_cli(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("あいうえ\n", encoding="utf-8")
    assert main(["--tategaki", "2", str(f)]) == 0
    assert capsys.readouterr().out == "う あ\nえ い\n"
    assert main(["--tategaki", "2", "--gap", "0", str(f)]) == 0
    assert capsys.readouterr().out == "うあ\nえい\n"


def test_cli_errors(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("あ", encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["--tategaki", "0", str(f)])
    with pytest.raises(SystemExit):
        main(["--tategaki", "2", "--gap", "-1", str(f)])
