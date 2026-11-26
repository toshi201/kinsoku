"""Linear-time hard splitting (#43) and ASCII quotes in CJK text (#52)."""

import base64
import random
import time

import pytest

from kinsoku import PRESETS, KinsokuRules, wrap
from kinsoku.cli import main

ALL = tuple(PRESETS)

# Generous: the fixed code takes ~0.1 s for these, the old one ~60 s.
LIMIT = 10.0


def _timed(fn):
    t0 = time.perf_counter()
    result = fn()
    return result, time.perf_counter() - t0


# --- #43: long words without spaces ------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "a" * 200_000,
        base64.b64encode(random.Random(43).randbytes(150_000)).decode(),
        "á" * 50_000,  # combining-free, but non-ASCII
        "á" * 50_000,  # base + combining mark clusters
    ],
    ids=["ascii", "base64", "latin1", "combining"],
)
def test_long_word_is_fast(text):
    lines, t = _timed(lambda: wrap(text, 76))
    assert t < LIMIT, f"wrap took {t:.1f}s"
    assert "".join(lines) == text
    assert all(len(l) <= 76 * 2 for l in lines)


def test_long_word_with_indents_and_hanging_is_fast():
    text = "a" * 200_000 + "。"
    lines, t = _timed(
        lambda: wrap(text, 80, initial_indent="  ", subsequent_indent="    ", hanging=True)
    )
    assert t < LIMIT
    assert lines[0] == "  " + "a" * 78
    assert all(l.startswith("    ") for l in lines[1:])
    assert "".join(l.strip() for l in lines) == text


def test_long_word_after_leading_whitespace_is_fast():
    text = "  " + "x" * 200_000
    lines, t = _timed(lambda: wrap(text, 80))
    assert t < LIMIT
    assert lines[0] == "  " + "x" * 78
    assert "".join(lines) == text


def test_long_word_split_is_unchanged():
    # chunks are cut exactly like before, first line with its own width
    assert wrap("abcdefghij", 4) == ["abcd", "efgh", "ij"]
    assert wrap("abcdefghij", 6, initial_indent="  ") == ["  abcd", "efghij"]
    assert wrap("abcdefghij", 6, subsequent_indent="  ") == ["abcdef", "  ghij"]
    # kinsoku still applies inside the split
    assert wrap("abc」defg", 3) == ["ab", "c」", "def", "g"]
    # hanging punctuation may still stay on the last line
    assert wrap("abcdefg。", 4, hanging=True) == ["abcd", "efg。"]


def test_long_word_cli_is_fast(capsys):
    text = base64.b64encode(random.Random(1).randbytes(150_000)).decode()
    import io
    import sys

    old = sys.stdin
    sys.stdin = io.StringIO(text)
    try:
        _, t = _timed(lambda: main(["-w", "76"]))
    finally:
        sys.stdin = old
    assert t < LIMIT
    out = capsys.readouterr().out.splitlines()
    assert "".join(out) == text


# --- #52: ASCII quotes in CJK text --------------------------------------------


def test_issue_example_ja():
    assert wrap('彼は"テスト"と言った', 6) == ["彼は", '"テス', 'ト"と', "言った"]


def test_issue_example_ko():
    lines = wrap('안녕하세요. 저는 "김철수"입니다.', 10, rules="ko")
    assert lines == ["안녕하세", "요. 저는", '"김철수"입', "니다."]


def _check(text, opening, closing, lines):
    """No line ends with an opening quote or starts with a closing one.

    ``opening`` / ``closing`` are indices into ``text``; ``text`` has no
    spaces, so the lines join back to it.
    """
    assert "".join(lines) == text
    pos = 0
    for line in lines:
        first, last = pos, pos + len(line) - 1
        assert last not in opening, (text, lines)
        assert first not in closing, (text, lines)
        pos += len(line)


@pytest.mark.parametrize("rules", ALL)
@pytest.mark.parametrize("q", ['"', "'"])
def test_quotes_never_dangle(rules, q):
    text = f"彼は{q}テスト{q}と言った"
    for w in range(4, 20):
        _check(text, {2}, {6}, wrap(text, w, rules=rules))


@pytest.mark.parametrize("rules", ALL)
def test_quotes_never_dangle_many(rules):
    text = '「"あ"」と言い、"テスト"、\'ア\'。次に"漢字"の"かな"。'
    opening = {i for i, c in enumerate(text) if c in "\"'"}
    closing = set(sorted(opening)[1::2])
    opening -= closing
    for w in range(6, 30):
        _check(text, opening, closing, wrap(text, w, rules=rules))


@pytest.mark.parametrize("rules", ALL)
def test_quote_after_space_opens_and_before_space_closes(rules):
    for w in range(4, 16):
        lines = wrap('設定を "有効" にする', w, rules=rules)
        for l in lines:
            assert not l.endswith(' "') and l != '"', (w, lines)
            assert not l.startswith('"') or l.startswith('"有'), (w, lines)


def test_quote_next_to_brackets_and_punctuation():
    # after an opening bracket: opening
    _check('「"あいう"」', {1}, {5}, wrap('「"あいう"」', 6))
    # before 。 (closing punctuation): closing
    _check('あいう"。', set(), {3}, wrap('あいう"。', 6))
    assert wrap('値は"abc"。', 7) == ["値は", '"abc"。']


def test_quotes_in_hard_split_stay_attached():
    # a unit wider than the line: the split does not leave a quote alone
    assert wrap('"テスト"', 4) == ['"テ', "ス", 'ト"']
    assert wrap("'アイ'", 3) == ["'ア", "イ'"]


