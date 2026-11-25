import io

import pytest

import kinsoku
from kinsoku import NO_END, NO_START, strip_ansi, table, width
from kinsoku.cli import main

ROWS = [
    ["東京", "日本の首都。人口は約1400万人で、世界有数の大都市です。", 1400],
    ["NYC", "New York City", None],
    ["大阪", "「天下の台所」と呼ばれた商業の街。", 275],
]
HEADERS = ["都市", "説明", "人口"]


def widths(out, aw=1):
    return {width(line, aw) for line in out.splitlines()}


def test_exported():
    assert "table" in kinsoku.__all__
    assert kinsoku.table is table


@pytest.mark.parametrize("style", ["simple", "grid", "plain"])
def test_cjk_ascii_alignment_equal_width(style):
    out = table(ROWS, HEADERS, max_col_width=20, style=style)
    assert len(widths(out)) == 1, out


def test_simple_layout():
    out = table([["あ", "b"], ["cc", "いい"]], ["名前", "x"])
    assert out.splitlines() == [
        "名前  x   ",
        "----  ----",
        "あ    b   ",
        "cc    いい",
    ]


def test_plain_has_no_rule():
    out = table([["あ", "b"]], ["名前", "x"], style="plain")
    assert out.splitlines() == ["名前  x", "あ    b"]


def test_no_headers():
    assert table([["a", "bb"], ["ccc", "d"]]).splitlines() == ["a    bb", "ccc  d "]


def test_grid_layout():
    out = table([["あい", 1]], ["名", "n"], style="grid")
    assert out.splitlines() == [
        "┌──────┬───┐",
        "│ 名   │ n │",
        "├──────┼───┤",
        "│ あい │ 1 │",
        "└──────┴───┘",
    ]


def test_none_and_str_conversion():
    out = table([[None, 3.5, True]], style="plain")
    assert out == "  3.5  True"  # empty column has width 0


def test_wrap_in_cells_with_kinsoku():
    out = table(ROWS, HEADERS, max_col_width=10, style="grid")
    assert len(widths(out)) == 1
    texts = [line.split("│")[2].strip() for line in out.splitlines()
             if line.startswith("│")]
    assert all(width(t) <= 10 for t in texts)
    assert "都。人口は" in texts  # 「。」 is pushed along, never starts a line
    for t in filter(None, texts):
        assert t[0] not in NO_START, texts
        assert t[-1] not in NO_END, texts


def test_wrap_respects_kinsoku_exact():
    out = table([["あいう。えお"]], max_col_width=6)
    assert [line.rstrip() for line in out.splitlines()] == ["あい", "う。え", "お"]


def test_embedded_newlines():
    out = table([["一行目\n二行目", "x"]], style="plain")
    assert out.splitlines() == ["一行目  x", "二行目   "]


def test_per_column_max_col_width():
    out = table([["abcdefgh", "abcdefgh"]], max_col_width=[4, None], style="plain")
    assert out.splitlines() == ["abcd  abcdefgh", "efgh          "]


@pytest.mark.parametrize("align,expected", [
    ("left", ["あ    ", "ああ  "]),
    ("right", ["    あ", "  ああ"]),
    ("center", ["  あ  ", " ああ "]),
])
def test_align_single(align, expected):
    out = table([["あ"], ["ああ"], ["abcdef"]], align=align, style="plain")
    assert out.splitlines()[:2] == expected


def test_align_per_column():
    out = table([["a", "1"], ["bbb", "222"], ["cc", "33"]],
                align=["left", "right"], style="plain")
    assert out.splitlines() == ["a      1", "bbb  222", "cc    33"]


def test_align_shorter_sequence_defaults_left():
    out = table([["a", "b"], ["ccc", "ddd"]], align=["right"], style="plain")
    assert out.splitlines() == ["  a  b  ", "ccc  ddd"]


def test_width_budget_shrinks_widest_first():
    out = table(ROWS, HEADERS, width=30, style="grid")
    assert widths(out) == {30}
    # the short columns keep their natural width
    assert out.splitlines()[1].startswith("│ 都市 │")
    out = table(ROWS, HEADERS, width=30)
    assert max(widths(out)) <= 30


def test_width_budget_min_column_width():
    rows = [["あいうえおかきくけこ"] * 5]
    out = table(rows, width=10, style="plain")
    # cannot fit: columns stop shrinking at 4
    first = out.splitlines()[0]
    assert first.startswith("あい  あい")
    assert len(widths(out)) == 1


def test_width_budget_not_needed():
    assert table(ROWS, HEADERS, width=1000) == table(ROWS, HEADERS)


def test_markdown():
    out = table([["a|b", "x\ny"], ["あ", 1]], ["h1", "h2"],
                style="markdown", align=["left", "right"])
    assert out.splitlines() == [
        "| h1   |     h2 |",
        "| :--- | -----: |",
        "| a\\|b | x<br>y |",
        "| あ   |      1 |",
    ]


def test_markdown_center_and_no_headers():
    out = table([["abc"]], style="markdown", align="center")
    assert out.splitlines() == ["|     |", "| :-: |", "| abc |"]


