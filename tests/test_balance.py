"""balance=True: even line lengths with the greedy number of lines (#76)."""

from __future__ import annotations

import re
import time

import pytest

import kinsoku
from kinsoku import KinsokuWrapper, fill, rewrap, shorten, wrap
from kinsoku.cli import main
from kinsoku.table import table

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover
    given = None

AW = 1
JA = (
    "吾輩は猫である。名前はまだ無い。どこで生れたかとんと見当がつかぬ。"
    "何でも薄暗いじめじめした所でニャーニャー泣いていた事だけは記憶している。"
)
RED, END = "\x1b[31m", "\x1b[0m"
EN = "The quick brown fox jumps over the lazy dog and keeps running far away"


def _spread(lines: list[str], w: int) -> int:
    return sum((w - kinsoku.width(x)) ** 2 for x in lines)


def _check(text: str, w: int, **kw: object) -> list[str]:
    greedy = wrap(text, w, **kw)  # type: ignore[arg-type]
    bal = wrap(text, w, balance=True, **kw)  # type: ignore[arg-type]
    assert len(bal) == len(greedy)
    assert all(kinsoku.width(x) <= w for x in bal)
    return bal


def _content(lines: list[str]) -> str:
    return "".join("".join(lines).split())


@pytest.mark.parametrize("text,w", [(JA, 30), (EN, 30), (JA * 3, 40), (EN * 2, 25)])
def test_same_count_fits_same_content(text: str, w: int) -> None:
    greedy = wrap(text, w)
    bal = wrap(text, w, balance=True)
    assert len(bal) == len(greedy)
    assert all(kinsoku.width(x) <= w for x in bal)
    assert _content(bal) == _content(greedy)


def test_english_example_is_more_even() -> None:
    greedy = wrap(EN, 30)
    bal = wrap(EN, 30, balance=True)
    assert greedy[-1] == "far away"
    assert bal == ["The quick brown fox jumps", "over the lazy dog and", "keeps running far away"]
    assert _spread(bal, 30) < _spread(greedy, 30)


def test_japanese_example_is_more_even() -> None:
    greedy = wrap(JA, 30)
    bal = wrap(JA, 30, balance=True)
    assert len(bal) == len(greedy) == 5
    assert _spread(bal, 30) < _spread(greedy, 30)
    widths = [kinsoku.width(x) for x in bal]
    assert max(widths) - min(widths) < max(map(kinsoku.width, greedy)) - min(
        map(kinsoku.width, greedy)
    )


def test_short_last_line_is_lengthened() -> None:
    text = "あ" * 21  # greedy: 20 + 1
    assert wrap(text, 40) == ["あ" * 20, "あ"]
    assert wrap(text, 40, balance=True) == ["あ" * 11, "あ" * 10]


def test_kinsoku_respected() -> None:
    text = "あいうえお。かきくけこ、「さしすせそ」たちつてと。"
    for w in range(6, 30):
        for line in wrap(text, w, balance=True):
            assert line[0] not in kinsoku.NO_START
            assert line[-1] not in kinsoku.NO_END


def test_single_line_and_empty_unchanged() -> None:
    assert wrap("短い", 30, balance=True) == wrap("短い", 30)
    assert wrap("", 30, balance=True) == [""]
    assert wrap("\n\n", 30, balance=True) == wrap("\n\n", 30)


def test_per_paragraph() -> None:
    text = EN + "\n" + "あ" * 21
    out = wrap(text, 30, balance=True)
    assert out == wrap(EN, 30, balance=True) + wrap("あ" * 21, 30, balance=True)


def test_indent_and_hanging() -> None:
    bal = _check(JA, 30, initial_indent="　", subsequent_indent="  ")
    assert bal[0].startswith("　")
    assert all(x.startswith("  ") for x in bal[1:])
    assert all(kinsoku.width(x) <= 30 for x in bal)
    hb = wrap(JA, 30, hanging=True, balance=True)
    assert len(hb) == len(wrap(JA, 30, hanging=True))
    # a line may only exceed the width by hanging punctuation
    for line in hb:
        assert kinsoku.width(line) <= 30 or line[-1] in "、。"


def test_leading_whitespace_kept() -> None:
    text = "　" + JA
    bal = wrap(text, 30, balance=True)
    assert bal[0].startswith("　")
    assert len(bal) == len(wrap(text, 30))


