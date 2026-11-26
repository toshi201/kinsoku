"""Undo hard wrapping: join wrapped lines back into paragraphs (``unwrap``)
and wrap them again at another width (``rewrap``)."""

from __future__ import annotations

import re
import unicodedata

from ._core import _ANSI_RE, NO_END, NO_START, char_width, strip_ansi, wrap

__all__ = ["unwrap", "rewrap"]

# A line plus its terminator (\r\n, \r or \n; empty for the last line).
_LINE_RE = re.compile(r"([^\r\n]*)(\r\n|\r|\n|$)")

# Lines that look like list items always start a new paragraph.
_LIST_RE = re.compile(r"[ \t　]*(?:[-*+•][ \t]|・|[0-9]+[.)][ \t])")

# Ambiguous-width punctuation used in both Japanese and English text: the
# junction is classified by the nearest other visible character instead.
_NEUTRAL = frozenset("…‥―─")

_HALF_SPACES = " \t"


def _split_lines(text: str) -> list[tuple[str, str]]:
    lines = []
    for m in _LINE_RE.finditer(text):
        body, term = m.group(1), m.group(2)
        if not body and not term:
            if m.start() == len(text):
                break
            continue
        lines.append((body, term))
    return lines


def _tokens(s: str) -> list[str]:
    """Split ``s`` into single characters and whole ANSI escape sequences."""
    out: list[str] = []
    pos = 0
    while pos < len(s):
        m = _ANSI_RE.match(s, pos) if s[pos] == "\x1b" else None
        if m:
            out.append(m.group())
            pos = m.end()
        else:
            out.append(s[pos])
            pos += 1
    return out


def _is_esc(tok: str) -> bool:
    return len(tok) > 1


def _rstrip_visible(s: str) -> str:
    """Remove trailing whitespace, keeping ANSI escapes that follow it."""
    toks = _tokens(s)
    kept: list[str] = []
    while toks and (_is_esc(toks[-1]) or toks[-1].isspace()):
        t = toks.pop()
        if _is_esc(t):
            kept.append(t)
    return "".join(toks) + "".join(reversed(kept))


def _lstrip_half(s: str) -> str:
    """Remove leading half-width spaces/tabs, keeping ANSI escapes before them."""
    toks = _tokens(s)
    kept: list[str] = []
    i = 0
    while i < len(toks) and (_is_esc(toks[i]) or toks[i] in _HALF_SPACES):
        if _is_esc(toks[i]):
            kept.append(toks[i])
        i += 1
    return "".join(kept) + "".join(toks[i:])


def _is_wide(c: str) -> bool:
    cp = ord(c)
    return char_width(c) >= 2 or 0xFF61 <= cp <= 0xFF9F  # incl. half-width kana


def _is_cjk_punct(c: str) -> bool:
    if c == "　" or c in "ー々〆〻":
        return True
    if c in NO_START or c in NO_END or unicodedata.category(c).startswith("P"):
        return _is_wide(c)
    return False


def _pick(visible: str, reverse: bool) -> str:
    """The character deciding a junction: skip neutral punctuation if possible."""
    chars = visible[::-1] if reverse else visible
    for c in chars:
        if c not in _NEUTRAL:
            return c
    return chars[:1]


def _is_latin_letter(c: str) -> bool:
    return c.isalpha() and "LATIN" in unicodedata.name(c, "")


def _is_hangul(c: str) -> bool:
    cp = ord(c)
    return (
        0x1100 <= cp <= 0x11FF
        or 0x3130 <= cp <= 0x318F
        or 0xA960 <= cp <= 0xA97F
        or 0xAC00 <= cp <= 0xD7FF
        or 0xFFA0 <= cp <= 0xFFDC
    )


def _separator(left: str, right: str, cjk_latin_space: bool = False) -> str:
    """Return "" or " " to put between two joined lines (both already stripped)."""
    lv, rv = strip_ansi(left), strip_ansi(right)
    if not lv or not rv:
        return ""
    # Hyphenated line end: keep the hyphen, join without a space.
    if lv[-1] == "-" and len(lv) >= 2 and _is_latin_letter(lv[-2]):
        return ""
    lc, rc = _pick(lv, True), _pick(rv, False)
    if _is_cjk_punct(lc) or _is_cjk_punct(rc):
        return ""
    lw, rw = _is_wide(lc), _is_wide(rc)
    if lw and rw:
        return ""
    # CJK next to latin/digits: Japanese text usually has no space there
    # (CSS Text 3 segment break rules). Hangul uses spaces between words.
    if not cjk_latin_space and ((lw and not _is_hangul(lc)) or (rw and not _is_hangul(rc))):
        return ""
    return " "


def _is_blank(body: str) -> bool:
    return not strip_ansi(body).strip()


def _starts_paragraph(body: str, indent_marks_paragraph: bool) -> bool:
    v = strip_ansi(body)
    if _LIST_RE.match(v):
        return True
    return indent_marks_paragraph and v[:1] in (" ", "\t", "　")