def test_markdown_wraps_with_br():
    out = table([["あいう。えお"]], ["h"], style="markdown", max_col_width=6)
    assert "あい<br>う。え<br>お" in out


def test_ansi_cells_align():
    red = "\x1b[31m赤\x1b[0m"
    out = table([[red, "x"], ["abcd", "y"]], ["色", "v"], style="grid")
    assert len(widths(out)) == 1
    plain = table([["赤", "x"], ["abcd", "y"]], ["色", "v"], style="grid")
    assert strip_ansi(out) == plain


def test_ansi_wrapped_cell_color_does_not_bleed():
    out = table([["\x1b[31mあいうえおか\x1b[0m", "x"]], max_col_width=4, style="grid")
    body = [line for line in out.splitlines() if line.startswith("│")]
    assert len(body) == 3
    for line in body:
        assert line.count("\x1b[31m") == 1
        assert line.index("\x1b[0m") < line.index(" │ ")
    assert len(widths(out)) == 1


def test_ambiguous_width_2_grid_falls_back_to_ascii():
    out = table([["○", "あ"]], ["記号", "x"], style="grid", ambiguous_width=2)
    assert out.splitlines() == [
        "+------+----+",
        "| 記号 | x  |",
        "+------+----+",
        "| ○   | あ |",
        "+------+----+",
    ]
    assert len(widths(out, 2)) == 1
    assert not any(ch in out for ch in "┌─│")


def test_ambiguous_width_2_alignment():
    out = table([["○△", "a"], ["abcd", "b"]], style="plain", ambiguous_width=2)
    assert len(widths(out, 2)) == 1


def test_ragged_rows_are_padded():
    out = table([["a"], ["b", "c", "d"]], ["h1", "h2"], style="grid")
    lines = out.splitlines()
    assert len(widths(out)) == 1
    assert lines[0].count("┬") == 2
    assert lines[3] == "│ a  │    │   │"


def test_empty():
    assert table([]) == ""
    assert table([], ["a", "b"]) == "a  b\n-  -"


@pytest.mark.parametrize("kwargs,msg", [
    ({"style": "fancy"}, "unknown style"),
    ({"align": "middle"}, "unknown align"),
    ({"align": ["left", "left", "left"]}, "align has 3 entries"),
    ({"max_col_width": 0}, "invalid max_col_width"),
    ({"width": 0}, "invalid width"),
    ({"ambiguous_width": 3}, "ambiguous_width"),
])
def test_errors(kwargs, msg):
    with pytest.raises(ValueError, match=msg):
        table([["a", "b"]], **kwargs)


def test_wrap_kwargs_forwarded():
    out = table([["あいう。えお"]], max_col_width=6, hanging=True)
    assert out.splitlines()[0] == "あいう。"


# --- cli -------------------------------------------------------------------

def run_cli(monkeypatch, capsys, data, *args):
    monkeypatch.setattr("sys.stdin", io.StringIO(data))
    assert main(["--table", *args]) == 0
    return capsys.readouterr().out


def test_cli_csv(monkeypatch, capsys):
    out = run_cli(monkeypatch, capsys, '名前,説明\n太郎,"a, b"\n', "--style", "grid")
    assert out.splitlines()[1] == "│ 名前 │ 説明 │"
    assert "│ 太郎 │ a, b │" in out


def test_cli_tsv_autodetect(monkeypatch, capsys):
    out = run_cli(monkeypatch, capsys, "名前\t点\n花子\t90\n")
    assert out.splitlines() == ["名前  点", "----  --", "花子  90"]


def test_cli_explicit_delimiter_and_no_header(monkeypatch, capsys):
    out = run_cli(monkeypatch, capsys, "a;b\nc;d\n", "--delimiter", ";", "--no-header")
    assert out.splitlines() == ["a  b", "c  d"]
    out = run_cli(monkeypatch, capsys, "a,b\tc\n", "--delimiter", "\\t", "--no-header",
                  "--style", "plain")
    assert out.splitlines() == ["a,b  c"]


def test_cli_width_budget(monkeypatch, capsys, tmp_path):
    f = tmp_path / "t.csv"
    f.write_text("都市,説明\n東京,日本の首都。人口は約1400万人で、世界有数の大都市です。\n",
                 encoding="utf-8")
    assert main(["--table", "-w", "24", "--style", "grid", str(f)]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert len(lines) > 5 and {width(line) for line in lines} <= {23, 24}
    assert len({width(line) for line in lines}) == 1


def test_cli_markdown(monkeypatch, capsys):
    out = run_cli(monkeypatch, capsys, "h\nx|y\n", "--style", "markdown")
    assert out.splitlines() == ["| h    |", "| :--- |", "| x\\|y |"]


def test_table_passes_rules_to_wrap():
    from kinsoku import table as _table, wrap as _wrap

    plain = _table([["あいッう"]], width=4, style="plain")
    loose = _table([["あいッう"]], width=4, style="plain", rules="loose")
    assert [l.rstrip() for l in plain.split("\n")] == _wrap("あいッう", 4)
    assert [l.rstrip() for l in loose.split("\n")] == ["あい", "ッう"]
