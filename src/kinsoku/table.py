"""Format rows of CJK/ANSI-aware text as an aligned table (:func:`table`)."""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional, Sequence, Union

from ._core import _check_align, _check_ambiguous_width, _check_width, pad, wrap
from ._core import width as _w

__all__ = ["table", "STYLES"]

STYLES = ("simple", "grid", "markdown", "plain")
_MIN_SHRINK = 4

_SGR = re.compile(r"\x1b\[[0-9;:]*m")
_RESET = "\x1b[0m"

# Box drawing characters are East Asian Ambiguous: with ambiguous_width=2
# they would be drawn two columns wide, so we fall back to ASCII.
_BOX = {
    "top": ("┌", "─", "┬", "┐"),
    "mid": ("├", "─", "┼", "┤"),
    "bottom": ("└", "─", "┴", "┘"),
    "v": "│",
}
_ASCII = {
    "top": ("+", "-", "+", "+"),
    "mid": ("+", "-", "+", "+"),
    "bottom": ("+", "-", "+", "+"),
    "v": "|",
}


def _cell(value: Any) -> str:
    return "" if value is None else str(value)


def _per_column(name: str, value: Any, ncols: int, default: Any) -> List[Any]:
    """Expand a scalar or per-column sequence to exactly ``ncols`` items."""
    if value is None or isinstance(value, (str, int)):
        return [default if value is None else value] * ncols
    items = list(value)
    if len(items) > ncols:
        raise ValueError(
            f"{name} has {len(items)} entries but the table has {ncols} columns"
        )
    return items + [default] * (ncols - len(items))


def _close_ansi(lines: List[str]) -> List[str]:
    """Make every line of a multi-line cell self-contained w.r.t. SGR colors.

    Active color codes are reset at the end of a line (so they never bleed
    into padding or borders) and re-applied at the start of the next one.
    """
    out: List[str] = []
    active = ""
    for line in lines:
        prefix = active
        for m in _SGR.finditer(line):
            code = m.group()
            active = "" if code in (_RESET, "\x1b[m") else active + code
        line = prefix + line
        out.append(line + _RESET if active else line)
    return out


def _cell_lines(text: str, limit: Optional[int], aw: int, wrap_kwargs: dict) -> List[str]:
    lines: List[str] = []
    for line in text.splitlines() or [""]:
        if limit is not None and _w(line, aw) > limit:
            lines.extend(wrap(line, limit, ambiguous_width=aw, **wrap_kwargs))
        else:
            lines.append(line)
    if "\x1b" in text:
        lines = _close_ansi(lines)
    return lines


def _md_escape(s: str) -> str:
    return s.replace("|", "\\|")


