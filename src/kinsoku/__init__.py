"""kinsoku: Japanese/CJK-aware text wrapping with 禁則処理 (kinsoku shori)."""

from ._core import (
    HANGABLE,
    NO_END,
    NO_START,
    char_width,
    fill,
    pad,
    truncate,
    width,
    wrap,
)

__all__ = [
    "HANGABLE",
    "NO_END",
    "NO_START",
    "char_width",
    "fill",
    "pad",
    "truncate",
    "width",
    "wrap",
]
__version__ = "0.1.0"
