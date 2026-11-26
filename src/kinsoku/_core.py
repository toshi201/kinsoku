"""Core implementation: display width, tokenizing, kinsoku-aware wrapping."""

from __future__ import annotations

import dataclasses
import html
import re
import unicodedata
from bisect import bisect_right
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from functools import lru_cache
from itertools import repeat
from types import MappingProxyType
from typing import Any, Literal

# 行頭禁則: characters that must not start a line.
NO_START = frozenset(
    "、。，．,.!?！？‼⁇⁈⁉)）]］}｝〕〉》」』】〙〗〟’”｠»"
    "ゝゞーァィゥェォッャュョヮヵヶぁぃぅぇぉっゃゅょゎゕゖ"
    "ㇰㇱㇲㇳㇴㇵㇶㇷㇸㇹㇺㇻㇼㇽㇾㇿ"
    "…‥・：；:;゛゜ヽヾ々〻‐゠–〜～%％"
    "｡､｣･ｰﾞﾟｧｨｩｪｫｬｭｮｯ"
)

# 行末禁則: characters that must not end a line.
NO_END = frozenset("(（[［{｛〔〈《「『【〘〖〝‘“｟«｢")

# ぶら下げ可能: punctuation allowed to hang past the right margin.
HANGABLE = frozenset("、。，．,.")

# Halfwidth katakana and punctuation (U+FF61-FF9F).
_HW_SMALL = "ｧｨｩｪｫｬｭｮｯ"
# Halfwidth (semi-)voiced sound marks: always kept with the preceding char.
_HW_SOUND = frozenset("ﾞﾟ")

# Kinsoku punctuation that stays inside a word between ASCII word characters
# (decimals, version numbers, digit grouping, URLs, file names).
_INFIX = frozenset(".,:;!?%")
# ASCII word characters that may surround infix punctuation
_WORD_CH = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_")
# characters that may follow infix punctuation (``/`` for ``https://``)
_INFIX_NEXT = _WORD_CH | {"/"}
# ASCII brackets that stay inside a word when the opening one directly
# follows an ASCII word character (``print(x)``, ``a[0]``, ``f{x}``, #65)
_BRACKETS = {"(": ")", "[": "]", "{": "}"}
_CLOSERS = frozenset(_BRACKETS.values())
# characters after which infix punctuation or an opening bracket stays in
# the word: word characters and a closing bracket kept in the word
_WORD_END = _WORD_CH | _CLOSERS


@dataclass(frozen=True, init=False)
class KinsokuRules:
    """A set of line-breaking (kinsoku) rules.

    :param no_start: characters that must not start a line (行頭禁則).
    :param no_end: characters that must not end a line (行末禁則).
    :param hangable: punctuation allowed to hang past the margin with
        ``hanging=True`` (ぶら下げ).
    :param quotes: ASCII-style quotes whose opening and closing forms look
        the same (``"`` ``'``, the default).  Next to CJK text they are
        told apart by context and kept with the text they quote: an opening
        quote never ends a line and a closing one never starts a line.
        Inside latin words and phrases (``"hello world"``, ``don't``)
        nothing changes.  ``quotes=""`` turns this off.

    Any iterable of characters (including a plain ``str``) is accepted and
    converted to a ``frozenset``. To customize a preset, use
    :meth:`preset` + :meth:`replace` (equivalent to
    :func:`dataclasses.replace`)::

        rules = KinsokuRules.preset("ja")
        rules = rules.replace(no_start=rules.no_start - {"ー"})
    """

    no_start: frozenset[str] = frozenset()
    no_end: frozenset[str] = frozenset()
    hangable: frozenset[str] = frozenset()
    quotes: frozenset[str] = frozenset("\"'")

    # An explicit __init__ (instead of the generated one + __post_init__) so
    # that the signature says what is accepted: any iterable of characters.
    def __init__(
        self,
        no_start: Iterable[str] = frozenset(),
        no_end: Iterable[str] = frozenset(),
        hangable: Iterable[str] = frozenset(),
        quotes: Iterable[str] = frozenset("\"'"),
    ) -> None:
        for name, value in (
            ("no_start", no_start),
            ("no_end", no_end),
            ("hangable", hangable),
            ("quotes", quotes),
        ):
            if isinstance(value, str) or not isinstance(value, frozenset):
                value = frozenset(value)
            object.__setattr__(self, name, value)

    @classmethod
    def preset(cls, name: str) -> KinsokuRules:
        """Return the built-in preset called ``name`` (see :data:`PRESETS`)."""
        try:
            return PRESETS[name]
        except (KeyError, TypeError):
            valid = ", ".join(PRESETS)
            raise ValueError(f"unknown rules preset {name!r} (valid: {valid})") from None

    def replace(self, **changes: Iterable[str]) -> KinsokuRules:
        """Return a copy with some fields replaced (like :func:`dataclasses.replace`)."""
        # mypy checks replace() against the field types (frozenset), but
        # __init__ accepts any iterable of characters
        return dataclasses.replace(self, **changes)  # type: ignore[arg-type]


_SMALL_KANA = "ァィゥェォッャュョヮヵヶぁぃぅぇぉっゃゅょゎゕゖㇰㇱㇲㇳㇴㇵㇶㇷㇸㇹㇺㇻㇼㇽㇾㇿ"
# Characters that CSS ``line-break: loose`` lets start a line: small kana,
# the prolonged sound mark, iteration marks and hyphen-like characters.
_LOOSE_ALLOWED = frozenset(_SMALL_KANA + "ー々〻ゝゞヽヾ‐゠–〜～" + _HW_SMALL + "ｰ")

_ZH_NO_START = "，。、．！？；：…‥·・”’」』）》〉】〗〕］｝〙〛｠,.!?;:)]}%％"
_ZH_NO_END = "“‘「『（《〈【〖〔［｛〘〚｟([{"
_ZH_HANGABLE = "，。、．,."

PRESETS: Mapping[str, KinsokuRules] = MappingProxyType(
    {
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
    }
)

_JA = PRESETS["ja"]

RulesLike = str | KinsokuRules


def _resolve_rules(rules: RulesLike) -> KinsokuRules:
    if isinstance(rules, KinsokuRules):
        return rules
    if isinstance(rules, str):
        return KinsokuRules.preset(rules)
    raise TypeError(f"rules must be a preset name or KinsokuRules, not {type(rules).__name__}")


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


