"""縦書き (tategaki): vertical text layout for terminals.

Each column holds ``height`` cells, every cell is two display columns wide,
and columns are laid out right to left.  Output is a string of rows, top to
bottom, all with the same display width.
"""

from __future__ import annotations

import re
import unicodedata
from typing import List, Optional, Tuple

from ._core import (
    HANGABLE,
    NO_END,
    NO_START,
    _check_width,
    _cluster_width,
    _clusters_plain,
    strip_ansi,
)

__all__ = ["tategaki", "VERTICAL_FORMS"]

_FULL_SPACE = "　"

# Horizontal form -> vertical presentation form (every target verified with
# unicodedata.name).  ー (KATAKANA-HIRAGANA PROLONGED SOUND MARK) becomes
# U+FF5C FULLWIDTH VERTICAL LINE, which renders centred in most terminal fonts.
# ～ / 〜 have no vertical presentation form; U+2240 WREATH PRODUCT is used as
# the customary substitute (it is narrow, so the cell is padded with a space).
VERTICAL_FORMS = {
    "ー": "｜",  # FULLWIDTH VERTICAL LINE
    "—": "︱",  # PRESENTATION FORM FOR VERTICAL EM DASH
    "―": "︱",
    "「": "﹁", "」": "﹂",
    "『": "﹃", "』": "﹄",
    "（": "︵", "）": "︶",
    "【": "︻", "】": "︼",
    "〔": "︹", "〕": "︺",
    "《": "︽", "》": "︾",
    "〈": "︿", "〉": "﹀",
    "｛": "︷", "｝": "︸",
    "［": "﹇", "］": "﹈",
    "、": "︑", "。": "︒", "，": "︐",
    "：": "︓", "；": "︔",
    "！": "︕", "？": "︖",
    "…": "︙", "‥": "︰",
    "～": "≀", "〜": "≀",  # WREATH PRODUCT
}

_HALFWIDTH_MODES = ("fullwidth", "pair")

# A cell: (first original char, last original char, display string).
_Cell = Tuple[str, str, str]


def _is_ascii(ch: str) -> bool:
    return 0x20 <= ord(ch) <= 0x7E


def _to_fullwidth(ch: str) -> str:
    if ch == " ":
        return _FULL_SPACE
    return chr(ord(ch) + 0xFEE0)


def _fit(s: str) -> str:
    """Pad ``s`` (one grapheme cluster) to exactly two display columns."""
    w = _cluster_width(s, 1)
    return s + " " * (2 - w) if w < 2 else s


_HW_KANA_RE = re.compile("[\uff66-\uff9d][\uff9e\uff9f]?|[\uff61-\uff65\uff9e\uff9f]")


def _hw_kana(cl: str) -> str:
    """Full-width form of a half-width katakana cluster (ｶﾞ -> ガ)."""
    fw = unicodedata.normalize("NFKC", cl)
    return unicodedata.normalize("NFC", fw)


def _cells(line: str, halfwidth: str) -> List[_Cell]:
    cells: List[_Cell] = []
    if halfwidth == "fullwidth" and _HW_KANA_RE.search(line):
        # Half-width katakana (with its sound mark) becomes one full-width
        # cluster; mark the result so the original chars stay available for
        # the kinsoku checks.
        clusters: List[Tuple[str, str]] = []
        pos = 0
        for m in _HW_KANA_RE.finditer(line):
            clusters.extend((cl, cl) for cl in _clusters_plain(line[pos:m.start()]))
            clusters.append((m.group(), _hw_kana(m.group())))
            pos = m.end()
        clusters.extend((cl, cl) for cl in _clusters_plain(line[pos:]))
    else:
        clusters = [(cl, cl) for cl in _clusters_plain(line)]
    i, n = 0, len(clusters)
    while i < n:
        orig, cl = clusters[i]
        i += 1
        ch = cl[0]
        if cl == "\t":
            cl = ch = " " if halfwidth == "fullwidth" else _FULL_SPACE
        cp = ord(ch)
        if cp < 0x20 or 0x7F <= cp < 0xA0:  # other control characters
            # A zero-width char after a control char would be its cluster.
            rest = cl[1:]
            if not rest:
                continue
            orig, cl, ch = orig[1:], rest, rest[0]
        w = _cluster_width(cl, 1)
        if len(cl) > 1 and w == 2:
            # Emoji sequence, flag, keycap, NFD Hangul: one cell as is.
            cells.append((orig[0], orig[-1], _fit(cl)))
            continue
        if w == 0:
            # Zero-width chars with nothing before them.
            cells.append((orig[0], orig[-1], _fit(" " + cl)))
            continue
        marks = cl[1:]  # combining marks on the base char
        if _is_ascii(ch):
            if halfwidth == "pair":
                if (not marks and i < n and len(clusters[i][1]) == 1
                        and _is_ascii(clusters[i][1])):
                    s = ch + clusters[i][1]
                    cells.append((s[0], s[1], s))
                    i += 1
                    continue
                cells.append((orig[0], orig[-1], _fit(cl)))
                continue
            fw = _to_fullwidth(ch)
            cells.append((orig[0], orig[-1], _fit(VERTICAL_FORMS.get(fw, fw) + marks)))
            continue
        cells.append((orig[0], orig[-1], _fit(VERTICAL_FORMS.get(ch, ch) + marks)))
    return cells