def test_ansi_and_ruby() -> None:
    red = "\x1b[31m" + EN + "\x1b[0m"
    bal = wrap(red, 30, balance=True)
    assert [kinsoku.strip_ansi(x) for x in bal] == wrap(EN, 30, balance=True)
    reflow = wrap(red, 30, balance=True, ansi_reflow=True)
    assert all(x.endswith("\x1b[0m") for x in reflow)
    rb = "｜魔法少女《マジカルガール》は今日も町を守るためにがんばっているのだった。"
    out = wrap(rb, 34, ruby=True, balance=True)
    assert len(out) == len(wrap(rb, 34, ruby=True))
    assert "｜魔法少女《マジカルガール》" in "".join(out)


def test_long_word_falls_back_to_greedy() -> None:
    text = "x" * 50 + " short words here"
    assert wrap(text, 20, balance=True) == wrap(text, 20)


def test_max_lines_balances_before_cut() -> None:
    full = wrap(JA, 30, balance=True)
    cut = wrap(JA, 30, balance=True, max_lines=2)
    assert len(cut) == 2
    assert cut[0] == full[0]
    assert cut[1].endswith("…")


def test_api_entry_points() -> None:
    assert fill(EN, 30, balance=True) == "\n".join(wrap(EN, 30, balance=True))
    assert shorten(EN, 30, balance=True) == shorten(EN, 30)
    assert KinsokuWrapper(width=30, balance=True).wrap(EN) == wrap(EN, 30, balance=True)
    assert rewrap(EN, 30, balance=True) == fill(EN, 30, balance=True)
    t = table([["a", EN]], width=30, balance=True)
    assert "keeps running far away" in t
    assert "keeps running far away" not in table([["a", EN]], width=30)


def test_cli(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(EN + "\n"))
    assert main(["-w", "30", "--balance"]) == 0
    assert capsys.readouterr().out.splitlines() == wrap(EN, 30, balance=True)
    monkeypatch.setattr("sys.stdin", io.StringIO(EN + "\n"))
    assert main(["-w", "30", "--rewrap", "--balance"]) == 0
    assert capsys.readouterr().out.splitlines() == wrap(EN, 30, balance=True)
    monkeypatch.setattr("sys.stdin", io.StringIO("x\n"))
    with pytest.raises(SystemExit):
        main(["--truncate", "--balance"])


def test_long_paragraph_speed() -> None:
    text = JA * 200  # well over 2000 units: greedy fallback
    t = time.perf_counter()
    assert wrap(text, 70, balance=True) == wrap(text, 70)
    mid = JA * 20  # under the limit: dynamic programming
    wrap(mid, 70, balance=True)
    assert time.perf_counter() - t < 5


if given is not None:
    CHARS = "あいうえおかきくけこ漢字。、「」ーっabc de f.,()  "

    @settings(max_examples=300, deadline=None)
    @given(
        st.text(alphabet=CHARS, max_size=120),
        st.integers(min_value=4, max_value=40),
        st.booleans(),
    )
    def test_property(text: str, w: int, hanging: bool) -> None:
        greedy = wrap(text, w, hanging=hanging)
        bal = wrap(text, w, hanging=hanging, balance=True)
        assert len(bal) == len(greedy)
        assert _content(bal) == _content(greedy)
        for line in bal:
            if hanging:
                assert kinsoku.width(line.rstrip("、。,.")) <= w
            else:
                assert kinsoku.width(line) <= w


if given is not None:

    @settings(max_examples=300, deadline=None)
    @given(
        st.lists(
            st.sampled_from(
                ["あ", "い", "。", "、", "「", "」", "ab", " ", "c", "\u3000", RED, END]
            ),
            max_size=40,
        ).map("".join),
        st.integers(min_value=3, max_value=30),
    )
    def test_property_ansi_and_one_line(text: str, w: int) -> None:
        greedy = wrap(text, w)
        bal = wrap(text, w, balance=True)
        assert len(bal) == len(greedy)
        assert _content([kinsoku.strip_ansi(x) for x in bal]) == _content(
            [kinsoku.strip_ansi(x) for x in greedy]
        )
        assert "".join(_esc(x) for x in bal) == "".join(_esc(x) for x in greedy)
        if len(greedy) == 1:
            assert bal == greedy


def _esc(text: str) -> str:
    return "".join(re.findall(r"\x1b\[[0-9;]*m", text))
