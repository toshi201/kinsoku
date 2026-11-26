"""unwrap / rewrap in linear time (#66).

The joined paragraph used to be passed whole to ``_separator`` for every
line, which made long paragraphs quadratic. The output must not change:
the random tests compare against a copy of the old implementation.
"""

import importlib
import random
import time
from collections.abc import Iterator

import pytest

from kinsoku import rewrap, unwrap
from kinsoku._core import strip_ansi
from kinsoku.cli import main

# ``kinsoku.unwrap`` is the function; get the module itself.
U = importlib.import_module("kinsoku.unwrap")

# --- the implementation before #66 (reference) --------------------------------


def _old_separator(left: str, right: str, cjk_latin_space: bool = False) -> str:
    lv, rv = strip_ansi(left), strip_ansi(right)
    if not lv or not rv:
        return ""
    if lv[-1] == "-" and len(lv) >= 2 and U._is_latin_letter(lv[-2]):
        return ""
    lc, rc = U._pick(lv, True), U._pick(rv, False)
    if U._is_cjk_punct(lc) or U._is_cjk_punct(rc):
        return ""
    lw, rw = U._is_wide(lc), U._is_wide(rc)
    if lw and rw:
        return ""
    if not cjk_latin_space and ((lw and not U._is_hangul(lc)) or (rw and not U._is_hangul(rc))):
        return ""
    return " "


def _old_paragraphs(
    text: str, indent_marks_paragraph: bool, cjk_latin_space: bool = False
) -> Iterator[tuple[bool, str, str]]:
    cur: str | None = None
    term = ""
    for body, t in U._split_lines(text):
        if U._is_blank(body):
            if cur is not None:
                yield False, cur, term
                cur = None
            yield True, body, t
        elif cur is None or U._starts_paragraph(body, indent_marks_paragraph):
            if cur is not None:
                yield False, cur, term
            cur, term = U._rstrip_visible(body), t
        else:
            nxt = U._lstrip_half(body)
            cur = cur + _old_separator(cur, nxt, cjk_latin_space) + U._rstrip_visible(nxt)
            term = t
    if cur is not None:
        yield False, cur, term


def _old_unwrap(text: str, **kw: bool) -> str:
    return "".join(
        b + t
        for _, b, t in _old_paragraphs(
            text, kw.get("indent_marks_paragraph", False), kw.get("cjk_latin_space", False)
        )
    )


# --- random inputs --------------------------------------------------------------

ATOMS = [
    # Japanese, punctuation, brackets, neutral punctuation
    *"あいうかきアイ漢字吾輩猫ー々",
    *"、。「」（）！？・",
    "…",
    "……",
    "―",
    "─",
    "‥",
    # Hangul, half-width kana, full-width latin
    *"한국어",
    *"ｱｲ",
    "Ｐｙ",
    # Latin, digits, hyphens
    "Python",
    "well",
    "a",
    "x",
    "-",
    "--",
    "123",
    "v1.2",
    "e-",
    "'",
    '"',
    # whitespace
    " ",
    "  ",
    "\t",
    "　",
    # ANSI: complete, and fragments that a later line may complete
    "\x1b[31m",
    "\x1b[0m",
    "\x1b[1;34m",
    "\x1b]8;;http://x\x07",
    "\x1b]8;;\x1b\\",
    "\x1b",
    "\x1b[",
    "\x1b[3",
    "\x1b[1;",
    "\x1b]",
    "\x1b]8;;u",
    "\x07",
    "\\",
    "m",
    "[",
    "]",
    "\x1bM",
    "\x1b(",
]

STARTS = ["", "", "", "  ", "　", "\t", "- ", "* ", "・", "1. ", "2) ", "+ ", "• "]
TERMS = ["\n", "\n", "\n", "\r\n", "\r"]


def _line(rng: random.Random) -> str:
    return rng.choice(STARTS) + "".join(rng.choices(ATOMS, k=rng.randint(0, 8)))


def _text(rng: random.Random) -> str:
    out = []
    for _ in range(rng.randint(0, 25)):
        r = rng.random()
        if r < 0.1:
            out.append("")
        elif r < 0.15:
            out.append(rng.choice([" ", "　", "\x1b[0m", " \x1b[31m "]))
        else:
            out.append(_line(rng))
        out.append(rng.choice(TERMS))
    if out and rng.random() < 0.5:
        out.pop()  # no final terminator
    return "".join(out)


