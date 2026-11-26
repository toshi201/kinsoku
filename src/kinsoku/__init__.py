"""kinsoku: Japanese/CJK-aware text wrapping with 禁則処理 (kinsoku shori)."""

from ._core import (
    HANGABLE,
    NO_END,
    NO_START,
    PRESETS,
    KinsokuRules,
    ansi_reflow,
    char_width,
    fill,
    pad,
    ruby_to_html,
    shorten,
    strip_ansi,
    strip_ruby,
    truncate,
    width,
    wrap,
)
from .table import table
from .tategaki import tategaki
from .unwrap import rewrap, unwrap
from .wrapper import KinsokuWrapper, dedent, indent

__all__ = [
    "HANGABLE",
    "KinsokuRules",
    "NO_END",
    "NO_START",
    "PRESETS",
    "ansi_reflow",
    "char_width",
    "fill",
    "pad",
    "rewrap",
    "ruby_to_html",
    "shorten",
    "strip_ansi",
    "strip_ruby",
    "table",
    "truncate",
    "unwrap",
    "width",
    "wrap",
    "KinsokuWrapper",
    "dedent",
    "indent",
    "tategaki",
]
__version__ = "0.3.0"
