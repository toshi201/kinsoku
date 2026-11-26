"""Command line interface: ``kinsoku [-w N] [FILE ...]``."""

from __future__ import annotations

import argparse
import codecs
import csv
import io
import os
import shutil
import sys

from . import __version__
from ._core import PRESETS, fill, strip_ruby, truncate, width
from .table import STYLES, table
from .tategaki import tategaki
from .unwrap import rewrap, unwrap


def _default_width() -> int:
    # COLUMNS env var -> terminal size of stdout -> 80
    return shutil.get_terminal_size((80, 24)).columns


def _table_default_width(style: str) -> int | None:
    """Width cap for ``--table`` when ``-w`` is omitted (#68).

    * ``markdown``: no cap. The output is meant to be saved and rendered
      elsewhere, and ``<br>`` joins never line up in a terminal anyway.
    * ``COLUMNS`` set to a positive integer: that value.
    * stdout is a terminal: the terminal width.
    * otherwise (pipe or redirect): no cap, the same as before #68.
    """
    if style == "markdown":
        return None
    try:
        columns = int(os.environ.get("COLUMNS", ""))
    except ValueError:
        columns = 0
    if columns > 0:
        return columns
    try:
        tty = sys.stdout.isatty()
    except (AttributeError, ValueError):
        tty = False
    if tty:
        return shutil.get_terminal_size((80, 24)).columns
    return None


def _input_encoding(encoding: str) -> str:
    """UTF-8 input is read as utf-8-sig so that a leading BOM is dropped."""
    return "utf-8-sig" if codecs.lookup(encoding).name == "utf-8" else encoding


def _read_input(path: str, encoding: str) -> str:
    """Read one input ("-" is stdin). Raises OSError / UnicodeDecodeError."""
    encoding = _input_encoding(encoding)
    if path == "-":
        buf = getattr(sys.stdin, "buffer", None)
        if buf is None:  # e.g. replaced by a StringIO
            text = sys.stdin.read()
            if encoding == "utf-8-sig" and text.startswith("\ufeff"):
                text = text[1:]
            return text
        data: bytes = buf.read()
        return data.decode(encoding)
    with open(path, encoding=encoding) as f:
        return f.read()


# Mode-dependent options: (flag, dest, default). An option still at its
# default counts as "not given".
_OPTIONS = (
    ("--width", "width", None),
    ("--hanging", "hanging", False),
    ("--no-break-long-words", "no_break_long_words", False),
    ("--keep-all", "keep_all", False),
    ("--indent", "indent", ""),
    ("--subsequent-indent", "subsequent_indent", ""),
    ("--max-lines", "max_lines", None),
    ("--ambiguous-width", "ambiguous_width", 1),
    ("--rules", "rules", "ja"),
    ("--ansi-reflow", "ansi_reflow", False),
    ("--ruby", "ruby", False),
    ("--ruby-width", "ruby_width", "full"),
    ("--tabsize", "tabsize", 8),
    ("--gap", "gap", None),
    ("--indent-marks-paragraph", "indent_marks_paragraph", False),
    ("--cjk-latin-space", "cjk_latin_space", False),
    ("--delimiter", "delimiter", None),
    ("--no-header", "no_header", False),
    ("--style", "style", "simple"),
    ("--placeholder", "placeholder", None),
    ("--balance", "balance", False),
)

_WRAP_OPTS = frozenset(
    {
        "width",
        "hanging",
        "no_break_long_words",
        "keep_all",
        "indent",
        "subsequent_indent",
        "max_lines",
        "placeholder",
        "ambiguous_width",
        "rules",
        "ansi_reflow",
        "tabsize",
    }
)