def _paragraphs(text: str, indent_marks_paragraph: bool, cjk_latin_space: bool = False):
    """Yield ``(is_blank, joined_body, terminator)`` for each output line."""
    cur: str | None = None
    term = ""
    for body, t in _split_lines(text):
        if _is_blank(body):
            if cur is not None:
                yield False, cur, term
                cur = None
            yield True, body, t
        elif cur is None or _starts_paragraph(body, indent_marks_paragraph):
            if cur is not None:
                yield False, cur, term
            cur, term = _rstrip_visible(body), t
        else:
            nxt = _lstrip_half(body)
            cur = cur + _separator(cur, nxt, cjk_latin_space) + _rstrip_visible(nxt)
            term = t
    if cur is not None:
        yield False, cur, term


def unwrap(
    text: str, *, indent_marks_paragraph: bool = False, cjk_latin_space: bool = False
) -> str:
    """Join hard-wrapped lines back into one line per paragraph.

    Blank (whitespace-only) lines separate paragraphs and are kept exactly,
    as are the line terminators (``\\n``, ``\\r\\n``) that remain. Inside a
    paragraph, trailing whitespace of a line and leading half-width spaces
    of the next line are removed, then the lines are joined:

    - with no space when the characters on both sides are wide (CJK), or
      either side is CJK punctuation or a bracket (``。」（`` ...);
    - with no space when one side is wide (CJK, except Hangul) and the other
      is latin text or digits (``"Python\\nを使う"`` -> ``"Pythonを使う"``),
      unless ``cjk_latin_space=True``;
    - with one space otherwise (wrapped English text, Hangul next to latin);
    - with no space after a hyphen that follows a latin letter, keeping the
      hyphen (``"well-\\nknown"`` -> ``"well-known"``). Hyphens are never
      removed, because a line-end hyphen cannot be told apart from a real one.

    Lines that look like list items (``- ``, ``* ``, ``・``, ``1. `` ...)
    always start a new paragraph. ANSI escape sequences are ignored when
    classifying characters and kept in the output.

    :param indent_marks_paragraph: a line starting with U+3000 or half-width
        spaces starts a new paragraph (its indent is kept).
    :param cjk_latin_space: put one space where a CJK character meets latin
        text or digits at a line break (the old default; it adds spaces
        that ``fill`` did not remove, so the round trip is not exact).
    """
    out: list[str] = []
    for _, body, term in _paragraphs(text, indent_marks_paragraph, cjk_latin_space):
        out.append(body + term)
    return "".join(out)


def _leading_space(s: str) -> tuple[str, str]:
    n = len(s) - len(s.lstrip(" \t　"))
    return s[:n], s[n:]


def rewrap(
    text: str,
    width: int = 70,
    *,
    indent_marks_paragraph: bool = False,
    cjk_latin_space: bool = False,
    **wrap_kwargs,
) -> str:
    """:func:`unwrap` ``text``, then wrap every paragraph to ``width`` columns.

    Blank lines are kept. A paragraph's own leading indentation (e.g. a
    U+3000 kept by ``indent_marks_paragraph=True``) is preserved and added to
    ``initial_indent``. ``cjk_latin_space`` is passed to :func:`unwrap`.
    Other keyword arguments are passed to :func:`wrap`;
    ``max_lines`` limits the whole output, like in :func:`wrap`.
    """
    max_lines = wrap_kwargs.pop("max_lines", None)
    placeholder = wrap_kwargs.pop("placeholder", "…")
    initial_indent = wrap_kwargs.pop("initial_indent", "")
    # validate the arguments even when the text is empty
    wrap(
        "",
        width,
        initial_indent=initial_indent,
        max_lines=max_lines,
        placeholder=placeholder,
        **wrap_kwargs,
    )
    nl = "\r\n" if "\r\n" in text else "\n"

    items = list(_paragraphs(text, indent_marks_paragraph, cjk_latin_space))
    lines: list[str] = []
    for i, (blank, body, _term) in enumerate(items):
        lead, rest = ("", "") if blank else _leading_space(body)

        # wrapped() is only called within this iteration, so the late binding is fine
        def wrapped(extra: str = "", **kw) -> list[str]:
            return wrap(
                rest + extra,  # noqa: B023
                width,
                initial_indent=initial_indent + lead,  # noqa: B023
                **wrap_kwargs,
                **kw,
            )

        new = [body] if blank else wrapped()
        if max_lines is not None and (
            len(lines) + len(new) > max_lines
            or len(lines) + len(new) == max_lines
            and i < len(items) - 1
        ):
            # Let wrap() cut and add the placeholder: the dummy extra line
            # guarantees the cut happens inside this paragraph.
            lines.extend(wrapped("\n.", max_lines=max_lines - len(lines), placeholder=placeholder))
            break
        lines.extend(new)
    out = nl.join(lines)
    if items and items[-1][2]:
        out += nl
    return out
