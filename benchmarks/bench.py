"""Micro-benchmark for kinsoku.

Generates a deterministic, Aozora-Bunko-like Japanese text (~1 MB UTF-8)
and times ``kinsoku.wrap`` / ``kinsoku.width`` against ``textwrap.wrap``
as a reference point.

    python benchmarks/bench.py [--size BYTES] [--repeat N]
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import textwrap
import time

try:
    import kinsoku
except ImportError:  # not installed: use the source tree
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
    import kinsoku

KANJI = "吾輩猫名前無生頓見当薄暗所泣記憶人間始書生種族中一番獰悪掌載持上時感"
HIRAGANA = (
    "あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん"
)
KATAKANA = (
    "アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲン"
)
SMALL = "ゃゅょっャュョッー"
WORDS = ["Python", "terminal", "UTF-8", "kinsoku", "API", "example.com", "v1.2.3"]
COLORS = ["\x1b[31m", "\x1b[32m", "\x1b[1;34m", "\x1b[38;5;208m"]
RESET = "\x1b[0m"
LONG_WORD_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"


def _phrase(rng: random.Random) -> str:
    parts = []
    for _ in range(rng.randint(2, 6)):
        r = rng.random()
        if r < 0.35:
            parts.append("".join(rng.choices(KANJI, k=rng.randint(1, 3))))
        elif r < 0.75:
            parts.append("".join(rng.choices(HIRAGANA, k=rng.randint(1, 4))))
        elif r < 0.85:
            parts.append("".join(rng.choices(KATAKANA + SMALL, k=rng.randint(2, 5))))
        elif r < 0.93:
            parts.append(" " + rng.choice(WORDS) + " ")
        else:
            word = "".join(rng.choices(KANJI + HIRAGANA, k=rng.randint(2, 4)))
            parts.append(rng.choice(COLORS) + word + RESET)
    return "".join(parts)


def _sentence(rng: random.Random) -> str:
    body = "、".join(_phrase(rng) for _ in range(rng.randint(1, 4)))
    end = rng.choice("。。。。！？…")
    if rng.random() < 0.2:
        return "「" + body + end + "」"
    if rng.random() < 0.05:
        return "（" + body + "）" + end
    return body + end


def generate(size: int = 1_000_000, seed: int = 6) -> str:
    """Return deterministic Japanese-like text of roughly ``size`` UTF-8 bytes."""
    rng = random.Random(seed)
    paras = []
    total = 0
    while total < size:
        p = "　" + "".join(_sentence(rng) for _ in range(rng.randint(1, 12)))
        paras.append(p)
        total += len(p.encode("utf-8")) + 1
    return "\n".join(paras)


def best(fn, repeat: int) -> float:
    times = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return min(times)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="kinsoku benchmark")
    ap.add_argument("--size", type=int, default=1_000_000, help="text size in bytes")
    ap.add_argument("--repeat", type=int, default=3, help="runs per case (best is shown)")
    ap.add_argument(
        "--long-word",
        type=int,
        default=200_000,
        help="length of the long-word case (chars)",
    )
    args = ap.parse_args(argv)

    text = generate(args.size)
    lines = text.splitlines()
    nbytes = len(text.encode("utf-8"))
    print(
        f"kinsoku {kinsoku.__version__}, Python {sys.version.split()[0]}: "
        f"{nbytes:,} bytes, {len(text):,} chars, "
        f"{len(lines):,} paragraphs, best of {args.repeat}"
    )

    def tw(w):
        return lambda: [textwrap.wrap(l, w) for l in lines]

    # one long word without spaces (base64, hashes, minified JS), #43
    rng = random.Random(43)
    long_word = "".join(rng.choices(LONG_WORD_CHARS, k=args.long_word))

    # hard-wrapped text with no blank lines: one paragraph of ~1 MB, #66
    hard = "\n".join(kinsoku.wrap(text, 40)) + "\n"
    hard_mb = len(hard.encode("utf-8")) / 1e6

    cases = [
        ("kinsoku.wrap(width=40)", lambda: kinsoku.wrap(text, 40)),
        ("kinsoku.wrap(width=80)", lambda: kinsoku.wrap(text, 80)),
        ("kinsoku.wrap(width=40, balance)", lambda: kinsoku.wrap(text, 40, balance=True)),
        ("kinsoku.wrap(width=80, balance)", lambda: kinsoku.wrap(text, 80, balance=True)),
        ("kinsoku.width", lambda: kinsoku.width(text)),
        ("textwrap.wrap(width=40) [ref]", tw(40)),
        ("textwrap.wrap(width=80) [ref]", tw(80)),
        (
            f"kinsoku.wrap(long word {len(long_word) // 1000}k, 76)",
            lambda: kinsoku.wrap(long_word, 76),
        ),
        ("textwrap.wrap(long word, 76) [ref]", lambda: textwrap.wrap(long_word, 76)),
        ("kinsoku.unwrap(1 paragraph)", lambda: kinsoku.unwrap(hard)),
        ("kinsoku.rewrap(1 paragraph, 60)", lambda: kinsoku.rewrap(hard, 60)),
        (
            "kinsoku.rewrap(1 paragraph, 60, bal)",
            lambda: kinsoku.rewrap(hard, 60, balance=True),
        ),
        (
            "kinsoku.unwrap(indent_marks)",
            lambda: kinsoku.unwrap(hard, indent_marks_paragraph=True),
        ),
    ]
    print(f"{'case':<36} {'seconds':>9} {'MB/s':>8}")
    print("-" * 55)
    mb = nbytes / 1e6
    for name, fn in cases:
        t = best(fn, args.repeat)
        if "long word" in name:
            size = len(long_word) / 1e6
        elif "unwrap" in name or "rewrap" in name:
            size = hard_mb
        else:
            size = mb
        print(f"{name:<36} {t:>9.4f} {size / t:>8.2f}")


if __name__ == "__main__":
    main()
