"""Core implementation: display width, tokenizing, kinsoku-aware wrapping."""

from __future__ import annotations

import html
import re
import unicodedata
import dataclasses
from dataclasses import dataclass
from bisect import bisect_right
from functools import lru_cache
from itertools import repeat
from types import MappingProxyType
from typing import (
    FrozenSet,
    Iterable,
    Iterator,
    List,
    Mapping,
    Optional,
    Tuple,
    Union,
)

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


# Ruby notation (青空文庫 / なろう形式): ``｜base《ruby》`` or ``漢字《ruby》``.
# Explicit form: base runs from ``｜`` (U+FF5C) or ``|`` up to ``《``.
# Implicit form: base is the run of kanji right before ``《``.
_KANJI = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff々〆ヶ〇"
_RUBY_RE = re.compile(
    r"[｜|](?P<ebase>[^｜|《》\n]+)《(?P<eruby>[^《》\n]+)》"
    r"|(?P<ibase>[" + _KANJI + r"]+)《(?P<iruby>[^《》\n]+)》"
)
_RUBY_WIDTHS = ("base", "full")
_LEADING_ANSI_RE = re.compile("(?:" + _ANSI_RE.pattern + ")+")
_TRAILING_ANSI_RE = re.compile("(?:" + _ANSI_RE.pattern + r")+\Z")


def _ruby_parts(m: "re.Match[str]") -> Tuple[str, str]:
    """(base, ruby) of a ruby-notation match."""
    if m.group("ebase") is not None:
        return m.group("ebase"), m.group("eruby")
    return m.group("ibase"), m.group("iruby")


def strip_ruby(text: str) -> str:
    """Remove ruby annotations, keeping only the base text.

    ``strip_ruby("｜東京《とうきょう》の漢字《かんじ》")`` → ``"東京の漢字"``.
    """
    return _RUBY_RE.sub(lambda m: _ruby_parts(m)[0], text)


def ruby_to_html(text: str) -> str:
    """Convert ruby notation to HTML ``<ruby>`` markup.

    ``ruby_to_html("漢字《かんじ》")`` → ``"<ruby>漢字<rt>かんじ</rt></ruby>"``.
    All text (inside and outside ruby) is HTML-escaped.
    """
    out: List[str] = []
    pos = 0
    for m in _RUBY_RE.finditer(text):
        base, rt = _ruby_parts(m)
        out.append(html.escape(text[pos:m.start()]))
        out.append(f"<ruby>{html.escape(base)}<rt>{html.escape(rt)}</rt></ruby>")
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


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


# --- emoji sequences ----------------------------------------------------------

