"""A drop-in replacement for :class:`textwrap.TextWrapper` with kinsoku shori.

``KinsokuWrapper`` accepts every constructor argument of
:class:`textwrap.TextWrapper`, but measures lines in terminal display columns
and applies Japanese line-breaking rules by delegating to :func:`kinsoku.wrap`.

Differences from :class:`textwrap.TextWrapper`:

* ``expand_tabs`` / ``tabsize``: tabs are expanded by *display columns*, so a
  tab after ``"日本"`` (4 columns) advances to column 8, not to column 2.
* ``replace_whitespace`` (default ``True``): like textwrap, every ``\\t \\n \\v
  \\f \\r`` becomes a space, so newlines no longer act as paragraph breaks.
  Pass ``replace_whitespace=False`` to keep each input line as a paragraph
  (the behaviour of :func:`kinsoku.wrap`).
* ``drop_whitespace``: kinsoku always strips whitespace at break points, so
  ``drop_whitespace=False`` is accepted but has no effect.
* ``fix_sentence_endings`` and ``break_on_hyphens`` are accepted and ignored
  (they are rules for English text; kinsoku never breaks inside a latin
  word unless ``break_long_words`` forces it).
* ``placeholder`` keeps textwrap's default ``" [...]"`` for compatibility;
  ``"…"`` usually looks nicer for CJK text.  When ``max_lines`` cuts text,
  the last line is shortened cluster by cluster, not word by word.

Kinsoku-specific keyword-only options (``hanging``, ``keep_all``,
``ambiguous_width``) and any other keyword arguments (``**extra``) are passed
through to :func:`kinsoku.wrap`.
"""

from __future__ import annotations

import textwrap
from typing import Any, List, Optional

from ._core import _check_ambiguous_width, _check_width, _expand_tabs
from ._core import width as _width
from ._core import wrap as _wrap

__all__ = ["KinsokuWrapper", "dedent", "indent"]

dedent = textwrap.dedent
indent = textwrap.indent

_WHITESPACE_TRANS = {ord(c): " " for c in "\t\n\x0b\x0c\r"}


class KinsokuWrapper(textwrap.TextWrapper):
    """:class:`textwrap.TextWrapper` compatible wrapper with kinsoku shori.

    All attributes are plain and may be changed after construction::

        w = KinsokuWrapper(width=40, placeholder="…")
        w.width = 20
        w.hanging = True
        print(w.fill(text))

    Extra keyword arguments are stored in :attr:`extra` and forwarded to
    :func:`kinsoku.wrap` unchanged.
    """

    def __init__(
        self,
        width: int = 70,
        initial_indent: str = "",
        subsequent_indent: str = "",
        expand_tabs: bool = True,
        replace_whitespace: bool = True,
        fix_sentence_endings: bool = False,
        break_long_words: bool = True,
        drop_whitespace: bool = True,
        break_on_hyphens: bool = True,
        tabsize: int = 8,
        *,
        max_lines: Optional[int] = None,
        placeholder: str = " [...]",
        hanging: bool = False,
        keep_all: bool = False,
        ambiguous_width: int = 1,
        **extra: Any,
    ) -> None:
        super().__init__(
            width=width,
            initial_indent=initial_indent,
            subsequent_indent=subsequent_indent,
            expand_tabs=expand_tabs,
            replace_whitespace=replace_whitespace,
            fix_sentence_endings=fix_sentence_endings,
            break_long_words=break_long_words,
            drop_whitespace=drop_whitespace,
            break_on_hyphens=break_on_hyphens,
            tabsize=tabsize,
            max_lines=max_lines,
            placeholder=placeholder,
        )
        self.hanging = hanging
        self.keep_all = keep_all
        self.ambiguous_width = ambiguous_width
        self.extra = dict(extra)

    def _munge_whitespace(self, text: str) -> str:
        if self.expand_tabs:
            text = _expand_tabs(text, self.tabsize, self.ambiguous_width)
        if self.replace_whitespace:
            text = text.translate(_WHITESPACE_TRANS)
        return text

    def wrap(self, text: str) -> List[str]:
        """Wrap ``text`` and return a list of lines without final newlines.

        Like textwrap, an empty or whitespace-only ``text`` gives ``[]``.
        ``width`` and ``ambiguous_width`` are checked first, even then, with
        the same ValueError as :func:`kinsoku.wrap`.
        """
        _check_width(self.width)
        _check_ambiguous_width(self.ambiguous_width)
        text = self._munge_whitespace(text)
        if not text.strip():
            return []
        initial_indent = self.initial_indent
        if "\n" not in text and "\r" not in text:
            # Single paragraph: keep leading whitespace like textwrap does
            # (kinsoku.wrap may drop it) by moving it into the indent.  The
            # body passed on never starts with spaces, so this works whether
            # or not kinsoku.wrap keeps them itself.
            body = text.lstrip(" ")
            lead = text[: len(text) - len(body)]
            if lead and self._keep_lead(initial_indent, lead, body):
                initial_indent += lead
            text = body
        return _wrap(
            text,
            self.width,
            initial_indent=initial_indent,
            subsequent_indent=self.subsequent_indent,
            hanging=self.hanging,
            break_long_words=self.break_long_words,
            keep_all=self.keep_all,
            max_lines=self.max_lines,
            placeholder=self.placeholder,
            ambiguous_width=self.ambiguous_width,
            **self.extra,
        )

    def _first_word_fits(self, indent: str, body: str) -> bool:
        """Whether the first word of ``body`` fits on a line after ``indent``."""
        word = body.split(" ", 1)[0]
        kw = dict(self.extra)
        kw.update(hanging=self.hanging, keep_all=self.keep_all,
                  ambiguous_width=self.ambiguous_width, break_long_words=False)
        first = _wrap(word, self.width, initial_indent=indent, **kw)[0]
        return _width(first, self.ambiguous_width) <= self.width

    def _keep_lead(self, indent: str, lead: str, body: str) -> bool:
        """Decide whether the leading whitespace ``lead`` moves into the indent.

        Like textwrap, it is kept unless it would push a first word that
        otherwise fits onto a forced break; then it is dropped (#31).
        """
        if _width(indent + lead, self.ambiguous_width) >= self.width:
            return False
        if self._first_word_fits(indent + lead, body):
            return True
        # the word does not fit even without the lead: textwrap keeps the
        # lead when it breaks the word anyway, and drops it otherwise
        return self.break_long_words and not self._first_word_fits(indent, body)

    def fill(self, text: str) -> str:
        """Wrap ``text`` and return a single string joined by newlines."""
        return "\n".join(self.wrap(text))
