"""Balanced line breaking (``wrap(..., balance=True)``, #76).

The greedy wrapper fills each line as far as it goes, which can leave a
very short last line.  :func:`balance_breaks` instead picks, by dynamic
programming, the breaks that keep the greedy number of lines and make the
lines as even as possible.

It works on the kinsoku units of one paragraph (what :func:`kinsoku._core._glue`
makes) and knows only their widths, hangs and whether they are spaces, so
the set of places a line may break is the same as for the greedy wrapper.
"""

from __future__ import annotations

from collections.abc import Sequence

#: Paragraphs with more units than this are wrapped greedily.
MAX_UNITS = 2000


def balance_breaks(
    widths: Sequence[int],
    hangs: Sequence[int],
    spaces: Sequence[bool],
    first_width: int,
    rest_width: int,
) -> list[int] | None:
    """Indices of the units that start lines 2, 3, ... of a balanced layout.

    A line may break before any visible non-space unit that has a non-space
    unit before it; whitespace before the break is dropped, as in the greedy
    wrapper.  A line holding units ``s .. t`` (``t`` the last non-space)
    fits when ``sum(widths[s..t]) - hangs[t]`` is at most its width
    (``first_width`` for the first line, ``rest_width`` after).

    Among the layouts with the fewest lines, the one with the smallest sum
    of ``(line width - used width) ** 2`` over *all* lines, the last one
    included, is chosen.  Leaving the last line out would let it be as
    short as it likes, which is what the greedy wrapper already does; with
    it, the slack is spread over every line.  Ties go to the layout with
    the longer earlier lines.

    Returns ``None`` if the units cannot be laid out that way (a unit
    wider than its line); the caller then wraps greedily.
    """
    n = len(widths)
    prefix = [0] * (n + 1)
    for i, w in enumerate(widths):
        prefix[i + 1] = prefix[i] + w
    # last[e]: index of the last non-space unit before e (-1 if none)
    last = [-1] * (n + 1)
    for i in range(n):
        last[i + 1] = last[i] if spaces[i] else i
    # line starts: 0, then each breakable position, in order
    starts = [0]
    for k in range(1, n):
        if not spaces[k] and widths[k] > 0 and last[k] >= 0:
            starts.append(k)
    ends = starts[1:] + [n]
    widest = max(first_width, rest_width)

    # The best layout of the units before starts[i] is scored by one integer,
    # lines * big + cost, so that fewer lines always win; -1: no layout.
    big = (widest + 1) ** 2 * (n + 1) + 1
    score = [-1] * (len(starts) + 1)
    score[0] = 0
    back = [0] * (len(starts) + 1)
    pre = [prefix[s] for s in starts]
    for j, e in enumerate(ends):
        t = last[e]
        if t < 0:
            return None
        used_end = prefix[t + 1] - hangs[t]
        cur = -1
        arg = -1
        # starts[j] is the latest start before e
        for i in range(j, -1, -1):
            used = used_end - pre[i]
            if used > widest:
                break
            sc = score[i]
            if sc < 0:
                continue
            limit = rest_width if i else first_width
            if used > limit:
                continue
            slack = limit - used
            cand = sc + big + slack * slack
            if cur < 0 or cand < cur:
                cur, arg = cand, i
        score[j + 1] = cur
        back[j + 1] = arg
    if score[-1] < 0:
        return None
    breaks: list[int] = []
    k = len(starts)
    while True:
        k = back[k]
        if not k:
            break
        breaks.append(starts[k])
    breaks.reverse()
    return breaks