def _ruby_parts(m: re.Match[str]) -> tuple[str, str]:
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
    out: list[str] = []
    pos = 0
    for m in _RUBY_RE.finditer(text):
        base, rt = _ruby_parts(m)
        out.append(html.escape(text[pos : m.start()]))
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
_ATTR_ON = {
    1: "bold",
    2: "dim",
    3: "italic",
    4: "underline",
    21: "underline",
    5: "blink",
    6: "blink",
    7: "inverse",
    8: "hidden",
    9: "strike",
    53: "overline",
}
_ATTR_OFF = {
    22: ("bold", "dim"),
    23: ("italic",),
    24: ("underline",),
    25: ("blink",),
    27: ("inverse",),
    28: ("hidden",),
    29: ("strike",),
    55: ("overline",),
}
_SLOTS = (
    "bold",
    "dim",
    "italic",
    "underline",
    "blink",
    "inverse",
    "hidden",
    "strike",
    "overline",
    "fg",
    "bg",
    "ulcolor",
)
_COLOR_SLOT = {38: "fg", 48: "bg", 58: "ulcolor"}


class _AnsiState:
    """Tracks the SGR attributes and the OSC 8 hyperlink active in a stream."""

    def __init__(self) -> None:
        self.sgr: dict[str, str] = {}
        self.link: tuple[str, str, str] | None = None  # (params, uri, terminator)

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
                st[_COLOR_SLOT[c]] = ";".join([str(c)] + ps[i : i + n])
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

    def copy(self) -> _AnsiState:
        c = _AnsiState()
        c.sgr = dict(self.sgr)
        c.link = self.link
        return c


def _close_after(text: str) -> str:
    """Sequence that closes the SGR / OSC 8 state left open by ``text``."""
    if "\x1b" not in text:
        return ""
    state = _AnsiState()
    state.feed_text(text)
    return state.close()


def _reflow_body(body: str, state: _AnsiState) -> str:
    """Re-open ``state`` before ``body``, update it, close it at the end."""
    if not body:
        return body
    prefix = state.open()
    state.feed_text(body)
    return prefix + body + state.close()


def ansi_reflow(lines: list[str]) -> list[str]:
    """Make each line self-contained with respect to ANSI styling.

    Lines that end with active SGR attributes (colors, bold, ...) or an open
    OSC 8 hyperlink get them closed at the end, and the next line re-opens
    the same state at its start. Lines without active styling are unchanged.
    """
    state = _AnsiState()
    return [_reflow_body(line, state) for line in lines]


# --- argument validation --------------------------------------------------------
# Every public function checks its arguments with these helpers, so the same
# bad value gives the same ValueError (with the same message) everywhere.

Align = Literal["left", "right", "center", "<", ">", "^"]
_CanonicalAlign = Literal["left", "right", "center"]

_ALIGNS: Mapping[str, _CanonicalAlign] = MappingProxyType(
    {
        "left": "left",
        "<": "left",
        "right": "right",
        ">": "right",
        "center": "center",
        "^": "center",
    }
)


def _check_ambiguous_width(ambiguous_width: int) -> None:
    """Raise ValueError unless ``ambiguous_width`` is 1 or 2."""
    if ambiguous_width not in (1, 2):
        raise ValueError(f"ambiguous_width must be 1 or 2, not {ambiguous_width!r}")


def _check_width(value: int, name: str = "width", *, allow_zero: bool = False) -> None:
    """Raise ValueError unless ``value`` is > 0 (>= 0 with ``allow_zero``)."""
    if allow_zero:
        if value < 0:
            raise ValueError(f"invalid {name} {value!r} (must be >= 0)")
    elif value < 1:
        raise ValueError(f"invalid {name} {value!r} (must be > 0)")


def _check_align(align: str) -> _CanonicalAlign:
    """Return the canonical name (left, right, center) of ``align``.

    ``"<"``, ``">"`` and ``"^"`` (as in :func:`format`) are accepted too.
    """
    try:
        return _ALIGNS[align]
    except (KeyError, TypeError):
        raise ValueError(f"unknown align {align!r} (choose from left, right, center)") from None


