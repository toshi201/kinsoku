"""Command line interface: ``kinsoku [-w N] [FILE ...]``."""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional

from . import __version__
from ._core import PRESETS, fill, truncate, width
from .tategaki import tategaki
from .unwrap import rewrap, unwrap


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
    p.add_argument("--keep-all", action="store_true",
                   help="break only at spaces (word-break: keep-all, for Korean)")
    p.add_argument("-i", "--indent", default="",
                   help="indent for the first line of each paragraph (e.g. '　')")
    p.add_argument("-s", "--subsequent-indent", default="",
                   help="indent for the other lines")
    p.add_argument("-n", "--max-lines", type=int, default=None,
                   help="keep at most N lines, ending with …")
    p.add_argument("--ambiguous-width", type=int, choices=(1, 2), default=1,
                   help="width of East Asian Ambiguous chars (default: 1)")
    p.add_argument("--rules", choices=tuple(PRESETS), default="ja",
                   help="kinsoku rules preset (default: ja)")
    p.add_argument("--ansi-reflow", action="store_true",
                   help="close ANSI colors/links at each line end and reopen them on the next line")
    p.add_argument("--truncate", action="store_true",
                   help="truncate each line with … instead of wrapping")
    p.add_argument("--width-of", action="store_true",
                   help="print the display width of each input line")
    p.add_argument("--tategaki", type=int, default=None, metavar="HEIGHT",
                   help="vertical layout (縦書き), HEIGHT chars per column")
    p.add_argument("--gap", type=int, default=1,
                   help="spaces between tategaki columns (default: 1)")
    p.add_argument("--unwrap", action="store_true",
                   help="join hard-wrapped lines back into paragraphs")
    p.add_argument("--rewrap", action="store_true",
                   help="unwrap, then wrap again to -w columns")
    p.add_argument("--indent-marks-paragraph", action="store_true",
                   help="with --unwrap/--rewrap: an indented line starts a new paragraph")
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)

    w = args.width or _default_width()
    if w < 1:
        p.error("width must be > 0")
    if args.unwrap and args.rewrap:
        p.error("--unwrap and --rewrap cannot be combined")
    if args.max_lines is not None and args.max_lines < 1:
        p.error("--max-lines must be >= 1")

    chunks = []
    if args.files:
        for path in args.files:
            with open(path, encoding="utf-8") as f:
                chunks.append(f.read())
    else:
        chunks.append(sys.stdin.read())
    text = "".join(chunks)

    if args.tategaki is not None:
        if args.tategaki < 1:
            p.error("--tategaki HEIGHT must be >= 1")
        if args.gap < 0:
            p.error("--gap must be >= 0")
        print(tategaki(text.rstrip("\n"), args.tategaki, gap=args.gap))
        return 0
    if args.width_of:
        for line in text.splitlines():
            print(width(line, args.ambiguous_width))
        return 0
    if args.truncate:
        for line in text.splitlines():
            print(truncate(line, w, ambiguous_width=args.ambiguous_width))
        return 0
    if args.unwrap:
        out = unwrap(text, indent_marks_paragraph=args.indent_marks_paragraph)
    elif args.rewrap:
        try:
            out = rewrap(
                text,
                w,
                indent_marks_paragraph=args.indent_marks_paragraph,
                hanging=args.hanging,
                break_long_words=not args.no_break_long_words,
                keep_all=args.keep_all,
                initial_indent=args.indent,
                subsequent_indent=args.subsequent_indent,
                max_lines=args.max_lines,
                ambiguous_width=args.ambiguous_width,
                rules=args.rules,
                ansi_reflow=args.ansi_reflow,
            )
        except ValueError as e:
            p.error(str(e))
    if args.unwrap or args.rewrap:
        sys.stdout.write(out if out.endswith("\n") or not out else out + "\n")
        return 0
    try:
        out = fill(
        text.rstrip("\n"),
        w,
        hanging=args.hanging,
        break_long_words=not args.no_break_long_words,
        keep_all=args.keep_all,
        initial_indent=args.indent,
        subsequent_indent=args.subsequent_indent,
        max_lines=args.max_lines,
        ambiguous_width=args.ambiguous_width,
        rules=args.rules,
        ansi_reflow=args.ansi_reflow,
        )
    except ValueError as e:
        p.error(str(e))
    print(out)
    return 0
