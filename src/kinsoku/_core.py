"""Core implementation: display width, tokenizing, kinsoku-aware wrapping."""

from __future__ import annotations

import re
import unicodedata
import dataclasses
from dataclasses import dataclass
from functools import lru_cache
from itertools import repeat
from types import MappingProxyType
from typing import FrozenSet, Iterable, Iterator, List, Mapping, Optional, Union

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


@dataclass(frozen=True)
class KinsokuRules:
    """A set of line-breaking (kinsoku) rules.

    :param no_start: characters that must not start a line (行頭禁則).
    :param no_end: characters that must not end a line (行末禁則).
    :param hangable: punctuation allowed to hang past the margin with
        ``hanging=True`` (ぶら下げ).

    Any iterable of characters (including a plain ``str``) is accepted and
    converted to a ``frozenset``. To customize a preset, use
    :meth:`preset` + :meth:`replace` (equivalent to
    :func:`dataclasses.replace`)::

        rules = KinsokuRules.preset("ja")
        rules = rules.replace(no_start=rules.no_start - {"ー"})
    """

    no_start: FrozenSet[str] = frozenset()
    no_end: FrozenSet[str] = frozenset()
    hangable: FrozenSet[str] = frozenset()

    def __post_init__(self) -> None:
        for name in ("no_start", "no_end", "hangable"):
            value = getattr(self, name)
            if isinstance(value, str) or not isinstance(value, frozenset):
                object.__setattr__(self, name, frozenset(value))

    @classmethod
    def preset(cls, name: str) -> "KinsokuRules":
        """Return the built-in preset called ``name`` (see :data:`PRESETS`)."""
        try:
            return PRESETS[name]
        except (KeyError, TypeError):
            valid = ", ".join(PRESETS)
            raise ValueError(
                f"unknown rules preset {name!r} (valid: {valid})"
            ) from None

    def replace(self, **changes: Iterable[str]) -> "KinsokuRules":
        """Return a copy with some fields replaced (like :func:`dataclasses.replace`)."""
        return dataclasses.replace(self, **changes)


_SMALL_KANA = (
    "ァィゥェォッャュョヮヵヶぁぃぅぇぉっゃゅょゎゕゖ"
    "ㇰㇱㇲㇳㇴㇵㇶㇷㇸㇹㇺㇻㇼㇽㇾㇿ"
)
# Characters that CSS ``line-break: loose`` lets start a line: small kana,
# the prolonged sound mark, iteration marks and hyphen-like characters.
_LOOSE_ALLOWED = frozenset(_SMALL_KANA + "ー々〻ゝゞヽヾ‐゠–〜～")

_ZH_NO_START = (
    "，。、．！？；：…‥·・"
    "”’」』）》〉】〗〕］｝〙〛｠"
    ",.!?;:)]}%％"
)
_ZH_NO_END = "“‘「『（《〈【〖〔［｛〘〚｟([{"
_ZH_HANGABLE = "，。、．,."

PRESETS: Mapping[str, KinsokuRules] = MappingProxyType({
    # Japanese (default): exactly NO_START / NO_END / HANGABLE.
    "ja": KinsokuRules(NO_START, NO_END, HANGABLE),
    # JIS X 4051-like: small kana, ー and iteration marks never start a line
    # (the "ja" rules already follow this).
    "strict": KinsokuRules(NO_START, NO_END, HANGABLE),
    # CSS ``line-break: loose``-like: small kana, ー, 々 etc. may start a line.
    "loose": KinsokuRules(NO_START - _LOOSE_ALLOWED, NO_END, HANGABLE),
    # Simplified Chinese.
    "zh-hans": KinsokuRules(_ZH_NO_START, _ZH_NO_END, _ZH_HANGABLE),
    # Traditional Chinese: plus the small form variants (﹐﹑﹒ ...).
    "zh-hant": KinsokuRules(
        _ZH_NO_START + "﹐﹑﹒﹔﹕﹖﹗﹚﹜﹞",
        _ZH_NO_END + "﹙﹛﹝",
        _ZH_HANGABLE + "﹐﹑﹒",
    ),
    # Korean: closing punctuation/brackets (Western and CJK); no kana rules.
    "ko": KinsokuRules(
        ".,!?;:)]}…%’”」』）》〉】〕］｝〙〗。、，．！？；：％",
        "([{‘“「『（《〈【〔［｛〘〖",
        ".,，．。、",
    ),
})

