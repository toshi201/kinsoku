"""Command line interface: ``kinsoku [-w N] [FILE ...]``."""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from . import __version__
from ._core import fill, truncate, width


def _default_width() -> int:
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        prog="kinsoku",
        description="Wrap Japanese/CJK text by display width with kinsoku shori.",
    )
    p.add_argument("files", nargs="*", help="input files (default: stdin)")
    p.add_argument("-w", "--width", type=int, default=None,
                   help="max columns per line (default: terminal width or 80)")
    p.add_argument("--hanging", action="store_true",
                   help="let 、。,. hang past the margin (ぶら下げ)")
    p.add_argument("--no-break-long-words", action="store_true",
                   help="never split words wider than the line")
    p.add_argument("--ambiguous-width", type=int, choices=(1, 2), default=1,
                   help="width of East Asian Ambiguous chars (default: 1)")
    p.add_argument("--truncate", action="store_true",
                   help="truncate each line with … instead of wrapping")
    p.add_argument("--width-of", action="store_true",
                   help="print the display width of each input line")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)

    w = args.width or _default_width()
    if w < 1:
        p.error("width must be > 0")

    chunks = []
    if args.files:
        for path in args.files:
            with open(path, encoding="utf-8") as f:
                chunks.append(f.read())
    else:
        chunks.append(sys.stdin.read())
    text = "".join(chunks)

    if args.width_of:
        for line in text.splitlines():
            print(width(line, args.ambiguous_width))
        return 0
    if args.truncate:
        for line in text.splitlines():
            print(truncate(line, w, ambiguous_width=args.ambiguous_width))
        return 0
    print(fill(
        text.rstrip("\n"),
        w,
        hanging=args.hanging,
        break_long_words=not args.no_break_long_words,
        ambiguous_width=args.ambiguous_width,
    ))
    return 0