# The options each mode accepts ("" is plain wrapping). --encoding and the
# input files are accepted everywhere.
_MODE_OPTIONS = {
    "": _WRAP_OPTS | {"ruby", "ruby_width", "balance"},
    "--truncate": frozenset({"width", "placeholder", "ambiguous_width", "tabsize"}),
    "--width-of": frozenset({"ambiguous_width", "tabsize"}),
    # --ruby: the ruby annotations are removed (strip_ruby) before layout
    "--tategaki": frozenset({"gap", "ruby"}),
    "--table": frozenset(
        {
            "width",
            "hanging",
            "no_break_long_words",
            "keep_all",
            "ambiguous_width",
            "rules",
            "delimiter",
            "no_header",
            "style",
        }
    ),
    "--unwrap": frozenset({"indent_marks_paragraph", "cjk_latin_space"}),
    "--rewrap": _WRAP_OPTS
    | {
        "ruby",
        "ruby_width",
        "indent_marks_paragraph",
        "cjk_latin_space",
        "balance",
    },
}


def _mode(args: argparse.Namespace) -> str:
    if args.tategaki is not None:
        return "--tategaki"
    for flag in ("--truncate", "--width-of", "--unwrap", "--rewrap", "--table"):
        if getattr(args, flag[2:].replace("-", "_")):
            return flag
    return ""


def _check_options(p: argparse.ArgumentParser, args: argparse.Namespace, mode: str) -> None:
    allowed = _MODE_OPTIONS[mode]
    for opt, dest, default in _OPTIONS:
        if dest in allowed or getattr(args, dest) == default:
            continue
        if mode:
            p.error(f"{opt} cannot be used with {mode}")
        modes = [m for m, a in _MODE_OPTIONS.items() if m and dest in a]
        p.error(f"{opt} requires {' or '.join(modes)}")


def main(argv: list[str] | None = None) -> int:
    """Entry point. Errors raised while writing the output are reported
    without a traceback (#67)."""
    try:
        code = _main(argv)
        sys.stdout.flush()
    except BrokenPipeError:
        # The reader went away (``kinsoku ... | head``). Following the
        # "Note on SIGPIPE" in the signal module docs, point stdout at
        # devnull so the flush at interpreter exit does not fail again,
        # and exit like a process killed by SIGPIPE (128 + 13).
        _silence_stdout()
        return 141
    except KeyboardInterrupt:
        return 130
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "the output encoding"
        sys.stderr.write(
            f"kinsoku: error: cannot encode output as {enc} (try PYTHONIOENCODING=utf-8)\n"
        )
        return 1
    return code


def _silence_stdout() -> None:
    try:
        fd = sys.stdout.fileno()
    except (AttributeError, OSError, ValueError):
        return  # not a real file (e.g. replaced in tests)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, fd)
    finally:
        os.close(devnull)