@pytest.mark.parametrize("seed", range(40))
def test_unwrap_matches_old_implementation(seed):
    rng = random.Random(seed)
    for _ in range(250):
        text = _text(rng)
        for imp in (False, True):
            for cls in (False, True):
                assert list(U._paragraphs(text, imp, cls)) == list(
                    _old_paragraphs(text, imp, cls)
                ), repr(text)
                kw = {"indent_marks_paragraph": imp, "cjk_latin_space": cls}
                assert unwrap(text, **kw) == _old_unwrap(text, **kw), repr(text)


def _result(fn, *args, **kw):
    """The return value, or the exception (type and message) it raised."""
    try:
        return fn(*args, **kw)
    except ValueError as e:
        return type(e), str(e)


@pytest.mark.parametrize("seed", range(10))
def test_rewrap_matches_old_implementation(seed, monkeypatch):
    rng = random.Random(1000 + seed)
    cases = []
    for _ in range(100):
        text = _text(rng)
        kw = {
            "indent_marks_paragraph": rng.random() < 0.5,
            "cjk_latin_space": rng.random() < 0.5,
        }
        width = rng.randint(4, 30)
        cases.append((text, width, kw, _result(rewrap, text, width, **kw)))
    monkeypatch.setattr(U, "_paragraphs", _old_paragraphs)
    for text, width, kw, new in cases:
        assert _result(rewrap, text, width, **kw) == new, repr(text)


def test_long_paragraph_matches_old_implementation():
    rng = random.Random(66)
    lines = ["".join(rng.choices([a for a in ATOMS if "\x1b" not in a], k=6)) for _ in range(400)]
    text = "\n".join(x for x in lines if x.strip())
    for cls in (False, True):
        assert unwrap(text, cjk_latin_space=cls) == _old_unwrap(text, cjk_latin_space=cls)


# --- speed -------------------------------------------------------------------------

# Generous: the fixed code takes well under a second for these, the old one
# 17 s or more (it grows with the square of the paragraph length).
LIMIT = 8.0


def _timed(fn):
    t0 = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - t0


def _wrapped_text(nbytes: int, ansi: bool = False) -> str:
    """Japanese text hard-wrapped at 40 columns, with no blank lines."""
    rng = random.Random(6)
    words = [
        "吾輩は",
        "猫である。",
        "名前は",
        "まだ無い。",
        "Python",
        "を使う",
        "「どこで",
        "生れたか」",
    ]
    lines = []
    size = 0
    while size < nbytes:
        line = "".join(rng.choices(words, k=6))
        if ansi and rng.random() < 0.3:
            line = "\x1b[31m" + line + "\x1b[0m"
        lines.append(line)
        size += len(line.encode()) + 1
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize("ansi", [False, True], ids=["plain", "ansi"])
def test_unwrap_2mb_paragraph_is_fast(ansi):
    text = _wrapped_text(2_000_000, ansi)
    out, t = _timed(lambda: unwrap(text))
    assert t < LIMIT, f"unwrap took {t:.1f}s"
    assert out.count("\n") == 1


def test_unwrap_many_short_lines_is_fast():
    text = "あ\n" * 200_000
    out, t = _timed(lambda: unwrap(text))
    assert t < LIMIT, f"unwrap took {t:.1f}s"
    assert out == "あ" * 200_000 + "\n"


def test_english_paragraph_is_fast():
    text = "the quick brown fox jumps over\n" * 60_000
    out, t = _timed(lambda: unwrap(text))
    assert t < LIMIT, f"unwrap took {t:.1f}s"
    assert out == " ".join(["the quick brown fox jumps over"] * 60_000) + "\n"


def test_rewrap_1mb_paragraph_is_fast():
    text = _wrapped_text(1_000_000)
    out, t = _timed(lambda: rewrap(text, 60))
    assert t < LIMIT, f"rewrap took {t:.1f}s"
    assert unwrap(out) == unwrap(text)


def test_cli_unwrap_is_fast(capsys, monkeypatch, tmp_path):
    path = tmp_path / "in.txt"
    path.write_text(_wrapped_text(1_000_000), encoding="utf-8")
    _, t = _timed(lambda: main(["--unwrap", str(path)]))
    assert t < LIMIT, f"kinsoku --unwrap took {t:.1f}s"
    assert capsys.readouterr().out.count("\n") == 1
