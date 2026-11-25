"""kinsoku: Japanese/CJK-aware text wrapping with 禁則処理 (kinsoku shori)."""

from ._core import (
    HANGABLE,
    KinsokuRules,
    NO_END,
    NO_START,
    PRESETS,
    char_width,
    fill,
    pad,
    shorten,
    strip_ansi,
    truncate,
    width,
    wrap,
)
from .tategaki import tategaki
from .wrapper import KinsokuWrapper, dedent, indent

__all__ = [
    "HANGABLE",
    "KinsokuRules",
    "NO_END",
    "NO_START",
    "PRESETS",
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
    "tategaki",
]
__version__ = "0.2.0"