# Extended_Pictographic (Unicode emoji-data.txt, emoji 15.1), as (first, last)
# code point ranges.  The standard library has no such data, so we keep our
# own table.  Covered: the pictographic code points of Latin-1 (© ®), General
# Punctuation (‼ ⁉), Letterlike Symbols (™ ℹ), Arrows, Misc Technical (⌚ ⏩
# …), Enclosed Alphanumerics (Ⓜ), Geometric Shapes, Misc Symbols, Dingbats,
# Supplemental Arrows-B, Misc Symbols and Arrows (⬅ ⭐ ⭕), CJK Symbols (〰 〽),
# Enclosed CJK (㊗ ㊙), and the whole emoji planes U+1F000–1FAFF (Mahjong,
# Domino, Playing Cards, Enclosed Alphanumeric/Ideographic Supplement, Misc
# Symbols and Pictographs, Emoticons, Transport, Geometric Shapes Extended,
# Supplemental Symbols and Pictographs, Symbols and Pictographs Extended-A)
# plus the reserved U+1FC00–1FFFD.  Regional indicators (U+1F1E6–1F1FF) and
# skin tone modifiers (U+1F3FB–1F3FF) are excluded, as in the Unicode data.
_EXT_PICT = (
    (0x00A9, 0x00A9), (0x00AE, 0x00AE), (0x203C, 0x203C), (0x2049, 0x2049),
    (0x2122, 0x2122), (0x2139, 0x2139), (0x2194, 0x2199), (0x21A9, 0x21AA),
    (0x231A, 0x231B), (0x2328, 0x2328), (0x2388, 0x2388), (0x23CF, 0x23CF),
    (0x23E9, 0x23F3), (0x23F8, 0x23FA), (0x24C2, 0x24C2), (0x25AA, 0x25AB),
    (0x25B6, 0x25B6), (0x25C0, 0x25C0), (0x25FB, 0x25FE), (0x2600, 0x2605),
    (0x2607, 0x2612), (0x2614, 0x2685), (0x2690, 0x2705), (0x2708, 0x2712),
    (0x2714, 0x2714), (0x2716, 0x2716), (0x271D, 0x271D), (0x2721, 0x2721),
    (0x2728, 0x2728), (0x2733, 0x2734), (0x2744, 0x2744), (0x2747, 0x2747),
    (0x274C, 0x274C), (0x274E, 0x274E), (0x2753, 0x2755), (0x2757, 0x2757),
    (0x2763, 0x2767), (0x2795, 0x2797), (0x27A1, 0x27A1), (0x27B0, 0x27B0),
    (0x27BF, 0x27BF), (0x2934, 0x2935), (0x2B05, 0x2B07), (0x2B1B, 0x2B1C),
    (0x2B50, 0x2B50), (0x2B55, 0x2B55), (0x3030, 0x3030), (0x303D, 0x303D),
    (0x3297, 0x3297), (0x3299, 0x3299),
    (0x1F000, 0x1F0FF), (0x1F10D, 0x1F10F), (0x1F12F, 0x1F12F),
    (0x1F16C, 0x1F171), (0x1F17E, 0x1F17F), (0x1F18E, 0x1F18E),
    (0x1F191, 0x1F19A), (0x1F1AD, 0x1F1E5), (0x1F201, 0x1F20F),
    (0x1F21A, 0x1F21A), (0x1F22F, 0x1F22F), (0x1F232, 0x1F23A),
    (0x1F23C, 0x1F23F), (0x1F249, 0x1F3FA), (0x1F400, 0x1F53D),
    (0x1F546, 0x1F64F), (0x1F680, 0x1F6FF), (0x1F774, 0x1F77F),
    (0x1F7D5, 0x1F7FF), (0x1F80C, 0x1F80F), (0x1F848, 0x1F84F),
    (0x1F85A, 0x1F85F), (0x1F888, 0x1F88F), (0x1F8AE, 0x1F8FF),
    (0x1F90C, 0x1F93A), (0x1F93C, 0x1F945), (0x1F947, 0x1FAFF),
    (0x1FC00, 0x1FFFD),
)
_EXT_PICT_STARTS = tuple(a for a, _ in _EXT_PICT)

_ZWJ = "‍"
_VS15 = "︎"
_VS16 = "️"
_KEYCAP = "⃣"
_KEYCAP_BASES = frozenset("#*0123456789")

# Any character that can make a cluster's width differ from the sum of its
# code point widths.  Text without these is measured per code point.
_EMOJI_SEQ_RE = re.compile(
    "[‍︎️⃣\U0001F1E6-\U0001F1FF"
    "\U0001F3FB-\U0001F3FF\U000E0020-\U000E007F]"
)


def _is_ext_pict(ch: str) -> bool:
    """Whether ``ch`` is Extended_Pictographic (see :data:`_EXT_PICT`)."""
    cp = ord(ch)
    if cp < 0xA9:
        return False
    i = bisect_right(_EXT_PICT_STARTS, cp) - 1
    return i >= 0 and cp <= _EXT_PICT[i][1]


@lru_cache(maxsize=8192)
def _cluster_kind(ch: str) -> int:
    """How ``ch`` joins the cluster before it: 0 starts a new cluster,
    1 extends it (zero width, skin tone modifier), 2 is a regional indicator."""
    if "\U0001F1E6" <= ch <= "\U0001F1FF":
        return 2
    if "\U0001F3FB" <= ch <= "\U0001F3FF":
        return 1
    return 1 if _char_width(ch, 1) == 0 and ch != "\t" else 0


@lru_cache(maxsize=4096)
def _cluster_width(cl: str, ambiguous_width: int) -> int:
    """Display width of one grapheme cluster (no escape sequences).

    A cluster shown as an emoji is 2 columns wide: an emoji ZWJ sequence, an
    emoji with a skin tone modifier, a tag sequence (🏴󠁧󠁢󠁥󠁮󠁧󠁿), an emoji
    presentation sequence (VS16, as in ❤️), a keycap (1️⃣) and a flag (a pair
    of regional indicators).  With VS15 (text presentation) the cluster keeps
    the width of its characters.  Emoji sequences must start with an
    Extended_Pictographic character (or ``#*0-9`` for keycaps); anything
    else is the sum of its characters' widths.
    """
    plain = sum(map(_char_width, cl, repeat(ambiguous_width)))
    if len(cl) == 1 or not _EMOJI_SEQ_RE.search(cl):
        return plain
    base = cl[0]
    if "\U0001F1E6" <= base <= "\U0001F1FF":
        if len(cl) >= 2 and "\U0001F1E6" <= cl[1] <= "\U0001F1FF":
            return 2  # flag
        return plain
    if _VS15 in cl and _VS16 not in cl and _ZWJ not in cl:
        return plain  # text presentation: the characters' own width
    if base in _KEYCAP_BASES:
        if _VS16 in cl or _KEYCAP in cl:
            return 2  # keycap / emoji digit
        return plain
    if _is_ext_pict(base):
        return 2  # VS16, skin tone, ZWJ or tag sequence on an emoji
    return plain


