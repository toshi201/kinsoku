"""Count breaks in the middle of a word with and without ``phrase=True`` (#77).

python benchmarks/phrase_eval.py
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    import kinsoku
except ImportError:  # not installed: use the source tree
    sys.path.insert(0, os.path.join(HERE, "..", "src"))
    import kinsoku
sys.path.insert(0, os.path.join(HERE, "..", "tests"))
from phrase_corpus import CORPUS  # noqa: E402

WIDTHS = range(8, 31, 2)


def count(phrase: bool) -> tuple[int, int, int]:
    """(breaks, breaks in the middle of a word, lines)"""
    breaks = bad = lines = 0
    for marked in CORPUS:
        text = marked.replace("/", "")
        ok = set()
        pos = 0
        for part in marked.split("/"):
            pos += len(part)
            ok.add(pos)
        for w in WIDTHS:
            out = kinsoku.wrap(text, w, phrase=phrase)
            assert "".join(out) == text
            lines += len(out)
            pos = 0
            for line in out[:-1]:
                pos += len(line)
                breaks += 1
                bad += pos not in ok
    return breaks, bad, lines


def main() -> None:
    print(f"{len(CORPUS)} sentences, widths {WIDTHS.start}-{WIDTHS.stop - 1} step {WIDTHS.step}")
    for phrase in (False, True):
        b, bad, n = count(phrase)
        print(f"phrase={phrase!s:5}  lines {n:4}  breaks {b:4}  mid-word {bad:4} ({bad / b:.1%})")


if __name__ == "__main__":
    main()