def _main(argv: list[str] | None) -> int:
    p = argparse.ArgumentParser(
        prog="kinsoku",
        description="Wrap Japanese/CJK text by display width with kinsoku shori.",
    )
    p.add_argument("files", nargs="*", help="input files; '-' is stdin (default: stdin)")
    p.add_argument(
        "-w",
        "--width",
        type=int,
        default=None,
        help="max columns per line (default: $COLUMNS, terminal width, or 80); "
        "with --table, 0 means no limit",
    )
    p.add_argument(
        "--hanging", action="store_true", help="let 、。,. hang past the margin (ぶら下げ)"
    )
    p.add_argument(
        "--no-break-long-words", action="store_true", help="never split words wider than the line"
    )
    p.add_argument(
        "--keep-all",
        action="store_true",
        help="break only at spaces (word-break: keep-all, for Korean)",
    )
    p.add_argument(
        "-i", "--indent", default="", help="indent for the first line of each paragraph (e.g. '　')"
    )
    p.add_argument("-s", "--subsequent-indent", default="", help="indent for the other lines")
    p.add_argument(
        "-n", "--max-lines", type=int, default=None, help="keep at most N lines, ending with …"
    )
    p.add_argument(
        "--ambiguous-width",
        type=int,
        choices=(1, 2),
        default=1,
        help="width of East Asian Ambiguous chars (default: 1)",
    )
    p.add_argument(
        "--rules", choices=tuple(PRESETS), default="ja", help="kinsoku rules preset (default: ja)"
    )
    p.add_argument(
        "--ansi-reflow",
        action="store_true",
        help="close ANSI colors/links at each line end and reopen them on the next line",
    )
    p.add_argument(
        "--ruby", action="store_true", help="keep ruby notation (｜漢字《かんじ》) unbroken"
    )
    p.add_argument(
        "--ruby-width",
        choices=("base", "full"),
        default="full",
        help="with --ruby: count only the base text (base) or the whole notation (full, default)",
    )
    p.add_argument(
        "--tabsize", type=int, default=8, help="expand tabs to multiples of N columns (default: 8)"
    )
    p.add_argument(
        "--balance",
        action="store_true",
        help="even out the line lengths (same number of lines as the default wrapping)",
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--truncate", action="store_true", help="truncate each line with … instead of wrapping"
    )
    mode.add_argument(
        "--width-of", action="store_true", help="print the display width of each input line"
    )
    mode.add_argument(
        "--tategaki",
        type=int,
        default=None,
        metavar="HEIGHT",
        help="vertical layout (縦書き), HEIGHT chars per column",
    )
    mode.add_argument(
        "--unwrap", action="store_true", help="join hard-wrapped lines back into paragraphs"
    )
    mode.add_argument("--rewrap", action="store_true", help="unwrap, then wrap again to -w columns")
    mode.add_argument(
        "--table",
        action="store_true",
        help="format CSV/TSV input as a table (-w is the total width budget; -w 0: no limit; "
        "-w omitted: $COLUMNS or the terminal width when stdout is a tty, else no limit; "
        "markdown: no limit unless -w is given)",
    )
    p.add_argument(
        "--gap", type=int, default=None, help="with --tategaki: spaces between columns (default: 1)"
    )
    p.add_argument(
        "--indent-marks-paragraph",
        action="store_true",
        help="with --unwrap/--rewrap: an indented line starts a new paragraph",
    )
    p.add_argument(
        "--delimiter",
        default=None,
        help="CSV delimiter for --table (default: tab if the first line "
        "has one, else comma; '\\t' means tab)",
    )
    p.add_argument(
        "--no-header", action="store_true", help="with --table: the first row is data, not a header"
    )
    p.add_argument(
        "--style",
        choices=STYLES,
        default="simple",
        help="table style for --table (default: simple)",
    )
    p.add_argument(
        "--placeholder", default=None, help="marker for cut text with --truncate / -n (default: …)"
    )
    p.add_argument(
        "--encoding",
        default="utf-8",
        help="input encoding (default: utf-8, a leading BOM is removed; e.g. cp932 / shift_jis "
        "for Aozora Bunko texts)",
    )
    p.add_argument(
        "--cjk-latin-space",
        action="store_true",
        help="with --unwrap/--rewrap: put a space where CJK meets "
        "latin text or digits at a line break",
    )
    p.add_argument("-V", "--version", action="version", version=f"%(prog)s {__version__}")
    args = p.parse_args(argv)

    w = args.width if args.width is not None else _default_width()
    if args.table and args.width == 0:
        pass  # --table -w 0: no width limit (#68)
    elif w < 1:
        p.error("width must be > 0")
    if args.max_lines is not None and args.max_lines < 1:
        p.error("--max-lines must be >= 1")
    _check_options(p, args, _mode(args))
    tate = args.tategaki is not None
    if tate:
        if args.tategaki < 1:
            p.error("--tategaki HEIGHT must be >= 1")
        if args.gap is not None and args.gap < 0:
            p.error("--gap must be >= 0")
    placeholder = "…" if args.placeholder is None else args.placeholder
    try:
        codecs.lookup(args.encoding)
    except LookupError:
        p.error(f"unknown encoding: {args.encoding}")

    chunks = []
    for path in args.files or ["-"]:
        name = "<stdin>" if path == "-" else path
        try:
            chunk = _read_input(path, args.encoding)
        except UnicodeDecodeError:
            p.exit(
                1,
                f"{p.prog}: error: {name}: cannot decode as "
                f"{args.encoding} (try --encoding, e.g. --encoding cp932)\n",
            )
        except OSError as e:
            p.exit(1, f"{p.prog}: error: {name}: {e.strerror or e}\n")
        # Each file is its own block: a missing final newline must not
        # glue the last line to the next file's first line.
        if chunk and not chunk.endswith("\n"):
            chunk += "\n"
        chunks.append(chunk)
    text = "".join(chunks)

    if tate:
        gap = 1 if args.gap is None else args.gap
        if args.ruby:
            text = strip_ruby(text)
        try:
            out = tategaki(text.rstrip("\n"), args.tategaki, gap=gap)
        except ValueError as e:
            p.error(str(e))
        print(out)
        return 0
    if args.table:
        if args.width is None:
            tw = _table_default_width(args.style)
        else:
            tw = None if args.width == 0 else args.width
        return _table(p, args, text, tw)
    if args.width_of:
        for line in text.splitlines():
            print(width(line, args.ambiguous_width, tabsize=args.tabsize))
        return 0
    if args.truncate:
        try:
            lines = [
                truncate(
                    line,
                    w,
                    placeholder=placeholder,
                    ambiguous_width=args.ambiguous_width,
                    tabsize=args.tabsize,
                )
                for line in text.splitlines()
            ]
        except ValueError as e:
            p.error(str(e))
        for line in lines:
            print(line)
        return 0
    if args.unwrap:
        out = unwrap(
            text,
            indent_marks_paragraph=args.indent_marks_paragraph,
            cjk_latin_space=args.cjk_latin_space,
        )
    elif args.rewrap:
        try:
            out = rewrap(
                text,
                w,
                indent_marks_paragraph=args.indent_marks_paragraph,
                cjk_latin_space=args.cjk_latin_space,
                hanging=args.hanging,
                break_long_words=not args.no_break_long_words,
                keep_all=args.keep_all,
                initial_indent=args.indent,
                subsequent_indent=args.subsequent_indent,
                max_lines=args.max_lines,
                placeholder=placeholder,
                ambiguous_width=args.ambiguous_width,
                rules=args.rules,
                ansi_reflow=args.ansi_reflow,
                tabsize=args.tabsize,
                ruby=args.ruby,
                ruby_width=args.ruby_width,
                balance=args.balance,
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
            placeholder=placeholder,
            ambiguous_width=args.ambiguous_width,
            rules=args.rules,
            ansi_reflow=args.ansi_reflow,
            ruby=args.ruby,
            ruby_width=args.ruby_width,
            tabsize=args.tabsize,
            balance=args.balance,
        )
    except ValueError as e:
        p.error(str(e))
    print(out)
    return 0


def _table(p: argparse.ArgumentParser, args: argparse.Namespace, text: str, w: int | None) -> int:
    delim = args.delimiter
    if delim in ("\\t", "tab"):
        delim = "\t"
    if delim is None:
        first = text.split("\n", 1)[0]
        delim = "\t" if "\t" in first else ","
    if len(delim) != 1:
        p.error("--delimiter must be a single character")
    rows = [r for r in csv.reader(io.StringIO(text), delimiter=delim) if r]
    headers = None
    if rows and not args.no_header:
        headers, rows = rows[0], rows[1:]
    try:
        out = table(
            rows,
            headers,
            width=w,
            style=args.style,
            ambiguous_width=args.ambiguous_width,
            hanging=args.hanging,
            break_long_words=not args.no_break_long_words,
            keep_all=args.keep_all,
            rules=args.rules,
        )
    except ValueError as e:
        p.error(str(e))
    if out:
        print(out)
    return 0
