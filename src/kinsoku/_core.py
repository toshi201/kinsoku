"""Core implementation: display width, tokenizing, kinsoku-aware wrapping."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Iterator, List

# 行頭禁則: characters that must not start a line.
NO_START = frozenset(
    "、。，．,.!?！？‼⁇⁈⁉)）]］}｝〕〉》」』】〙〗〟’”｠»"
    "ゝゞーァィゥェォッャュョヮヵヶぁぃぅぇぉっゃゅょゎゕゖ"
    "ㇰㇱㇲㇳㇴㇵㇶㇷㇸㇹㇺㇻㇼㇽㇾㇿ"
    "…‥・：；:;゛゜ヽヾ々〻‐゠–〜～%％"
)

# 行末禁則: characters that must not end a line.
NO_END = frozenset("(（[［{｛〔〈《「『【〘〖〝‘“｟«")

# ぶら下げ可能: punctuation allowed to hang past the right margin.
HANGABLE = frozenset("、。，．,.")

_SPACES = frozenset(" \t　")


def char_width(ch: str, ambiguous_width: int = 1) -> int:
    """Return the terminal display width (0, 1 or 2) of a single character."""
    if not ch:
        return 0
    cp = ord(ch)
    # Control characters, zero-width joiners, variation selectors, etc.
    if cp < 0x20 or 0x7F <= cp < 0xA0:
        return 0
    if cp in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF) or 0xFE00 <= cp <= 0xFE0F:
        return 0
    if 0xE0100 <= cp <= 0xE01EF:  # variation selectors supplement
        return 0
    cat = unicodedata.category(ch)
    if cat in ("Mn", "Me", "Cf"):
        return 0
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ("W", "F"):
        return 2
    if eaw == "A":
        return ambiguous_width
    return 1


def width(text: str, ambiguous_width: int = 1) -> int:
    """Return the display width of ``text`` in terminal columns."""
    return sum(char_width(c, ambiguous_width) for c in text)


def _clusters(text: str) -> Iterator[str]:
    """Yield rough grapheme clusters: a base char plus trailing zero-width chars."""
    buf = ""
    joiner = False
    for ch in text:
        zero = char_width(ch) == 0 and ch not in "\t"
        if buf and (zero or joiner):
            buf += ch
        else:
            if buf:
                yield buf
            buf = ch
        joiner = ch == "‍"
    if buf:
        yield buf


def _is_wide_cluster(cl: str, ambiguous_width: int) -> bool:
    return char_width(cl[0], ambiguous_width) >= 2


@dataclass
class _Unit:
    text: str
    width: int
    space: bool = False
    hang: int = 0  # width of trailing hangable punctuation


def _atoms(text: str, ambiguous_width: int) -> List[_Unit]:
    """Split text into atoms: spaces, latin word runs, single wide clusters."""
    atoms: List[_Unit] = []
    word = ""
    for cl in _clusters(text):
        if cl[0] in _SPACES:
            if word:
                atoms.append(_Unit(word, width(word, ambiguous_width)))
                word = ""
            atoms.append(_Unit(cl, width(cl, ambiguous_width) or 1, space=True))
        elif _is_wide_cluster(cl, ambiguous_width) or cl[0] in NO_START or cl[0] in NO_END:
            if word:
                atoms.append(_Unit(word, width(word, ambiguous_width)))
                word = ""
            atoms.append(_Unit(cl, width(cl, ambiguous_width)))
        else:
            word += cl
    if word:
        atoms.append(_Unit(word, width(word, ambiguous_width)))
    return atoms


def _glue(atoms: List[_Unit], hanging: bool, ambiguous_width: int) -> List[_Unit]:
    """Merge atoms that must not be separated according to kinsoku rules."""
    units: List[_Unit] = []
    for a in atoms:
        if units and not a.space and not units[-1].space:
            prev = units[-1]
            if a.text[0] in NO_START or prev.text[-1] in NO_END:
                prev.text += a.text
                prev.width += a.width
                continue
        units.append(_Unit(a.text, a.width, a.space))
    if hanging:
        for u in units:
            if u.space:
                continue
            h = 0
            for ch in reversed(u.text):
                if ch in HANGABLE:
                    h += char_width(ch, ambiguous_width)
                else:
                    break
            # never let the whole unit hang
            u.hang = h if h < u.width else 0
    return units


def _split_long(u: _Unit, limit: int, ambiguous_width: int) -> List[_Unit]:
    """Hard-split an over-long unit into chunks no wider than ``limit``."""
    cls = list(_clusters(u.text))
    ws = [width(c, ambiguous_width) for c in cls]

    def good_break(i: int) -> bool:
        # breaking before cls[i] respects kinsoku
        return cls[i][0] not in NO_START and cls[i - 1][-1] not in NO_END

    chunks: List[_Unit] = []
    start = 0
    n = len(cls)
    while start < n:
        end, bw = start, 0
        while end < n and (end == start or bw + ws[end] <= limit):
            bw += ws[end]
            end += 1
        if end < n:
            # back off to the latest kinsoku-safe break inside this chunk
            for j in range(end, start, -1):
                if good_break(j):
                    end = j
                    break
        chunks.append(_Unit("".join(cls[start:end]), sum(ws[start:end])))
        start = end
    return chunks


def _wrap_line(
    line: str,
    width_: int,
    hanging: bool,
    break_long_words: bool,
    ambiguous_width: int,
) -> List[str]:
    units = _glue(_atoms(line, ambiguous_width), hanging, ambiguous_width)
    lines: List[str] = []
    cur: List[_Unit] = []
    cur_w = 0

    def flush() -> None:
        nonlocal cur, cur_w
        while cur and cur[-1].space:
            cur.pop()
        lines.append("".join(u.text for u in cur))
        cur, cur_w = [], 0

    for u in units:
        if u.space:
            if cur:
                cur.append(u)
                cur_w += u.width
            continue
        if cur_w + u.width - u.hang <= width_:
            cur.append(u)
            cur_w += u.width
            continue
        if cur:
            flush()
        if u.width - u.hang > width_ and break_long_words:
            pieces = _split_long(u, width_, ambiguous_width)
            for p in pieces[:-1]:
                lines.append(p.text)
            u = pieces[-1]
        cur = [u]
        cur_w = u.width
    if cur or not lines:
        flush()
    return lines


def wrap(
    text: str,
    width: int = 70,
    *,
    hanging: bool = False,
    break_long_words: bool = True,
    ambiguous_width: int = 1,
) -> List[str]:
    """Wrap ``text`` so every line fits in ``width`` terminal columns.

    Existing newlines are kept as hard line breaks. Kinsoku shori (Japanese
    line-breaking rules) is applied: closing brackets and punctuation never
    start a line, and opening brackets never end one.

    :param hanging: allow ``、。,.`` to hang past the margin (ぶら下げ).
    :param break_long_words: hard-split units wider than ``width``.
    :param ambiguous_width: width of East Asian Ambiguous characters (1 or 2).
    """
    if width < 1:
        raise ValueError(f"invalid width {width!r} (must be > 0)")
    if ambiguous_width not in (1, 2):
        raise ValueError("ambiguous_width must be 1 or 2")
    out: List[str] = []
    for line in text.splitlines() or [""]:
        out.extend(_wrap_line(line, width, hanging, break_long_words, ambiguous_width))
    return out


def fill(text: str, width: int = 70, **kwargs) -> str:
    """Like :func:`wrap` but return a single string joined by newlines."""
    return "\n".join(wrap(text, width, **kwargs))


def truncate(
    text: str,
    width: int,
    placeholder: str = "…",
    *,
    ambiguous_width: int = 1,
) -> str:
    """Cut ``text`` to fit in ``width`` columns, appending ``placeholder``."""
    if _w(text, ambiguous_width) <= width:
        return text
    pw = _w(placeholder, ambiguous_width)
    if pw > width:
        raise ValueError("placeholder is wider than width")
    buf, bw = "", 0
    for cl in _clusters(text):
        cw = _w(cl, ambiguous_width)
        if bw + cw > width - pw:
            break
        buf += cl
        bw += cw
    return buf + placeholder


def pad(
    text: str,
    width: int,
    align: str = "left",
    fillchar: str = " ",
    *,
    ambiguous_width: int = 1,
) -> str:
    """Pad ``text`` to ``width`` columns. ``align`` is left, right or center."""
    if _w(fillchar, ambiguous_width) != 1:
        raise ValueError("fillchar must have display width 1")
    gap = width - _w(text, ambiguous_width)
    if gap <= 0:
        return text
    if align == "left":
        return text + fillchar * gap
    if align == "right":
        return fillchar * gap + text
    if align == "center":
        left = gap // 2
        return fillchar * left + text + fillchar * (gap - left)
    raise ValueError(f"unknown align {align!r}")


_w = width
