"""kinsoku: Japanese/CJK-aware text wrapping with 禁則処理 (kinsoku shori)."""

from ._core import (
    HANGABLE,
    NO_END,
    NO_START,
    char_width,
    fill,
    pad,
    shorten,
    strip_ansi,
    truncate,
    width,
    wrap,
)
from .wrapper import KinsokuWrapper, dedent, indent

__all__ = [
    "HANGABLE",
    "NO_END",
    "NO_START",
    "char_width",
    "fill",
    "pad",
    "shorten",
    "strip_ansi",
    "truncate",
    "width",
    "wrap",
    "KinsokuWrapper",
    "dedent",
    "indent",
]
__version__ = "0.2.0"