_JA = PRESETS["ja"]

RulesLike = Union[str, KinsokuRules]


def _resolve_rules(rules: RulesLike) -> KinsokuRules:
    if isinstance(rules, KinsokuRules):
        return rules
    if isinstance(rules, str):
        return KinsokuRules.preset(rules)
    raise TypeError(
        f"rules must be a preset name or KinsokuRules, not {type(rules).__name__}"
    )

_SPACES = frozenset(" \t　")

# ANSI escape sequences: CSI (colors, cursor), OSC (hyperlinks, titles), 2-byte ESC.
_ANSI_RE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\x1b[@-Z\\-_]"
)


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences (colors, hyperlinks, ...) from ``text``."""
    return _ANSI_RE.sub("", text)


# --- ANSI state tracking (ansi_reflow) ---------------------------------------

_SGR_RE = re.compile(r"\x1b\[([0-9:;]*)m")
_OSC8_RE = re.compile(r"\x1b\]8;([^;\x07\x1b]*);([^\x07\x1b]*)(\x07|\x1b\\)")

# simple on/off attributes: slot -> (codes that set it, codes that clear it)
_ATTR_ON = {1: "bold", 2: "dim", 3: "italic", 4: "underline", 21: "underline",
            5: "blink", 6: "blink", 7: "inverse", 8: "hidden", 9: "strike",
            53: "overline"}
_ATTR_OFF = {22: ("bold", "dim"), 23: ("italic",), 24: ("underline",),
             25: ("blink",), 27: ("inverse",), 28: ("hidden",),
             29: ("strike",), 55: ("overline",)}
_SLOTS = ("bold", "dim", "italic", "underline", "blink", "inverse", "hidden",
          "strike", "overline", "fg", "bg", "ulcolor")
_COLOR_SLOT = {38: "fg", 48: "bg", 58: "ulcolor"}


class _AnsiState:
    """Tracks the SGR attributes and the OSC 8 hyperlink active in a stream."""

    def __init__(self) -> None:
        self.sgr: dict = {}
        self.link: Optional[tuple] = None  # (params, uri, terminator)

    def feed(self, seq: str) -> None:
        """Update the state with one escape sequence (others are ignored)."""
        m = _SGR_RE.fullmatch(seq)
        if m:
            self._sgr(m.group(1))
            return
        m = _OSC8_RE.fullmatch(seq)
        if m:
            params, uri, term = m.groups()
            self.link = (params, uri, term) if uri else None

    def feed_text(self, text: str) -> None:
        if "\x1b" in text:
            for m in _ANSI_RE.finditer(text):
                self.feed(m.group())

    def _sgr(self, body: str) -> None:
        ps = body.split(";")
        st = self.sgr
        i = 0
        while i < len(ps):
            p = ps[i]
            i += 1
            if ":" in p:  # colon sub-parameters, e.g. 38:2::r:g:b or 4:3
                head = p.split(":", 1)[0]
                h = int(head) if head.isdigit() else -1
                if h in _COLOR_SLOT:
                    st[_COLOR_SLOT[h]] = p
                elif h == 4:
                    if p.split(":")[1] in ("", "0"):
                        st.pop("underline", None)
                    else:
                        st["underline"] = p
                continue
            c = int(p) if p else 0
            if c == 0:
                st.clear()
            elif c in _ATTR_ON:
                st[_ATTR_ON[c]] = str(c)
            elif c in _ATTR_OFF:
                for slot in _ATTR_OFF[c]:
                    st.pop(slot, None)
            elif 30 <= c <= 37 or 90 <= c <= 97:
                st["fg"] = str(c)
            elif 40 <= c <= 47 or 100 <= c <= 107:
                st["bg"] = str(c)
            elif c in (39, 49, 59):
                st.pop({39: "fg", 49: "bg", 59: "ulcolor"}[c], None)
            elif c in _COLOR_SLOT:
                mode = ps[i] if i < len(ps) else ""
                n = 2 if mode == "5" else 4 if mode == "2" else 0
                if n == 0 or i + n > len(ps):
                    return  # malformed: ignore the rest of the sequence
                st[_COLOR_SLOT[c]] = ";".join([str(c)] + ps[i:i + n])
                i += n

    def active(self) -> bool:
        return bool(self.sgr) or self.link is not None

    def open(self) -> str:
        """Minimal sequence that re-establishes this state from the default."""
        out = ""
        if self.sgr:
            out = "\x1b[" + ";".join(self.sgr[k] for k in _SLOTS if k in self.sgr) + "m"
        if self.link:
            params, uri, term = self.link
            out += f"\x1b]8;{params};{uri}{term}"
        return out

    def close(self) -> str:
        """Sequence that returns the terminal to the default state."""
        out = ""
        if self.link:
            out += f"\x1b]8;;{self.link[2]}"
        if self.sgr:
            out += "\x1b[0m"
        return out

    def copy(self) -> "_AnsiState":
        c = _AnsiState()
        c.sgr = dict(self.sgr)
        c.link = self.link
        return c


def _reflow_body(body: str, state: _AnsiState) -> str:
    """Re-open ``state`` before ``body``, update it, close it at the end."""
    if not body:
        return body
    prefix = state.open()
    state.feed_text(body)
    return prefix + body + state.close()


def ansi_reflow(lines: List[str]) -> List[str]:
    """Make each line self-contained with respect to ANSI styling.

    Lines that end with active SGR attributes (colors, bold, ...) or an open
    OSC 8 hyperlink get them closed at the end, and the next line re-opens
    the same state at its start. Lines without active styling are unchanged.
    """
    state = _AnsiState()
    return [_reflow_body(line, state) for line in lines]


def char_width(ch: str, ambiguous_width: int = 1) -> int:
    """Return the terminal display width (0, 1 or 2) of a single character."""
    if not ch:
        return 0
    if " " <= ch <= "~" and len(ch) == 1:  # printable ASCII fast path
        return 1
    return _char_width(ch, ambiguous_width)


@lru_cache(maxsize=8192)
def _char_width(ch: str, ambiguous_width: int) -> int:
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
    """Return the display width of ``text`` in terminal columns.

    ANSI escape sequences are ignored.
    """
    if "\x1b" in text:
        text = strip_ansi(text)
    if text.isascii() and text.isprintable():
        return len(text)
    return sum(map(_char_width, text, repeat(ambiguous_width)))


def _clusters(text: str) -> Iterator[str]:
    """Yield rough grapheme clusters: a base char plus trailing zero-width chars.

    ANSI escape sequences are kept intact and attached to a neighbouring
    cluster, so they are never split and never counted.
    """
    if "\x1b" not in text:
        yield from _clusters_plain(text)
        return
    buf = ""
    prefix = ""  # escapes seen before any base char of the next cluster
    joiner = False
    pos = 0
    n = len(text)
    while pos < n:
        ch = text[pos]
        if ch == "\x1b":
            m = _ANSI_RE.match(text, pos)
            if m:
                if buf:
                    buf += m.group()
                else:
                    prefix += m.group()
                pos = m.end()
                continue
        pos += 1
        zero = char_width(ch) == 0 and ch != "\t"
        if buf and (zero or joiner):
            buf += ch
        else:
            if buf:
                yield buf
            buf = prefix + ch
            prefix = ""
        joiner = ch == "\u200d"
    if buf or prefix:
        yield buf + prefix


def _clusters_plain(text: str) -> Iterator[str]:
    """:func:`_clusters` for text without escape sequences."""
    if text.isascii() and text.isprintable():
        yield from text
        return
    cw = _char_width
    buf = ""
    joiner = False
    for ch in text:
        if buf and (joiner or (cw(ch, 1) == 0 and ch != "\t")):
            buf += ch
        else:
            if buf:
                yield buf
            buf = ch
        joiner = ch == "‍"
    if buf:
        yield buf


def _base(cl: str) -> str:
    """First visible character of a cluster ("" for a pure escape cluster)."""
    if cl[:1] == "\x1b":
        cl = strip_ansi(cl)
    return cl[:1]


def _is_wide_cluster(cl: str, ambiguous_width: int) -> bool:
    b = _base(cl)
    return bool(b) and char_width(b, ambiguous_width) >= 2


def _first(text: str) -> str:
    return _base(text)


def _last(text: str) -> str:
    if "\x1b" in text:
        text = strip_ansi(text)
    return text[-1:]


@dataclass(slots=True)
class _Unit:
    text: str
    width: int
    space: bool = False
    hang: int = 0  # width of trailing hangable punctuation


def _atoms(
    text: str,
    ambiguous_width: int,
    keep_all: bool = False,
    rules: KinsokuRules = _JA,
) -> List[_Unit]:
    """Split text into atoms: spaces, word runs, single wide clusters."""
    atoms: List[_Unit] = []
    word: List[str] = []  # clusters of the current word run
    word_w = 0
    append = atoms.append
    cw = _char_width
    no_start = rules.no_start
    no_end = rules.no_end

    for cl in _clusters(text):
        # The width of a word run is the sum of its cluster widths, so each
        # cluster is measured exactly once.
        if len(cl) == 1:  # the common case: a lone character, no escapes
            b = cl
            w = bw = cw(cl, ambiguous_width)
        else:
            b = _base(cl)
            w = width(cl, ambiguous_width)
            bw = char_width(b, ambiguous_width) if b else 0
        if b and b in _SPACES:
            if word:
                append(_Unit("".join(word), word_w))
                word, word_w = [], 0
            append(_Unit(cl, w or 1, space=True))
        elif b and not keep_all and (bw >= 2 or b in no_start or b in no_end):
            if word:
                append(_Unit("".join(word), word_w))
                word, word_w = [], 0
            append(_Unit(cl, w))
        else:
            word.append(cl)
            word_w += w
    if word:
        append(_Unit("".join(word), word_w))
    return atoms


def _glue(
    atoms: List[_Unit],
    hanging: bool,
    ambiguous_width: int,
    rules: KinsokuRules = _JA,
) -> List[_Unit]:
    """Merge atoms that must not be separated according to kinsoku rules."""
    units: List[_Unit] = []
    no_start = rules.no_start
    no_end = rules.no_end
    for a in atoms:
        if units and not a.space and not units[-1].space:
            prev = units[-1]
            if _first(a.text) in no_start or _last(prev.text) in no_end:
                prev.text += a.text
                prev.width += a.width
                continue
        units.append(_Unit(a.text, a.width, a.space))
    if hanging:
        for u in units:
            if u.space:
                continue
            h = 0
            for ch in reversed(strip_ansi(u.text)):
                if ch in rules.hangable:
                    h += char_width(ch, ambiguous_width)
                else:
                    break
            # never let the whole unit hang
            u.hang = h if h < u.width else 0
    return units


def _split_long(
    u: _Unit, limit: int, ambiguous_width: int, rules: KinsokuRules = _JA
) -> List[_Unit]:
    """Hard-split an over-long unit into chunks no wider than ``limit``."""
    cls = list(_clusters(u.text))
    ws = [width(c, ambiguous_width) for c in cls]

    def good_break(i: int) -> bool:
        # breaking before cls[i] respects kinsoku
        return (
            _first(cls[i]) not in rules.no_start
            and _last(cls[i - 1]) not in rules.no_end
        )

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
    first_width: int,
    rest_width: int,
    hanging: bool,
    break_long_words: bool,
    keep_all: bool,
    ambiguous_width: int,
    rules: KinsokuRules = _JA,
    keep_escapes: bool = False,
) -> List[str]:
    units = _glue(
        _atoms(line, ambiguous_width, keep_all, rules), hanging, ambiguous_width, rules
    )
    lines: List[str] = []
    cur: List[_Unit] = []
    cur_w = 0
    pending = ""  # escapes of dropped leading spaces (keep_escapes only)

    def limit() -> int:
        return rest_width if lines else first_width

    def escapes(t: str) -> str:
        return "".join(_ANSI_RE.findall(t)) if keep_escapes and "\x1b" in t else ""

    def flush() -> None:
        nonlocal cur, cur_w
        dropped = ""
        while cur and cur[-1].space:
            dropped = escapes(cur.pop().text) + dropped
        lines.append("".join(u.text for u in cur) + dropped)
        cur, cur_w = [], 0

    for u in units:
        if u.space:
            if cur:
                cur.append(u)
                cur_w += u.width
            else:
                pending += escapes(u.text)
            continue
        if pending:
            u = _Unit(pending + u.text, u.width, hang=u.hang)
            pending = ""
        if cur_w + u.width - u.hang <= limit():
            cur.append(u)
            cur_w += u.width
            continue
        if cur:
            flush()
        if break_long_words:
            while u.width - u.hang > limit():
                pieces = _split_long(u, limit(), ambiguous_width, rules)
                if len(pieces) < 2:
                    break
                lines.append(pieces[0].text)
                u = _Unit(
                    "".join(x.text for x in pieces[1:]),
                    sum(x.width for x in pieces[1:]),
                    hang=u.hang,
                )
        cur = [u]
        cur_w = u.width
    if cur or not lines:
        flush()
    if pending:
        lines[-1] += pending
    return lines


def wrap(
    text: str,
    width: int = 70,
    *,
    initial_indent: str = "",
    subsequent_indent: str = "",
    hanging: bool = False,
    break_long_words: bool = True,
    keep_all: bool = False,
    max_lines: Optional[int] = None,
    placeholder: str = "…",
    ambiguous_width: int = 1,
    rules: RulesLike = "ja",
    ansi_reflow: bool = False,
) -> List[str]:
    """Wrap ``text`` so every line fits in ``width`` terminal columns.

    Existing newlines are kept as hard line breaks (each input line is a
    paragraph). Kinsoku shori (Japanese line-breaking rules) is applied:
    closing brackets and punctuation never start a line, and opening
    brackets never end one. ANSI escape sequences are preserved and take no
    width.

    :param initial_indent: prepended to the first line of every paragraph
        (e.g. ``"\u3000"`` for Japanese paragraph indentation).
    :param subsequent_indent: prepended to the other lines.
    :param hanging: allow ``、。,.`` to hang past the margin (ぶら下げ).
    :param break_long_words: hard-split units wider than ``width``.
    :param keep_all: only break at spaces, like CSS ``word-break: keep-all``
        (natural for Korean).
    :param max_lines: keep at most this many lines; if text is cut, the last
        line ends with ``placeholder``.
    :param ambiguous_width: width of East Asian Ambiguous characters (1 or 2).
    :param rules: kinsoku rules: a preset name (``"ja"`` (default),
        ``"strict"``, ``"loose"``, ``"zh-hans"``, ``"zh-hant"``, ``"ko"``)
        or a :class:`KinsokuRules` instance.
    :param ansi_reflow: close active ANSI styling (SGR colors/attributes and
        OSC 8 links) at the end of each line and re-open it at the start of
        the next one, after the indent, so every line stands on its own.
    """
    rules = _resolve_rules(rules)
    if width < 1:
        raise ValueError(f"invalid width {width!r} (must be > 0)")
    if ambiguous_width not in (1, 2):
        raise ValueError("ambiguous_width must be 1 or 2")
    iw = _w(initial_indent, ambiguous_width)
    sw = _w(subsequent_indent, ambiguous_width)
    if width - iw < 1 or width - sw < 1:
        raise ValueError("indent is as wide as or wider than width")
    if max_lines is not None and max_lines < 1:
        raise ValueError("max_lines must be >= 1")

    # (indent, body) pairs; the indent stays outside any re-opened styling
    pairs: List[tuple] = []
    for line in text.splitlines() or [""]:
        wrapped = _wrap_line(
            line, width - iw, width - sw, hanging, break_long_words, keep_all,
            ambiguous_width, rules, ansi_reflow,
        )
        pairs.append((initial_indent if wrapped[0] else "", wrapped[0]))
        pairs.extend((subsequent_indent, l) for l in wrapped[1:])

    cut = max_lines is not None and len(pairs) > max_lines
    if cut:
        pairs = pairs[:max_lines]

    if not ansi_reflow:
        out = [i + b for i, b in pairs]
        if cut:
            body = _cut_for_placeholder(
                out[-1], width, placeholder, ambiguous_width, rules
            )
            if "\x1b" in out[-1]:
                body += "\x1b[0m"
            out[-1] = body + placeholder
        return out

    state = _AnsiState()
    out = []
    for k, (indent, body) in enumerate(pairs):
        if cut and k == len(pairs) - 1:
            start = state.copy()
            line = indent + (start.open() if body else "") + body
            kept = _cut_for_placeholder(
                line, width, placeholder, ambiguous_width, rules
            )
            if len(kept) < len(indent):  # the cut ate into the indent
                end = _AnsiState()
                end.feed_text(kept)
            else:
                end = start
                end.feed_text(kept[len(indent):])
            out.append(kept + end.close() + placeholder)
        else:
            out.append(indent + _reflow_body(body, state))
    return out


def _cut_for_placeholder(
    line: str, width_: int, placeholder: str, aw: int, rules: KinsokuRules = _JA
) -> str:
    """Cut ``line`` so that ``placeholder`` can follow it within ``width_``."""
    pw = _w(placeholder, aw)
    if pw > width_:
        raise ValueError("placeholder is wider than width")
    cls = list(_clusters(line))
    while cls and (
        _w("".join(cls), aw) + pw > width_
        or _first(cls[-1]) in _SPACES
        or _first(placeholder) in rules.no_start and _first(cls[-1]) in rules.no_end
    ):
        cls.pop()
    return "".join(cls)


def fill(text: str, width: int = 70, **kwargs) -> str:
    """Like :func:`wrap` but return a single string joined by newlines."""
    return "\n".join(wrap(text, width, **kwargs))


def shorten(text: str, width: int, placeholder: str = "…", **kwargs) -> str:
    """Wrap ``text`` and keep only what fits on one line (like textwrap.shorten,
    but whitespace is not collapsed and kinsoku is respected)."""
    return wrap(text, width, max_lines=1, placeholder=placeholder, **kwargs)[0]


def truncate(
    text: str,
    width: int,
    placeholder: str = "…",
    *,
    ambiguous_width: int = 1,
) -> str:
    """Cut ``text`` to fit in ``width`` columns, appending ``placeholder``.

    ANSI escape sequences are kept intact; if any are present and the text is
    cut, a reset sequence is inserted before the placeholder.
    """
    if _w(text, ambiguous_width) <= width:
        return text
    pw = _w(placeholder, ambiguous_width)
    if pw > width:
        raise ValueError("placeholder is wider than width")
    parts: List[str] = []
    bw = 0
    for cl in _clusters(text):
        cw = _w(cl, ambiguous_width)
        if bw + cw > width - pw:
            break
        parts.append(cl)
        bw += cw
    buf = "".join(parts)
    if "\x1b" in text:
        buf += "\x1b[0m"
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