def _layout(cells: List[_Cell], height: int, hanging: bool) -> List[List[_Cell]]:
    columns: List[List[_Cell]] = []
    cur: List[_Cell] = []
    for c in cells:
        if len(cur) < height:
            cur.append(c)
            continue
        if hanging and len(cur) == height and c[0] in HANGABLE:
            cur.append(c)  # ぶら下げ: occupies row height+1
            continue
        # Find the latest break position j (cur[:j] stays, cur[j:] + [c]
        # moves to the next column) that satisfies both kinsoku rules.
        split: Optional[int] = None
        for j in range(len(cur), 0, -1):
            moved = len(cur) - j + 1
            if moved > height:
                break
            head = cur[j][0] if j < len(cur) else c[0]
            if head in NO_START or cur[j - 1][1] in NO_END:
                continue
            split = j
            break
        if split is None:  # impossible to satisfy: best effort
            split = len(cur)
        columns.append(cur[:split])
        cur = cur[split:] + [c]
    columns.append(cur)
    return columns


def tategaki(
    text: str,
    height: int,
    *,
    gap: int = 1,
    hanging: bool = True,
    halfwidth: str = "fullwidth",
) -> str:
    """Lay out ``text`` vertically (縦書き) for display in a terminal.

    Columns of ``height`` cells (2 display columns each) flow from right to
    left, separated by ``gap`` half-width spaces.  Every newline in ``text``
    starts a new column.  Empty cells are filled with U+3000 so that every
    output row has the same display width.

    - Brackets, punctuation, ``ー`` etc. are replaced by their vertical
      presentation forms (see :data:`VERTICAL_FORMS`).
    - Each grapheme cluster takes one cell: emoji sequences (ZWJ, flags,
      skin tones, keycaps) and decomposed (NFD) Hangul syllables are never
      split across cells.
    - ``halfwidth="fullwidth"``: printable ASCII and half-width katakana
      (with its sound mark, ``ｶﾞ`` -> ``ガ``) are converted to full-width,
      one char per cell.  ``halfwidth="pair"``: up to two consecutive ASCII
      chars share one cell (縦中横, e.g. ``"12"``).
    - Kinsoku (judged on the original chars): NO_START chars never start a
      column and NO_END chars never end one, by pushing chars to the next
      column (追い出し).  With ``hanging=True``, ``、。，．,.`` may instead
      hang in an extra row below the column; if any char hangs, every column
      gets ``height + 1`` rows.
    - Zero-width / combining chars stay with the char they combine with; ANSI escape
      sequences are removed.
    """
    _check_width(height, "height")
    _check_width(gap, "gap", allow_zero=True)
    if halfwidth not in _HALFWIDTH_MODES:
        raise ValueError(f"halfwidth must be one of {_HALFWIDTH_MODES!r}, not {halfwidth!r}")
    text = strip_ansi(text)
    lines = text.splitlines()
    if not lines:
        return ""
    columns: List[List[_Cell]] = []
    for line in lines:
        columns.extend(_layout(_cells(line, halfwidth), height, hanging))
    # A hanging char makes its column height + 1 long; pad all to match.
    rows = max(height, max(len(col) for col in columns))
    sep = " " * gap
    out = []
    for r in range(rows):
        out.append(sep.join(col[r][2] if r < len(col) else _FULL_SPACE
                            for col in reversed(columns)))
    return "\n".join(out)
