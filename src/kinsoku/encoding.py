"""Guess the encoding of Japanese text: UTF-8, UTF-16/32 (with BOM), cp932, EUC-JP.

No external libraries are used. The steps are:

1. a byte order mark (UTF-8, UTF-16, UTF-32)
2. strict UTF-8
3. cp932 and EUC-JP: whichever decodes; if both do, the one whose text
   looks more like Japanese prose (see :func:`_score`)
"""

from __future__ import annotations

import codecs

__all__ = ["detect_encoding"]

# Longest BOMs first: the UTF-32-LE BOM starts with the UTF-16-LE one.
_BOMS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)

# Tried in this order; on a tie the first one wins (cp932 is the more
# common of the two, e.g. Aozora Bunko texts).
_LEGACY = ("cp932", "euc-jp")

# What cp932 makes of the bytes 0x80, 0xA0, 0xFD-0xFF, which are not
# characters in Shift_JIS: their presence means the input is not cp932.
_CP932_JUNK = frozenset("\x80\uf8f0\uf8f1\uf8f2\uf8f3")

_JA_PUNCT = frozenset("、。，．・「」『』（）【】〈〉《》〔〕〜ー…―‥々〆〃　！？：；")


def _kanji_score(ch: str) -> float:
    """JIS X 0208 level 1 kanji (the common ones, close to the jōyō list)
    score high; level 2 a little; anything outside JIS X 0208 (vendor
    extensions, JIS X 0212) counts against the guess."""
    try:
        b = ch.encode("euc-jp")
    except UnicodeEncodeError:
        return -1.0
    if len(b) != 2:
        return -1.0  # 3-byte JIS X 0212
    return 1.5 if 0xB0 <= b[0] <= 0xCF else 0.25


def _score(text: str) -> float:
    """How much ``text`` looks like Japanese prose (higher is better)."""
    s = 0.0
    for ch in text:
        o = ord(ch)
        if o < 0x80:
            if ch.isprintable() or ch in "\t\n\r":
                continue  # ASCII is neutral: it decodes the same either way
            s -= 2.0  # other control characters
        elif 0x3041 <= o <= 0x3096 or 0x30A1 <= o <= 0x30FA:
            s += 2.0  # hiragana, katakana
        elif ch in _JA_PUNCT:
            s += 1.5
        elif 0x4E00 <= o <= 0x9FFF:
            s += _kanji_score(ch)
        elif 0xFF61 <= o <= 0xFF9F:
            s -= 0.5  # half-width katakana: what EUC-JP bytes look like as cp932
        elif 0xFF01 <= o <= 0xFF5E:
            s += 0.5  # full-width ASCII
        elif 0xE000 <= o <= 0xF8FF or 0x80 <= o < 0xA0:
            s -= 3.0  # private use area, C1 controls
        else:
            s -= 1.0
    return s


def _decode_auto(data: bytes) -> tuple[str, str]:
    """Decode ``data`` with the detected encoding: ``(text, encoding)``.

    Raises :class:`UnicodeDecodeError` when no candidate decodes it.
    """
    for bom, enc in _BOMS:
        if data.startswith(bom):
            return data.decode(enc), enc
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError as e:
        utf8_error = e
    best: tuple[float, str, str] | None = None
    for enc in _LEGACY:
        try:
            text = data.decode(enc)
        except UnicodeDecodeError:
            continue
        if enc == "cp932" and not _CP932_JUNK.isdisjoint(text):
            continue
        score = _score(text)
        if best is None or score > best[0]:
            best = (score, text, enc)
    if best is None:
        raise UnicodeDecodeError(
            "auto",
            data,
            utf8_error.start,
            utf8_error.end,
            "not UTF-8, cp932 or EUC-JP",
        )
    return best[1], best[2]


def detect_encoding(data: bytes) -> str:
    """Guess the encoding of ``data`` (Japanese text).

    Returns a codec name to pass to :meth:`bytes.decode`: ``"utf-8-sig"``,
    ``"utf-16"`` or ``"utf-32"`` when there is a BOM (these codecs drop
    it), else ``"utf-8"``, ``"cp932"`` or ``"euc-jp"``. Empty and ASCII-only
    input is ``"utf-8"``.

    >>> detect_encoding("吾輩は猫である。".encode("cp932"))
    'cp932'

    Raises :class:`UnicodeDecodeError` when the bytes are none of these.
    Very short input can be guessed wrong.
    """
    return _decode_auto(data)[1]