def table(
    rows: Iterable[Sequence[Any]],
    headers: Optional[Sequence[Any]] = None,
    *,
    align: Union[str, Sequence[str], None] = None,
    max_col_width: Union[int, Sequence[Optional[int]], None] = None,
    width: Optional[int] = None,
    style: str = "simple",
    ambiguous_width: int = 1,
    **wrap_kwargs: Any,
) -> str:
    """Render ``rows`` as a table aligned by display width.

    Wide (CJK) characters count as 2 columns and ANSI escape sequences as 0,
    so colored and Japanese cells line up in a terminal.

    :param rows: iterable of sequences; each cell is converted with ``str()``
        (``None`` becomes an empty cell). Rows shorter than the widest row
        (or the headers) are padded with empty cells.
    :param headers: optional header row.
    :param align: ``"left"`` (default), ``"right"`` or ``"center"`` (or
        ``"<"``, ``">"``, ``"^"``), or a sequence with one value per column
        (missing entries are left).
    :param max_col_width: maximum display width of a column (int, or a
        sequence of int/``None`` per column). Wider cells are wrapped with
        :func:`kinsoku.wrap`, so kinsoku rules apply inside cells. Embedded
        newlines always start a new line within the cell.
    :param width: total width budget of the table including separators and
        borders. If the table is wider, the widest columns are narrowed first
        (down to 4 columns each) and their cells wrapped. If it still does
        not fit, the narrowest possible table is returned.
    :param style: ``"simple"`` (header, dashed underline, 2-space gaps),
        ``"grid"`` (box drawing borders; ASCII ``+-|`` when
        ``ambiguous_width=2`` because box drawing characters are East Asian
        Ambiguous), ``"markdown"`` (GitHub pipe table; ``|`` is escaped and
        multi-line cells are joined with ``<br>``) or ``"plain"`` (no rules).
    :param ambiguous_width: width of East Asian Ambiguous characters (1 or 2).
    :param wrap_kwargs: passed to :func:`kinsoku.wrap` when wrapping cells
        (e.g. ``hanging``, ``keep_all``, ``break_long_words``).
    """
    if style not in STYLES:
        raise ValueError(f"unknown style {style!r} (choose from {', '.join(STYLES)})")
    if width is not None:
        _check_width(width)
    _check_ambiguous_width(ambiguous_width)
    aw = ambiguous_width

    body = [[_cell(c) for c in row] for row in rows]
    head = None if headers is None else [_cell(c) for c in headers]
    ncols = max([len(r) for r in body] + [len(head) if head else 0])
    if ncols == 0:
        return ""
    for r in body:
        r.extend([""] * (ncols - len(r)))
    if head is not None:
        head.extend([""] * (ncols - len(head)))
    elif style == "markdown":
        head = [""] * ncols  # a pipe table always needs a header row

    aligns = [_check_align(a) for a in _per_column("align", align, ncols, "left")]
    limits = _per_column("max_col_width", max_col_width, ncols, None)
    for lim in limits:
        if lim is not None and (not isinstance(lim, int) or lim < 1):
            raise ValueError(f"invalid max_col_width {lim!r} (must be an int > 0)")

    all_rows = ([head] if head is not None else []) + body

    # 1. natural column widths, capped by max_col_width
    def natural(i: int) -> int:
        return max(
            _w(line, aw) for r in all_rows for line in r[i].splitlines() or [""]
        )

    cols = [natural(i) for i in range(ncols)]
    cols = [c if lim is None else min(c, lim) for c, lim in zip(cols, limits)]

    # 2. shrink to the total width budget, widest column first
    if style in ("simple", "plain"):
        overhead = 2 * (ncols - 1)
    else:
        overhead = 3 * (ncols - 1) + 4
    if width is not None:
        while sum(cols) + overhead > width:
            i = max(range(ncols), key=lambda k: cols[k])
            if cols[i] <= _MIN_SHRINK:
                break
            cols[i] -= 1

    # 3. wrap cells, then use the actual widths (wrapping may leave slack)
    cells = [
        [_cell_lines(r[i], cols[i], aw, wrap_kwargs) for i in range(ncols)]
        for r in all_rows
    ]
    if style == "markdown":
        cells = [[["<br>".join(_md_escape(l) for l in c)] for c in r] for r in cells]
    cols = [
        max(_w(line, aw) for r in cells for line in r[i]) for i in range(ncols)
    ]
    if style == "markdown":
        cols = [max(3, c) for c in cols]

    box = _ASCII if aw == 2 else _BOX

    def render(row: List[List[str]]) -> List[str]:
        height = max(len(c) for c in row)
        out = []
        for k in range(height):
            parts = [
                pad(c[k] if k < len(c) else "", cols[i], aligns[i], ambiguous_width=aw)
                for i, c in enumerate(row)
            ]
            if style in ("simple", "plain"):
                out.append("  ".join(parts))
            elif style == "markdown":
                out.append("| " + " | ".join(parts) + " |")
            else:
                v = box["v"]
                out.append(f"{v} " + f" {v} ".join(parts) + f" {v}")
        return out

    lines: List[str] = []
    head_cells, body_cells = (cells[0], cells[1:]) if head is not None else (None, cells)

    if style in ("simple", "plain"):
        if head_cells is not None:
            lines += render(head_cells)
            if style == "simple":
                lines.append("  ".join("-" * c for c in cols))
        for r in body_cells:
            lines += render(r)
    elif style == "markdown":
        lines += render(head_cells)
        marks = {
            "left": lambda n: ":" + "-" * (n - 1),
            "right": lambda n: "-" * (n - 1) + ":",
            "center": lambda n: ":" + "-" * (n - 2) + ":",
        }
        lines.append("| " + " | ".join(marks[a](c) for a, c in zip(aligns, cols)) + " |")
        for r in body_cells:
            lines += render(r)
    else:  # grid
        def rule(kind: str) -> str:
            left, fill, cross, right = box[kind]
            return left + cross.join(fill * (c + 2) for c in cols) + right

        lines.append(rule("top"))
        groups = ([head_cells] if head_cells is not None else []) + body_cells
        for n, r in enumerate(groups):
            if n:
                lines.append(rule("mid"))
            lines += render(r)
        lines.append(rule("bottom"))
    return "\n".join(lines)
