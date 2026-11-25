"""Invariant checks on a large generated text.

These guard performance work: whatever the implementation does internally,
wrapping must keep every line within the width, lose no text, and respect
kinsoku rules.
"""

import random
import re

import pytest

import kinsoku
from kinsoku import HANGABLE, NO_END, NO_START, strip_ansi

KANJI = "吾輩猫名前無生頓見当薄暗所泣記憶人間始書生種族中一番獰悪掌載持上時感"
KANA = "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをんアイウエオカキクケコッャュョー"
WORDS = ["Python", "terminal", "UTF-8", "example.com", "supercalifragilisticexpialidocious"]
_SPACE_BEFORE = re.compile("[ \u3000]+(?=[%s])" % re.escape("".join(NO_START)))
_SPACE_AFTER = re.compile("([%s])[ \u3000]+" % re.escape("".join(NO_END)))
COLORS = ["\x1b[31m", "\x1b[1;34m", "\x1b[38;5;208m"]


def _generate(n_paragraphs: int = 300, seed: int = 6) -> list:
    rng = random.Random(seed)
    paras = []
    for _ in range(n_paragraphs):
        sentences = []
        for _ in range(rng.randint(1, 8)):
            parts = []
            for _ in range(rng.randint(2, 10)):
                r = rng.random()
                if r < 0.4:
                    parts.append("".join(rng.choices(KANJI, k=rng.randint(1, 3))))
                elif r < 0.8:
                    parts.append("".join(rng.choices(KANA, k=rng.randint(1, 4))))
                elif r < 0.88:
                    parts.append(" " + rng.choice(WORDS) + " ")
                elif r < 0.94:
                    parts.append(rng.choice("、、，・…"))
                else:
                    word = "".join(rng.choices(KANJI + KANA, k=rng.randint(2, 4)))
                    parts.append(rng.choice(COLORS) + word + "\x1b[0m")
            s = "".join(parts) + rng.choice("。。。！？")
            if rng.random() < 0.25:
                s = rng.choice(["「", "『", "（"]) + s + rng.choice(["」", "』", "）"])
            sentences.append(s)
        para = "　" + "".join(sentences)
        # A space is a legal break point even next to kinsoku characters, so
        # keep spaces away from them to make the kinsoku checks meaningful.
        para = _SPACE_BEFORE.sub("", para)
        para = _SPACE_AFTER.sub(r"\1", para)
        paras.append(para)
    return paras


PARAS = _generate()
TEXT = "\n".join(PARAS)


def _squash(s: str) -> str:
    """Remove escapes and the spaces that wrapping may drop at line breaks."""
    return strip_ansi(s).replace(" ", "").replace("　", "")


@pytest.mark.parametrize("width", [4, 10, 17, 40, 80])
@pytest.mark.parametrize("hanging", [False, True])
def test_invariants(width, hanging):
    init, sub = "> ", "  "
    whole = kinsoku.wrap(
        TEXT, width, initial_indent=init, subsequent_indent=sub, hanging=hanging
    )
    rebuilt = []
    for para in PARAS:
        lines = kinsoku.wrap(
            para, width, initial_indent=init, subsequent_indent=sub, hanging=hanging
        )
        rebuilt.extend(lines)

        body = []
        for i, line in enumerate(lines):
            indent = init if i == 0 else sub
            assert line.startswith(indent)
            line = line[len(indent):]
            body.append(line)

            # every line fits (hangable punctuation may hang past the margin)
            visible = strip_ansi(line)
            fitted = visible.rstrip("".join(HANGABLE)) if hanging else visible
            assert kinsoku.width(fitted) <= width - len(indent), (width, line)

            # kinsoku rules: a break may only violate them when it is forced,
            # i.e. a run with no allowed break point was hard-split, which
            # always fills the previous line completely.
            if i > 0 and visible:
                prev = strip_ansi(body[i - 1])
                if visible[0] in NO_START or prev[-1:] in NO_END:
                    prev_limit = width - len(init if i == 1 else sub)
                    full = kinsoku.width(prev) + kinsoku.char_width(visible[0])
                    assert full > prev_limit, (width, prev, line)
                    if width >= 40:
                        # wide enough that the generated text never needs it
                        pytest.fail(f"forced kinsoku violation: {prev!r} / {line!r}")

        # no text is lost or duplicated
        assert _squash("".join(body)) == _squash(para)
    assert whole == rebuilt


@pytest.mark.parametrize("ambiguous_width", [1, 2])
def test_width_is_sum_of_char_widths(ambiguous_width):
    plain = strip_ansi(TEXT)
    expected = sum(kinsoku.char_width(c, ambiguous_width) for c in plain)
    assert kinsoku.width(TEXT, ambiguous_width) == expected
    for line in kinsoku.wrap(TEXT, 30, ambiguous_width=ambiguous_width):
        assert kinsoku.width(line, ambiguous_width) <= 30


def test_fast_paths_match_general_path():
    for cp in range(0x3100):
        ch = chr(cp)
        assert kinsoku.width(ch) == kinsoku.char_width(ch)
        assert kinsoku.width(ch * 3) == 3 * kinsoku.char_width(ch)
    assert kinsoku.width("hello world") == 11
    assert kinsoku.width("tab\there") == 7
    assert kinsoku.width("") == 0