def width(text: str, ambiguous_width: int = 1) -> int:
    """Return the display width of ``text`` in terminal columns.

    The width is the sum of the widths of its grapheme clusters, so emoji
    sequences (ZWJ, skin tones, VS16, keycaps, flags) count as 2 columns.
    ANSI escape sequences are ignored.
    """
    if "\x1b" in text:
        text = strip_ansi(text)
    if text.isascii() and text.isprintable():
        return len(text)
    if _EMOJI_SEQ_RE.search(text) is None:
        return sum(map(_char_width, text, repeat(ambiguous_width)))
    return sum(
        _cluster_width(cl, ambiguous_width) for cl in _clusters_plain(text)
    )


def _clusters(text: str) -> Iterator[str]:
    """Yield grapheme clusters.

    A cluster is a base character plus trailing zero-width characters
    (combining marks, variation selectors, keycap, tags), skin tone
    modifiers, and anything joined by ZWJ; two regional indicators form one
    flag.  ANSI escape sequences are kept intact and attached to a
    neighbouring cluster, so they are never split and never counted.
    """
    if "\x1b" not in text:
        yield from _clusters_plain(text)
        return
    kind = _cluster_kind
    buf = ""
    prefix = ""  # escapes seen before any base char of the next cluster
    joiner = False
    ri_open = False  # buf is a lone regional indicator
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
        k = kind(ch)
        if buf and (joiner or k == 1 or (k == 2 and ri_open)):
            buf += ch
            ri_open = False
        else:
            if buf:
                yield buf
            buf = prefix + ch
            prefix = ""
            ri_open = k == 2
        joiner = ch == _ZWJ
    if buf or prefix:
        yield buf + prefix


def _clusters_plain(text: str) -> Iterator[str]:
    """:func:`_clusters` for text without escape sequences."""
    if text.isascii() and text.isprintable():
        yield from text
        return
    kind = _cluster_kind
    buf = ""
    joiner = False
    ri_open = False
    for ch in text:
        k = kind(ch)
        if buf and (joiner or k == 1 or (k == 2 and ri_open)):
            buf += ch
            ri_open = False
        else:
            if buf:
                yield buf
            buf = ch
            ri_open = k == 2
        joiner = ch == _ZWJ
    if buf:
        yield buf


def _pieces(
    text: str,
    ambiguous_width: int,
    ruby: bool = False,
    ruby_width: str = "full",
) -> Iterator[Tuple[str, int]]:
    """Yield ``(cluster, width)`` pairs.

    With ``ruby=True`` every ruby notation is yielded as one indivisible
    cluster; its width is that of the base text (``ruby_width="base"``) or
    of the whole notation (``"full"``).  ANSI escapes right before a ruby
    notation are attached to its start and those right after it to its end,
    so styling around a ruby unit always moves with it.
    """
    if not ruby or "《" not in text:
        for cl in _clusters(text):
            yield cl, width(cl, ambiguous_width)
        return
    pos = 0
    held: Optional[Tuple[str, int]] = None  # previous ruby unit
    for m in _RUBY_RE.finditer(text):
        seg = text[pos:m.start()]
        if held is not None:
            lead = _LEADING_ANSI_RE.match(seg)
            if lead:
                held = (held[0] + lead.group(), held[1])
                seg = seg[lead.end():]
            yield held
        pre = ""
        tail = _TRAILING_ANSI_RE.search(seg)
        if tail:
            pre = tail.group()
            seg = seg[:tail.start()]
        for cl in _clusters(seg):
            yield cl, width(cl, ambiguous_width)
        unit = m.group()
        if ruby_width == "base":
            held = (pre + unit, width(_ruby_parts(m)[0], ambiguous_width))
        else:
            held = (pre + unit, width(unit, ambiguous_width))
        pos = m.end()
    seg = text[pos:]
    if held is not None:
        lead = _LEADING_ANSI_RE.match(seg)
        if lead:
            held = (held[0] + lead.group(), held[1])
            seg = seg[lead.end():]
        yield held
    for cl in _clusters(seg):
        yield cl, width(cl, ambiguous_width)