def char_width(ch: str, ambiguous_width: int = 1) -> int:
    """Return the terminal display width (0, 1 or 2) of a single character.

    :raises ValueError: if ``ambiguous_width`` is not 1 or 2.
    """
    if ambiguous_width not in (1, 2):
        _check_ambiguous_width(ambiguous_width)
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
    # Hangul medial vowels and final consonants (conjoining jamo, including
    # Jamo Extended-B) combine with the leading consonant before them into
    # one syllable that is as wide as the leading consonant alone.
    if 0x1160 <= cp <= 0x11FF or 0xD7B0 <= cp <= 0xD7FF:
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
    (0x00A9, 0x00A9),
    (0x00AE, 0x00AE),
    (0x203C, 0x203C),
    (0x2049, 0x2049),
    (0x2122, 0x2122),
    (0x2139, 0x2139),
    (0x2194, 0x2199),
    (0x21A9, 0x21AA),
    (0x231A, 0x231B),
    (0x2328, 0x2328),
    (0x2388, 0x2388),
    (0x23CF, 0x23CF),
    (0x23E9, 0x23F3),
    (0x23F8, 0x23FA),
    (0x24C2, 0x24C2),
    (0x25AA, 0x25AB),
    (0x25B6, 0x25B6),
    (0x25C0, 0x25C0),
    (0x25FB, 0x25FE),
    (0x2600, 0x2605),
    (0x2607, 0x2612),
    (0x2614, 0x2685),
    (0x2690, 0x2705),
    (0x2708, 0x2712),
    (0x2714, 0x2714),
    (0x2716, 0x2716),
    (0x271D, 0x271D),
    (0x2721, 0x2721),
    (0x2728, 0x2728),
    (0x2733, 0x2734),
    (0x2744, 0x2744),
    (0x2747, 0x2747),
    (0x274C, 0x274C),
    (0x274E, 0x274E),
    (0x2753, 0x2755),
    (0x2757, 0x2757),
    (0x2763, 0x2767),
    (0x2795, 0x2797),
    (0x27A1, 0x27A1),
    (0x27B0, 0x27B0),
    (0x27BF, 0x27BF),
    (0x2934, 0x2935),
    (0x2B05, 0x2B07),
    (0x2B1B, 0x2B1C),
    (0x2B50, 0x2B50),
    (0x2B55, 0x2B55),
    (0x3030, 0x3030),
    (0x303D, 0x303D),
    (0x3297, 0x3297),
    (0x3299, 0x3299),
    (0x1F000, 0x1F0FF),
    (0x1F10D, 0x1F10F),
    (0x1F12F, 0x1F12F),
    (0x1F16C, 0x1F171),
    (0x1F17E, 0x1F17F),
    (0x1F18E, 0x1F18E),
    (0x1F191, 0x1F19A),
    (0x1F1AD, 0x1F1E5),
    (0x1F201, 0x1F20F),
    (0x1F21A, 0x1F21A),
    (0x1F22F, 0x1F22F),
    (0x1F232, 0x1F23A),
    (0x1F23C, 0x1F23F),
    (0x1F249, 0x1F3FA),
    (0x1F400, 0x1F53D),
    (0x1F546, 0x1F64F),
    (0x1F680, 0x1F6FF),
    (0x1F774, 0x1F77F),
    (0x1F7D5, 0x1F7FF),
    (0x1F80C, 0x1F80F),
    (0x1F848, 0x1F84F),
    (0x1F85A, 0x1F85F),
    (0x1F888, 0x1F88F),
    (0x1F8AE, 0x1F8FF),
    (0x1F90C, 0x1F93A),
    (0x1F93C, 0x1F945),
    (0x1F947, 0x1FAFF),
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
_EMOJI_SEQ_RE = re.compile("[‍︎️⃣\U0001f1e6-\U0001f1ff\U0001f3fb-\U0001f3ff\U000e0020-\U000e007f]")


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
    1 extends it (zero width, skin tone modifier), 2 is a regional indicator,
    3 is a Hangul leading consonant (L) and 4 a precomposed Hangul syllable
    (LV / LVT); 3 and 4 join a cluster that ends in an L.

    Hangul medial vowels (V) and final consonants (T) are zero width, so
    they extend the cluster before them: an L + V (+ T) sequence (NFD
    Hangul) is one cluster, as in the Unicode Hangul syllable rules
    (UAX #29 GB6–GB8).
    """
    if "\u1100" <= ch <= "\u115f" or "\ua960" <= ch <= "\ua97f":
        return 3
    if "\uac00" <= ch <= "\ud7a3":
        return 4
    if "\U0001f1e6" <= ch <= "\U0001f1ff":
        return 2
    if "\U0001f3fb" <= ch <= "\U0001f3ff":
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
    if "\U0001f1e6" <= base <= "\U0001f1ff":
        if len(cl) >= 2 and "\U0001f1e6" <= cl[1] <= "\U0001f1ff":
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


def width(text: str, ambiguous_width: int = 1, *, tabsize: int = 8) -> int:
    """Return the display width of ``text`` in terminal columns.

    The width is the sum of the widths of its grapheme clusters, so emoji
    sequences (ZWJ, skin tones, VS16, keycaps, flags) count as 2 columns.
    ANSI escape sequences are ignored. A tab advances to the next multiple
    of ``tabsize`` columns (counted by display width from the start of the
    line, wide characters as 2), so the result is the width of ``text``
    with its tabs expanded the way :func:`wrap` expands them.  Line breaks
    reset the tab column and count as zero width.

    :raises ValueError: if ``ambiguous_width`` is not 1 or 2.
    """
    if ambiguous_width not in (1, 2):
        _check_ambiguous_width(ambiguous_width)
    if "\t" in text:
        text = _expand_tabs(text, tabsize, ambiguous_width)
    if "\x1b" in text:
        text = strip_ansi(text)
    if text.isascii() and text.isprintable():
        return len(text)
    if _EMOJI_SEQ_RE.search(text) is None:
        return sum(map(_char_width, text, repeat(ambiguous_width)))
    return sum(_cluster_width(cl, ambiguous_width) for cl in _clusters_plain(text))


_TAB_SPLIT_RE = re.compile(r"(\t|\r\n|\n|\r)")


def _expand_tabs(text: str, tabsize: int, ambiguous_width: int) -> str:
    """``str.expandtabs`` that counts columns by display width.

    Wide characters count as two columns and ANSI escapes as none, so a tab
    after ``"日本"`` (4 columns) advances to column 8.  ``tabsize <= 0``
    removes tabs, like :meth:`str.expandtabs`.
    """
    if "\t" not in text:
        return text
    out: list[str] = []
    col = 0
    for part in _TAB_SPLIT_RE.split(text):
        if part == "\t":
            n = tabsize - col % tabsize if tabsize > 0 else 0
            out.append(" " * n)
            col += n
        elif part in ("\r\n", "\n", "\r"):
            out.append(part)
            col = 0
        elif part:
            out.append(part)
            col += width(part, ambiguous_width)
    return "".join(out)


def _clusters(text: str) -> Iterator[str]:
    """Yield grapheme clusters.

    A cluster is a base character plus trailing zero-width characters
    (combining marks, variation selectors, keycap, tags), skin tone
    modifiers, and anything joined by ZWJ; two regional indicators form one
    flag.  Decomposed (NFD) Hangul — a leading consonant followed by a vowel
    and an optional final consonant, written as conjoining jamo — is one
    cluster, like the precomposed syllable.  ANSI escape sequences are kept intact and attached to a
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
    lead = False  # buf ends in a Hangul leading consonant
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
        if buf and (joiner or k == 1 or (k == 2 and ri_open) or (k > 2 and lead)):
            buf += ch
            ri_open = False
        else:
            if buf:
                yield buf
            buf = prefix + ch
            prefix = ""
            ri_open = k == 2
        joiner = ch == _ZWJ
        lead = k == 3
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
    lead = False
    for ch in text:
        k = kind(ch)
        if buf and (joiner or k == 1 or (k == 2 and ri_open) or (k > 2 and lead)):
            buf += ch
            ri_open = False
        else:
            if buf:
                yield buf
            buf = ch
            ri_open = k == 2
        joiner = ch == _ZWJ
        lead = k == 3
    if buf:
        yield buf


def _pieces(
    text: str,
    ambiguous_width: int,
    ruby: bool = False,
    ruby_width: str = "full",
) -> Iterator[tuple[str, int]]:
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
    held: tuple[str, int] | None = None  # previous ruby unit
    for m in _RUBY_RE.finditer(text):
        seg = text[pos : m.start()]
        if held is not None:
            lead = _LEADING_ANSI_RE.match(seg)
            if lead:
                held = (held[0] + lead.group(), held[1])
                seg = seg[lead.end() :]
            yield held
        pre = ""
        tail = _TRAILING_ANSI_RE.search(seg)
        if tail:
            pre = tail.group()
            seg = seg[: tail.start()]
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
            seg = seg[lead.end() :]
        yield held
    for cl in _clusters(seg):
        yield cl, width(cl, ambiguous_width)


def _base(cl: str) -> str:
    """First visible character of a cluster ("" for a pure escape cluster)."""
    if cl[:1] == "\x1b":
        cl = strip_ansi(cl)
    return cl[:1]


def _last_base(word: list[str]) -> str:
    """Base character of the last visible cluster of a word run."""
    for c in reversed(word):
        b = c if len(c) == 1 else _base(c)
        if b:
            return b
    return ""


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
    glue_next: bool = False  # an opening quote: keep with the next atom
    glue_prev: bool = False  # a closing quote: keep with the previous atom


def _atoms(
    text: str,
    ambiguous_width: int,
    keep_all: bool = False,
    rules: KinsokuRules = _JA,
    ruby: bool = False,
    ruby_width: str = "full",
) -> list[_Unit]:
    """Split text into atoms: spaces, word runs, single wide clusters.

    A word run is a run of narrow clusters. Punctuation such as ``.`` ``,``
    ``:`` that is a kinsoku character normally forms its own atom, but when
    it sits between ASCII word characters (letters, digits, ``_``) --
    ``v1.2.3``, ``1,000``, ``https://example.com``, ``config.yaml`` -- it
    stays inside the word. Before a symbol (``foo."bar"``, ``end.)``) it
    stays an atom of its own.
    An ASCII opening bracket ``(`` ``[`` ``{`` right after an ASCII word
    character, and its matching closing bracket, stay inside the word too
    (``print(x)``, ``a[0]``, ``foo.bar.baz()``); a bracket before a word
    (``(see above)``, ``言った(笑)``) is an atom as before.
    Halfwidth katakana are atoms of their own, like wide kana, and the
    halfwidth sound marks ``ﾞ`` ``ﾟ`` always stick to the preceding cluster.

    A ruby notation (``ruby=True``) is one atom, or part of a latin word
    when its base text starts with a narrow character.
    """
    atoms: list[_Unit] = []
    word: list[str] = []  # clusters of the current word run
    word_w = 0
    # (cluster, width) of infix punctuation after an ASCII word, kept in the
    # word only if another ASCII word character follows
    pend: list[tuple[str, int]] = []
    # closing brackets expected for the opening brackets kept in the word
    opened: list[str] = []
    append = atoms.append
    cw = _char_width
    no_start = rules.no_start
    no_end = rules.no_end
    infix = _INFIX
    infix_next = _INFIX_NEXT
    word_end = _WORD_END
    brackets = _BRACKETS
    closers = _CLOSERS
    sound = _HW_SOUND

    def flush() -> None:
        nonlocal word, word_w
        if opened:
            opened.clear()
        if word:
            append(_Unit("".join(word), word_w))
            word, word_w = [], 0
        if pend:
            for c, cwid in pend:
                append(_Unit(c, cwid))
            pend.clear()

    if ruby and "《" in text:
        src: Iterable[Any] = _ruby_items(text, ambiguous_width, ruby_width)
        rmode = True
    else:
        src = _clusters(text)
        rmode = False

    # ASCII quotes next to CJK text (#52): decide open/close up front, since
    # that needs the next character
    qs = rules.quotes - no_start - no_end
    qdec: Iterator[bool | None] | None = None
    if qs and not keep_all and any(q in text for q in qs):
        src = list(src)
        qdec = iter(_quote_kinds(src, rmode, qs, no_start, no_end))

    for cl in src:
        # The width of a word run is the sum of its cluster widths, so each
        # cluster is measured exactly once.
        if rmode:
            cl, w, b, bw = cl
        elif len(cl) == 1:  # the common case: a lone character, no escapes
            b = cl
            w = bw = cw(cl, ambiguous_width)
        else:
            b = _base(cl)
            w = width(cl, ambiguous_width)
            bw = char_width(b, ambiguous_width) if b else 0
        if b and b in _SPACES:
            if word or pend:
                flush()
            append(_Unit(cl, w or 1, space=True))
        elif (
            b
            and not keep_all
            and (bw >= 2 or b in no_start or b in no_end or "\uff61" <= b <= "\uff9f")
        ):
            if b in sound:
                # ﾞ ﾟ: never separated from the preceding cluster
                if pend:
                    flush()
                if word:
                    word.append(cl)
                    word_w += w
                elif atoms and not atoms[-1].space:
                    atoms[-1].text += cl
                    atoms[-1].width += w
                else:
                    append(_Unit(cl, w))
            elif b in brackets and bw == 1 and not pend and _last_base(word) in word_end:
                # ``foo(``: the bracket is part of the word (#65)
                opened.append(brackets[b])
                word.append(cl)
                word_w += w
            elif b in closers and opened and not pend and b == opened[-1]:
                opened.pop()
                word.append(cl)
                word_w += w
            elif b in infix and bw == 1 and not pend and _last_base(word) in word_end:
                pend.append((cl, w))
            else:
                if word or pend:
                    flush()
                append(_Unit(cl, w))
        else:
            if qdec is not None and b in qs:
                kind = next(qdec)
                if kind is not None:
                    if kind:  # opening: glued to what follows
                        if word or pend:
                            flush()
                        append(_Unit(cl, w, glue_next=True))
                        continue
                    if not word or pend:  # closing: glued to what precedes
                        if word or pend:
                            flush()
                        append(_Unit(cl, w, glue_prev=True))
                        continue
            if pend:
                if not b:  # escape-only cluster: decide on the next character
                    pend.append((cl, w))
                    continue
                if b in infix_next:
                    for c, cwid in pend:
                        word.append(c)
                        word_w += cwid
                    pend.clear()
                else:
                    flush()
            word.append(cl)
            word_w += w
    if word or pend:
        flush()
    return atoms


_SENTENCE_END = frozenset("。！？．")


def _quote_kinds(
    items: list[Any],
    rmode: bool,
    qs: frozenset[str],
    no_start: frozenset[str],
    no_end: frozenset[str],
) -> list[bool | None]:
    """Classify each quote in ``items`` (clusters or ruby items) for :func:`_atoms`.

    ``True`` is an opening quote, ``False`` a closing one and ``None`` a
    quote left alone (inside a latin word such as ``don't``, or between
    spaces).  A quote before a space or the end of the line closes, one
    after a space, the start of the line or an opening bracket opens, one
    before closing punctuation (``"。``) closes, and one between two other
    characters (``彼は"テスト"と``) closes only if a quote of the same kind
    is open.  That last rule needs a non-ASCII character on at least one
    side; a quote between two ASCII characters (``key:"value"``) is left
    alone.  A quote that opened English text and is still open at the end
    of a sentence no longer counts as open (#60).
    """
    bases = []
    for it in items:
        if rmode:
            bases.append(it[2])
        else:
            bases.append(it if len(it) == 1 else _base(it))
    kinds: list[bool | None] = []
    opened: dict[str, list[bool]] = {}  # open quotes: True if opened English text
    wch = _WORD_CH
    prev = ""
    n = len(bases)
    for i, b in enumerate(bases):
        if not b:
            continue
        if b in qs:
            j = i + 1
            while j < n and not bases[j]:
                j += 1
            nxt = bases[j] if j < n else ""
            kind: bool | None
            if not nxt or nxt in _SPACES:
                kind = False if prev and prev not in _SPACES else None
            elif not prev or prev in _SPACES or prev in no_end:
                kind = True
            elif nxt in no_start:
                kind = False
            elif (prev in wch and nxt in wch) or (prev[0] < "\x80" and nxt[0] < "\x80"):
                # Between two ASCII characters (``key:"value"``) the quote
                # stays part of the latin word, as before; the depth rule is
                # only for quotes touching non-ASCII text (``彼は"テスト"と``).
                kind = None
            else:
                kind = not opened.get(b)
            st = opened.setdefault(b, [])
            if kind is True:
                # Remember whether the quote opened English text (ASCII on
                # both sides, like ``said "hello``).
                st.append(prev[:1] < "\x80" and nxt[0] < "\x80")
            elif kind is False and st:
                st.pop()
            kinds.append(kind)
        elif (b in _SENTENCE_END or b in _SPACES and prev in ".!?") and prev:
            # An English quote still open at the end of a sentence is taken
            # as unclosed (#60), so that ``He said "hello. 彼は"テスト"と``
            # does not flip the quotes inside the Japanese text.
            for st in opened.values():
                if st and any(st):
                    st[:] = [x for x in st if not x]
        prev = b
    return kinds


def _ruby_items(
    text: str, ambiguous_width: int, ruby_width: str
) -> Iterator[tuple[str, int, str, int]]:
    """``(cluster, width, base, base_width)`` for :func:`_atoms` with ruby."""
    for cl, w in _pieces(text, ambiguous_width, True, ruby_width):
        b = _base(cl)
        s = strip_ansi(cl) if "\x1b" in cl else cl
        if len(s) > 1 and s[0] in ("｜", "|") and "《" in s:
            b = s[1]  # explicit ruby unit: classify by its base text
        yield cl, w, b, char_width(b, ambiguous_width) if b else 0


def _glue(
    atoms: list[_Unit],
    hanging: bool,
    ambiguous_width: int,
    rules: KinsokuRules = _JA,
) -> list[_Unit]:
    """Merge atoms that must not be separated according to kinsoku rules."""
    units: list[_Unit] = []
    no_start = rules.no_start
    no_end = rules.no_end
    for a in atoms:
        if units and not a.space and not units[-1].space:
            prev = units[-1]
            if (
                a.glue_prev
                or prev.glue_next
                or _first(a.text) in no_start
                or _last(prev.text) in no_end
            ):
                prev.text += a.text
                prev.width += a.width
                prev.glue_next = a.glue_next
                continue
        units.append(_Unit(a.text, a.width, a.space, glue_next=a.glue_next))
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


def _split_prep(
    u: _Unit,
    ambiguous_width: int,
    ruby: bool = False,
    ruby_width: str = "full",
    rules: KinsokuRules = _JA,
) -> tuple[list[str], list[int], frozenset[int]]:
    """Clusters of ``u``, their widths and the indices no break may come
    before (next to a quote, #52), for :func:`_chunk_end`."""
    if ruby:
        pieces = list(_pieces(u.text, ambiguous_width, ruby, ruby_width))
        cls = [c for c, _ in pieces]
        ws = [w for _, w in pieces]
    else:
        cls = list(_clusters(u.text))
        ws = [width(c, ambiguous_width) for c in cls]
    if "ﾞ" in u.text or "ﾟ" in u.text:
        cls, ws = _join_sound_marks(cls, ws)
    nobreak: frozenset[int] = frozenset()
    qs = rules.quotes - rules.no_start - rules.no_end
    if qs and any(q in u.text for q in qs):
        kinds = iter(_quote_kinds(cls, False, qs, rules.no_start, rules.no_end))
        nb = set()
        for i, c in enumerate(cls):
            b = c if len(c) == 1 else _base(c)
            if b in qs:
                kind = next(kinds)
                if kind is not None:
                    nb.add(i + 1 if kind else i)
        nobreak = frozenset(nb)
    return cls, ws, nobreak


def _chunk_end(
    cls: list[str],
    ws: list[int],
    start: int,
    limit: int,
    rules: KinsokuRules = _JA,
    ruby: bool = False,
    nobreak: frozenset[int] = frozenset(),
) -> int:
    """End index of the hard-split chunk that starts at ``cls[start]``.

    Takes time proportional to the chunk, not to the rest of the word (#43).
    """
    no_start = rules.no_start
    no_end = rules.no_end

    def good_break(i: int) -> bool:
        # breaking before cls[i] respects kinsoku
        return (
            _first(cls[i]) not in no_start and _last(cls[i - 1]) not in no_end and i not in nobreak
        )

    n = len(cls)
    end, bw = start, 0
    while end < n and (end == start or bw + ws[end] <= limit):
        bw += ws[end]
        end += 1
    if end < n:
        # back off to the latest kinsoku-safe break inside this chunk
        for j in range(end, start, -1):
            if good_break(j):
                return j
        if ruby and end == start + 1 and _RUBY_RE.fullmatch(strip_ansi(cls[start])):
            # a lone, unbreakable ruby unit: let the line overflow
            # rather than push 。」 etc. to the start of the next line
            while end < n and not good_break(end):
                end += 1
    return end


def _split_long(
    u: _Unit,
    limit: int,
    ambiguous_width: int,
    rules: KinsokuRules = _JA,
    ruby: bool = False,
    ruby_width: str = "full",
) -> list[_Unit]:
    """Hard-split an over-long unit into chunks no wider than ``limit``.

    Ruby notations (``ruby=True``) are never split.
    """
    cls, ws, nobreak = _split_prep(u, ambiguous_width, ruby, ruby_width, rules)
    chunks: list[_Unit] = []
    start = 0
    n = len(cls)
    while start < n:
        end = _chunk_end(cls, ws, start, limit, rules, ruby, nobreak)
        chunks.append(_Unit("".join(cls[start:end]), sum(ws[start:end])))
        start = end
    return chunks


def _strip_wide_ruby(text: str, limit: int, aw: int, ruby_width: str) -> str:
    """Replace each ruby notation of ``text`` wider than ``limit`` by its base."""
    out: list[str] = []
    for cl, w in _pieces(text, aw, True, ruby_width):
        if w > limit and "《" in cl:
            cl = strip_ruby(cl)  # escapes around the notation are kept
        out.append(cl)
    return "".join(out)


def _unruby_wide(
    units: list[_Unit],
    limit: int,
    hanging: bool,
    keep_all: bool,
    aw: int,
    rules: KinsokuRules,
    ruby_width: str,
) -> list[_Unit]:
    """Make ruby notations that fit on no line breakable (#51).

    A ruby notation wider than ``limit`` (the widest line) cannot be kept
    whole without overflowing, so with ``break_long_words=True`` its ruby is
    dropped and the base text is wrapped like ordinary text.  Ruby cannot be
    re-attached to parts of the base: which reading belongs to which base
    character is unknown (``｜魔法少女《マジカルガール》``).
    """
    out: list[_Unit] = []
    for u in units:
        if u.space or u.width - u.hang <= limit or "《" not in u.text:
            out.append(u)
            continue
        text = _strip_wide_ruby(u.text, limit, aw, ruby_width)
        if text == u.text:
            out.append(u)
            continue
        out.extend(_glue(_atoms(text, aw, keep_all, rules, True, ruby_width), hanging, aw, rules))
    return out


def _join_sound_marks(cls: list[str], ws: list[int]) -> tuple[list[str], list[int]]:
    """Merge each halfwidth ﾞ / ﾟ into the preceding cluster."""
    out_c: list[str] = []
    out_w: list[int] = []
    for c, w in zip(cls, ws, strict=True):
        if out_c and _base(c) in _HW_SOUND:
            out_c[-1] += c
            out_w[-1] += w
        else:
            out_c.append(c)
            out_w.append(w)
    return out_c, out_w


def _wrap_line(
    line: str,
    first_width: int,
    rest_width: int,
    hanging: bool,
    break_long_words: bool,
    keep_all: bool,
    ambiguous_width: int,
    rules: KinsokuRules = _JA,
    ruby: bool = False,
    ruby_width: str = "full",
) -> list[str]:
    units = _glue(
        _atoms(line, ambiguous_width, keep_all, rules, ruby, ruby_width),
        hanging,
        ambiguous_width,
        rules,
    )
    if ruby and break_long_words and "《" in line:
        units = _unruby_wide(
            units,
            max(first_width, rest_width),
            hanging,
            keep_all,
            ambiguous_width,
            rules,
            ruby_width,
        )
    lines: list[str] = []
    cur: list[_Unit] = []
    cur_w = 0
    pending = ""  # escapes of dropped spaces at the start of a line
    lead = True  # cur holds only the paragraph's leading whitespace (#21)

    def limit() -> int:
        return rest_width if lines else first_width

    def escapes(t: str) -> str:
        # Whitespace dropped at a break keeps its escapes (#16).
        return "".join(_ANSI_RE.findall(t)) if "\x1b" in t else ""

    def flush() -> None:
        nonlocal cur, cur_w
        dropped = ""
        while cur and cur[-1].space:
            dropped = escapes(cur.pop().text) + dropped
        lines.append("".join(u.text for u in cur) + dropped)
        cur, cur_w = [], 0

    def drop_lead() -> None:
        # The leading whitespace leaves no room: drop it, keep its escapes.
        nonlocal cur, cur_w, pending
        pending = "".join(escapes(x.text) for x in cur) + pending
        cur, cur_w = [], 0

    i = 0
    while i < len(units):
        u = units[i]
        i += 1
        if u.space:
            if cur or lead:
                cur.append(u)
                cur_w += u.width
            else:
                pending += escapes(u.text)
            continue
        if pending:
            u = _Unit(pending + u.text, u.width, hang=u.hang)
            pending = ""
        if ruby and break_long_words and "《" in u.text and cur_w + u.width - u.hang > limit():
            # The width a ruby notation must fit in is that of the line it
            # lands on, after the indent and the leading whitespace (#59):
            # the current line if it holds only leading whitespace, else
            # the next one.  If it does not fit there, drop its ruby (#51).
            room = limit() if lead or not cur else rest_width
            if u.width - u.hang > room:
                text = _strip_wide_ruby(u.text, room, ambiguous_width, ruby_width)
                if text != u.text:
                    atoms = _atoms(text, ambiguous_width, keep_all, rules, True, ruby_width)
                    units[i:i] = _glue(atoms, hanging, ambiguous_width, rules)
                    continue
        if cur_w + u.width - u.hang <= limit():
            cur.append(u)
            cur_w += u.width
            lead = False
            continue
        if lead:
            lead = False
            avail = limit() - cur_w
            if cur and break_long_words and u.width - u.hang > limit() and avail >= 1:
                # an over-long word after the indent: split it into the rest
                pieces = _split_long(u, avail, ambiguous_width, rules, ruby, ruby_width)
                if len(pieces) >= 2 and pieces[0].width <= avail:
                    cur.append(pieces[0])
                    flush()
                    u = _Unit(
                        "".join(x.text for x in pieces[1:]),
                        sum(x.width for x in pieces[1:]),
                        hang=u.hang,
                    )
                else:
                    drop_lead()
            else:
                drop_lead()
            if pending:
                u = _Unit(pending + u.text, u.width, hang=u.hang)
                pending = ""
            if not lines and cur_w + u.width - u.hang <= limit():
                cur = [u]
                cur_w = u.width
                continue
        if cur:
            flush()
        if break_long_words and u.width - u.hang > limit():
            # Split the clusters once and walk them by index, so a long
            # word takes linear time (#43).
            cls, ws, nobreak = _split_prep(u, ambiguous_width, ruby, ruby_width, rules)
            n = len(cls)
            start = 0
            rest = u.width
            while rest - u.hang > limit():
                end = _chunk_end(cls, ws, start, limit(), rules, ruby, nobreak)
                if end >= n:
                    break
                lines.append("".join(cls[start:end]))
                if start == 0:
                    rest = sum(ws)
                rest -= sum(ws[start:end])
                start = end
            if start:
                u = _Unit("".join(cls[start:]), rest, hang=u.hang)
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
    max_lines: int | None = None,
    placeholder: str = "…",
    ambiguous_width: int = 1,
    rules: RulesLike = "ja",
    ansi_reflow: bool = False,
    ruby: bool = False,
    ruby_width: str = "full",
    tabsize: int = 8,
) -> list[str]:
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
    :param break_long_words: hard-split units wider than ``width``.  With
        ``ruby=True``, a ruby notation wider than every line loses its ruby
        and its base text is wrapped like ordinary text (#51).
    :param keep_all: only break at spaces, like CSS ``word-break: keep-all``
        (natural for Korean).
    :param max_lines: keep at most this many lines; if text is cut, the last
        line ends with ``placeholder``.  To make room for it, latin words are
        dropped whole, as in :mod:`textwrap`, and CJK text character by
        character; if nothing of the last line is left, the placeholder ends
        the previous line when it fits there, or stands on a line of its
        own.  A word that fills a line by itself, or the first word of the
        first line, is cut by characters instead, so some text always
        remains (textwrap would drop it).
    :param ambiguous_width: width of East Asian Ambiguous characters (1 or 2).
    :param rules: kinsoku rules: a preset name (``"ja"`` (default),
        ``"strict"``, ``"loose"``, ``"zh-hans"``, ``"zh-hant"``, ``"ko"``)
        or a :class:`KinsokuRules` instance.
    :param ansi_reflow: close active ANSI styling (SGR colors/attributes and
        OSC 8 links) at the end of each line and re-open it at the start of
        the next one, after the indent, so every line stands on its own.
    :param ruby: recognize ruby notation (``｜漢字《かんじ》`` / ``漢字《かんじ》``,
        青空文庫・なろう形式). The base text and its ruby form one unbreakable
        unit; kinsoku still applies around it.  A unit wider than every line
        is reduced to its base text when ``break_long_words=True``, and
        overflows when it is ``False``.
    :param ruby_width: how a ruby unit is measured when ``ruby=True``:
        ``"full"`` (default) counts the notation as displayed, including
        ``｜《》`` and the annotation; ``"base"`` counts only the base text
        (for output that is later rendered as real ruby).
    :param tabsize: tabs are expanded to spaces before wrapping, up to the
        next multiple of ``tabsize`` columns counted by display width from
        the start of each paragraph (wide characters count as 2; the indent
        is not counted).  :class:`KinsokuWrapper` expands tabs itself when
        ``expand_tabs=True`` (its default), with its own ``tabsize``; with
        ``expand_tabs=False`` any remaining tabs are expanded here with
        ``tabsize=8``.

    A grapheme cluster is never split, so one that is wider than the room on
    a line (a wide character such as ``"あ"`` with ``width=1``) is put on a
    line of its own, and that line is wider than ``width``:
    ``wrap("あいう", 1) == ["あ", "い", "う"]``.

    Whitespace at the start of a paragraph (e.g. a U+3000 字下げ or a code
    indent) is kept on its first line; it is dropped only when not even the
    first word fits after it.  Whitespace at a line break is dropped, but
    ANSI escapes attached to it stay at the end of the previous line.
    """
    _check_width(width)
    _check_ambiguous_width(ambiguous_width)
    rules = _resolve_rules(rules)
    iw = _w(initial_indent, ambiguous_width)
    sw = _w(subsequent_indent, ambiguous_width)
    if width - iw < 1 or width - sw < 1:
        raise ValueError("indent is as wide as or wider than width")
    if max_lines is not None and max_lines < 1:
        raise ValueError("max_lines must be >= 1")
    if ruby_width not in _RUBY_WIDTHS:
        raise ValueError("ruby_width must be 'base' or 'full'")

    # (indent, body) pairs; the indent stays outside any re-opened styling
    pairs: list[tuple[str, str]] = []
    for line in text.splitlines() or [""]:
        if "\t" in line:
            line = _expand_tabs(line, tabsize, ambiguous_width)
        wrapped = _wrap_line(
            line,
            width - iw,
            width - sw,
            hanging,
            break_long_words,
            keep_all,
            ambiguous_width,
            rules,
            ruby,
            ruby_width,
        )
        # an escape-only line is visually empty, like "": no indent (#34)
        first = wrapped[0]
        visible = strip_ansi(first) if "\x1b" in first else first
        pairs.append((initial_indent if visible else "", first))
        pairs.extend((subsequent_indent, line) for line in wrapped[1:])

    cut = max_lines is not None and len(pairs) > max_lines
    if cut:
        pairs = pairs[:max_lines]

    if not ansi_reflow:
        out = [i + b for i, b in pairs]
        if cut:
            body = _cut_for_placeholder(
                out[-1],
                width,
                placeholder,
                ambiguous_width,
                rules,
                ruby,
                ruby_width,
                pairs[-1][0],
                len(out) == 1,
            )
            if body is None:
                # nothing of the last line fits: like textwrap, end the
                # previous line with the placeholder if it fits there
                del out[-1]
                if out and _w(out[-1], ambiguous_width) + _w(placeholder, ambiguous_width) <= width:
                    out[-1] += _close_after("".join(out)) + placeholder
                else:
                    out.append(
                        _lone_placeholder(
                            pairs[-1][0], placeholder, width, ambiguous_width
                        ).replace("\0", _close_after("".join(out)))
                    )
                return out
            # close whatever is open at the cut (styling may come from
            # earlier lines, since they are printed one after another)
            out[-1] = body + _close_after("".join(out[:-1]) + body) + placeholder
        return out

    state = _AnsiState()
    out = []
    for k, (indent, body) in enumerate(pairs):
        if cut and k == len(pairs) - 1:
            start = state.copy()
            line = indent + (start.open() if body else "") + body
            kept = _cut_for_placeholder(
                line,
                width,
                placeholder,
                ambiguous_width,
                rules,
                ruby,
                ruby_width,
                indent,
                k == 0,
            )
            if kept is None:
                if out and _w(out[-1], ambiguous_width) + _w(placeholder, ambiguous_width) <= width:
                    out[-1] += placeholder  # the line is already closed
                else:
                    out.append(
                        _lone_placeholder(indent, placeholder, width, ambiguous_width).replace(
                            "\0", ""
                        )
                    )
                break
            if len(kept) < len(indent):  # the cut ate into the indent
                end = _AnsiState()
                end.feed_text(kept)
            else:
                end = start
                end.feed_text(kept[len(indent) :])
            out.append(kept + end.close() + placeholder)
        else:
            out.append(indent + _reflow_body(body, state))
    return out


def _lone_placeholder(indent: str, placeholder: str, width_: int, aw: int) -> str:
    """A last line holding only the placeholder (``"\\0"`` marks where to
    close styling)."""
    ph = placeholder.lstrip()
    if _w(indent + ph, aw) <= width_:
        return indent + "\0" + ph
    return "\0" + ph


def _is_word(text: str, aw: int) -> bool:
    """Whether ``text`` is made only of narrow characters (a latin word)."""
    v = strip_ansi(text) if "\x1b" in text else text
    return all(_char_width(c, aw) == 1 and not "\uff61" <= c <= "\uff9f" for c in v)


def _cut_units(text: str, aw: int, rules: KinsokuRules, ruby: bool, ruby_width: str) -> list[_Unit]:
    """Units the placeholder cut drops one at a time.

    A latin word (a run of narrow characters, with the punctuation attached
    to it, like a :mod:`textwrap` chunk) is one unit; a wide character, a
    halfwidth kana and a ruby notation are units of their own; spaces are
    separate units.
    """
    out: list[_Unit] = []
    prev_word = False
    for a in _atoms(text, aw, False, rules, ruby, ruby_width):
        word = not a.space and _is_word(a.text, aw)
        if word and prev_word:
            out[-1].text += a.text
            out[-1].width += a.width
        else:
            out.append(_Unit(a.text, a.width, a.space))
        prev_word = word
    return out


def _visible(text: str) -> bool:
    return bool((strip_ansi(text) if "\x1b" in text else text).strip())


def _cut_for_placeholder(
    line: str,
    width_: int,
    placeholder: str,
    aw: int,
    rules: KinsokuRules = _JA,
    ruby: bool = False,
    ruby_width: str = "full",
    indent: str = "",
    alone: bool = True,
) -> str | None:
    """Cut ``line`` so that ``placeholder`` can follow it within ``width_``.

    ``line`` starts with ``indent``, which is kept.  The rest is shortened
    unit by unit (see :func:`_cut_units`), like :mod:`textwrap` drops whole
    words.  If that leaves nothing of the text and the first word is too
    long (it reaches ``width_`` on its own), or this is the only line
    (``alone``), it is cut cluster by cluster instead, with ruby notations
    reduced to their base text, so some text always remains (#50, #51).
    Otherwise ``None`` is returned: the caller then puts the placeholder at
    the end of the previous line or on a line of its own, as textwrap does.
    """
    pw = _w(placeholder, aw)
    if pw > width_:
        raise ValueError("placeholder is wider than width")
    body = line[len(indent) :]
    budget = width_ - pw - _w(indent, aw)
    no_end = _first(placeholder) in rules.no_start
    units = _cut_units(body, aw, rules, ruby, ruby_width)
    kept = list(units)
    total = sum(u.width for u in kept)
    while kept and (
        total > budget or kept[-1].space or no_end and _last(kept[-1].text) in rules.no_end
    ):
        total -= kept.pop().width
    if any(not u.space and _visible(u.text) for u in kept):
        return indent + "".join(u.text for u in kept)

    # nothing fits word by word
    first = next((u for u in units if not u.space and _visible(u.text)), None)
    if first is None:
        return None
    reach = _w(indent, aw)
    for u in units:
        reach += u.width
        if u is first:
            break
    if not (alone or reach >= width_ or not _is_word(first.text, aw)):
        return None
    if ruby and "《" in body:
        body = strip_ruby(body)
    pieces = list(_pieces(body, aw))
    if "ﾞ" in body or "ﾟ" in body:
        cls, ws = _join_sound_marks([c for c, _ in pieces], [w for _, w in pieces])
        pieces = list(zip(cls, ws, strict=True))
    total = sum(w for _, w in pieces)
    while pieces and (
        total > budget
        or _first(pieces[-1][0]) in _SPACES
        or no_end
        and _first(pieces[-1][0]) in rules.no_end
    ):
        total -= pieces.pop()[1]
    kept_text = "".join(c for c, _ in pieces)
    if not _visible(kept_text):
        return None
    return indent + kept_text


def fill(text: str, width: int = 70, **kwargs: Any) -> str:
    """Like :func:`wrap` but return a single string joined by newlines."""
    return "\n".join(wrap(text, width, **kwargs))


def shorten(text: str, width: int, placeholder: str = "…", **kwargs: Any) -> str:
    """Wrap ``text`` and keep only what fits on one line (like textwrap.shorten,
    but whitespace is not collapsed and kinsoku is respected)."""
    return wrap(text, width, max_lines=1, placeholder=placeholder, **kwargs)[0]


def truncate(
    text: str,
    width: int,
    placeholder: str = "…",
    *,
    ambiguous_width: int = 1,
    tabsize: int = 8,
) -> str:
    """Cut ``text`` to fit in ``width`` columns, appending ``placeholder``.

    ANSI escape sequences are kept intact.  If the text is cut while SGR
    attributes or an OSC 8 hyperlink are active, they are closed (the link
    with its original BEL or ST terminator) before the placeholder; nothing
    is added when nothing is open.

    Tabs are expanded to spaces first, the same way :func:`width` counts
    them (up to the next multiple of ``tabsize`` columns), so the result
    contains no tabs.  A grapheme cluster is never split: if the next one
    does not fit before the placeholder, it is left out whole.

    :raises ValueError: if ``width`` is negative, ``ambiguous_width`` is not
        1 or 2, or the text must be cut and ``placeholder`` is wider than
        ``width``.
    """
    _check_width(width, allow_zero=True)
    _check_ambiguous_width(ambiguous_width)
    if "\t" in text:
        text = _expand_tabs(text, tabsize, ambiguous_width)
    if _w(text, ambiguous_width) <= width:
        return text
    pw = _w(placeholder, ambiguous_width)
    if pw > width:
        raise ValueError("placeholder is wider than width")
    parts: list[str] = []
    bw = 0
    for cl in _clusters(text):
        cw = _w(cl, ambiguous_width)
        if bw + cw > width - pw:
            break
        parts.append(cl)
        bw += cw
    buf = "".join(parts)
    return buf + _close_after(buf) + placeholder


def pad(
    text: str,
    width: int,
    align: Align = "left",
    fillchar: str = " ",
    *,
    ambiguous_width: int = 1,
    tabsize: int = 8,
) -> str:
    """Pad ``text`` with ``fillchar`` to ``width`` display columns.

    :param align: ``"left"`` (default), ``"right"`` or ``"center"``; also
        ``"<"``, ``">"`` and ``"^"`` as in :func:`format`.  It is checked
        even when no padding is needed.
    :param fillchar: a character of display width 1.
    :param tabsize: tabs are expanded to spaces first, the same way
        :func:`width` counts them, so the result contains no tabs.

    ``text`` that is already ``width`` columns or wider is returned as it
    is (with tabs expanded), not cut; use :func:`truncate` first to make it
    fit, e.g. ``pad(truncate(s, 10), 10)``.

    :raises ValueError: if ``width`` is negative, ``align`` is unknown,
        ``ambiguous_width`` is not 1 or 2, or ``fillchar`` is not 1 column.
    """
    _check_width(width, allow_zero=True)
    align = _check_align(align)
    _check_ambiguous_width(ambiguous_width)
    if _w(fillchar, ambiguous_width) != 1:
        raise ValueError("fillchar must have display width 1")
    if "\t" in text:
        text = _expand_tabs(text, tabsize, ambiguous_width)
    gap = width - _w(text, ambiguous_width)
    if gap <= 0:
        return text
    if align == "left":
        return text + fillchar * gap
    if align == "right":
        return fillchar * gap + text
    left = gap // 2
    return fillchar * left + text + fillchar * (gap - left)


_w = width