def test_english_unchanged():
    texts = [
        'He said "hello world" and it\'s fine',
        "don't stop 'til you get enough",
        "rock 'n' roll in the '90s",
        'x"y"z and "a", "b"',
        '("quoted") text here',
    ]
    for rules in ALL:
        r_noq = KinsokuRules.preset(rules).replace(quotes="")
        for text in texts:
            for w in range(10, 40):
                assert wrap(text, w, rules=rules) == wrap(text, w, rules=r_noq)
    assert wrap('He said "hello world" ok', 13) == ["He said", '"hello world"', "ok"]


def test_closing_quote_after_period():
    # previously '"end.' / '"' (the quote was a word of its own after '.')
    assert wrap('"the end." next', 10) == ['"the end."', "next"]


def test_latin_word_next_to_cjk_unchanged():
    assert wrap('設定を"enabled"にする', 10) == ["設定を", '"enabled"', "にする"]
    assert wrap('設定を "enabled" にする', 10) == ["設定を", '"enabled"', "にする"]


def test_quotes_can_be_turned_off():
    noq = KinsokuRules.preset("ja").replace(quotes="")
    assert noq.quotes == frozenset()
    assert wrap('彼は"テスト"と言った', 6, rules=noq) == ['彼は"', "テスト", '"と', "言った"]


def test_quotes_field():
    for name in ALL:
        assert PRESETS[name].quotes == frozenset("\"'")
    assert KinsokuRules(quotes="x").quotes == frozenset("x")


def test_keep_all_unaffected():
    assert wrap('저는 "김철수"입니다', 14, rules="ko", keep_all=True) == ["저는", '"김철수"입니다']


def test_quotes_with_ansi_and_ruby():
    lines = wrap('彼は\x1b[31m"テスト"\x1b[0mと言った', 6)
    assert [l.replace("\x1b[31m", "").replace("\x1b[0m", "") for l in lines] == [
        "彼は",
        '"テス',
        'ト"と',
        "言った",
    ]
    assert wrap('彼は"｜漢字《かんじ》"と', 20, ruby=True) == ["彼は", '"｜漢字《かんじ》"と']


# --- #52 follow-up: the open-quote count only applies next to non-ASCII ------


def test_unclosed_quote_earlier_does_not_flip_ascii_quotes():
    # A paragraph that opens a quote and never closes it (the usual way to
    # quote across paragraphs in English) must not turn a later opening
    # quote between ASCII characters into a closing one.
    t = '"Quotes may span paragraphs. Then he typed key:"value" twice.'
    assert wrap(t, 48) == [
        '"Quotes may span paragraphs. Then he typed key:',
        '"value" twice.',
    ]
    assert wrap('"start roll v1.2 say:"hi" x"y', 21) == [
        '"start roll v1.2 say:',
        '"hi" x"y',
    ]


@pytest.mark.parametrize("rules", ALL)
@pytest.mark.parametrize(
    "text",
    [
        '"Unclosed start. Then key:"value" and x="abc" here.',
        "'Unclosed single. Then q:'z' and it's x='abc' ok.",
        'Some text end" then key:"value" and say:"hi" more.',
        '" lone quote then key:"value" and a"b"c done',
        '"one "two "three then x="1" y="2" z="3" end',
        '"a" "b "c then say:"hi" x"y and q:\'z\' w\'s',
    ],
)
def test_unclosed_quotes_in_english_unchanged(rules, text):
    r_noq = KinsokuRules.preset(rules).replace(quotes="")
    for w in range(max(map(len, text.split())), len(text) + 2):
        assert wrap(text, w, rules=rules) == wrap(text, w, rules=r_noq), w


@pytest.mark.parametrize("rules", ALL)
def test_unclosed_quotes_in_english_random(rules):
    # Quotes only at word edges next to letters or between ASCII
    # characters, many of them unbalanced: the result matches quotes="".
    words = [
        "he",
        "typed",
        "twice",
        'key:"value"',
        'x="abc"',
        'say:"hi"',
        '"start',
        'end"',
        "don't",
        "'tis",
        "rock'n'roll",
        "v1.2",
        'a"b',
        'foo"',
        '"bar',
        "it's",
        'x"y',
        "q:'z'",
        "'open",
        "close'",
    ]
    r_noq = KinsokuRules.preset(rules).replace(quotes="")
    rnd = random.Random(5252)
    for _ in range(300):
        text = " ".join(rnd.choice(words) for _ in range(rnd.randint(3, 25)))
        w = rnd.randint(max(map(len, text.split())), 40)
        assert wrap(text, w, rules=rules) == wrap(text, w, rules=r_noq), (
            text,
            w,
        )


@pytest.mark.parametrize("rules", ALL)
@pytest.mark.parametrize("q", ['"', "'"])
def test_ascii_quotes_earlier_do_not_break_cjk_fix(rules, q):
    # Balanced ASCII-context quotes before the CJK sentence (left alone by
    # the depth rule) do not change how the CJK quotes are classified.
    for prefix in ["", f"key:{q}value{q}", f"x={q}abc{q}", f"say:{q}hi{q}x{q}y{q}"]:
        prefix += "、" if prefix else ""
        text = prefix + f"彼は{q}テスト{q}と言った"
        n = len(prefix)
        for w in range(max(len(prefix), 4), 24):
            _check(text, {n + 2}, {n + 6}, wrap(text, w, rules=rules))