def _base(cl: str) -> str:
    """First visible character of a cluster ("" for a pure escape cluster)."""
    if cl[:1] == "\x1b":
        cl = strip_ansi(cl)
    return cl[:1]


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
    ruby: bool = False,
    ruby_width: str = "full",
) -> List[_Unit]:
    """Split text into atoms: spaces, word runs, single wide clusters.

    A ruby notation (``ruby=True``) is one atom, or part of a latin word
    when its base text starts with a narrow character.
    """
    atoms: List[_Unit] = []
    word: List[str] = []  # clusters of the current word run
    word_w = 0
    append = atoms.append
    cw = _char_width
    no_start = rules.no_start
    no_end = rules.no_end

    if ruby and "《" in text:
        for cl, w in _pieces(text, ambiguous_width, True, ruby_width):
            b = _base(cl)
            s = strip_ansi(cl) if "\x1b" in cl else cl
            if len(s) > 1 and s[0] in ("｜", "|") and "《" in s:
                b = s[1]  # explicit ruby unit: classify by its base text
            if b and b in _SPACES:
                if word:
                    append(_Unit("".join(word), word_w))
                    word, word_w = [], 0
                append(_Unit(cl, w or 1, space=True))
            elif b and not keep_all and (
                char_width(b, ambiguous_width) >= 2 or b in no_start or b in no_end
            ):
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
    u: _Unit,
    limit: int,
    ambiguous_width: int,
    rules: KinsokuRules = _JA,
    ruby: bool = False,
    ruby_width: str = "full",
) -> List[_Unit]:
    """Hard-split an over-long unit into chunks no wider than ``limit``.

    Ruby notations (``ruby=True``) are never split.
    """
    if ruby:
        pieces = list(_pieces(u.text, ambiguous_width, ruby, ruby_width))
        cls = [c for c, _ in pieces]
        ws = [w for _, w in pieces]
    else:
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
            else:
                if ruby and end == start + 1 and _RUBY_RE.fullmatch(strip_ansi(cls[start])):
                    # a lone, unbreakable ruby unit: let the line overflow
                    # rather than push 。」 etc. to the start of the next line
                    while end < n and not good_break(end):
                        end += 1
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
    ruby: bool = False,
    ruby_width: str = "full",
) -> List[str]:
    units = _glue(
        _atoms(line, ambiguous_width, keep_all, rules, ruby, ruby_width),
        hanging,
        ambiguous_width,
        rules,
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
                pieces = _split_long(
                    u, limit(), ambiguous_width, rules, ruby, ruby_width
                )
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
    ruby: bool = False,
    ruby_width: str = "full",
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
    :param ruby: recognize ruby notation (``｜漢字《かんじ》`` / ``漢字《かんじ》``,
        青空文庫・なろう形式). The base text and its ruby form one unbreakable
        unit; kinsoku still applies around it.
    :param ruby_width: how a ruby unit is measured when ``ruby=True``:
        ``"full"`` (default) counts the notation as displayed, including
        ``｜《》`` and the annotation; ``"base"`` counts only the base text
        (for output that is later rendered as real ruby).
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
    if ruby_width not in _RUBY_WIDTHS:
        raise ValueError("ruby_width must be 'base' or 'full'")

    # (indent, body) pairs; the indent stays outside any re-opened styling
    pairs: List[tuple] = []
    for line in text.splitlines() or [""]:
        wrapped = _wrap_line(
            line, width - iw, width - sw, hanging, break_long_words, keep_all,
            ambiguous_width, rules, ansi_reflow, ruby, ruby_width,
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
                out[-1], width, placeholder, ambiguous_width, rules, ruby, ruby_width
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
                line, width, placeholder, ambiguous_width, rules, ruby, ruby_width
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
    line: str,
    width_: int,
    placeholder: str,
    aw: int,
    rules: KinsokuRules = _JA,
    ruby: bool = False,
    ruby_width: str = "full",
) -> str:
    """Cut ``line`` so that ``placeholder`` can follow it within ``width_``."""
    pw = _w(placeholder, aw)
    if pw > width_:
        raise ValueError("placeholder is wider than width")
    pieces = list(_pieces(line, aw, ruby, ruby_width))
    total = sum(w for _, w in pieces)
    while pieces and (
        total + pw > width_
        or _first(pieces[-1][0]) in _SPACES
        or _first(placeholder) in rules.no_start
        and _first(pieces[-1][0]) in rules.no_end
    ):
        total -= pieces.pop()[1]
    return "".join(c for c, _ in pieces)


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
