"""Where a line may break: ASCII brackets with non-ASCII contents (#73) and
phrase-like break positions with ``phrase=True`` (#77)."""

import random

import pytest
from phrase_corpus import CORPUS

from kinsoku import (
    PRESETS,
    KinsokuWrapper,
    fill,
    rewrap,
    shorten,
    strip_ansi,
    strip_ruby,
    table,
    width,
    wrap,
)
from kinsoku._core import _WORD_BRACKET_RE, _atoms, _glue, _phrase_break, _word_bracket
from kinsoku.cli import main

RED = "\x1b[31m"
RESET = "\x1b[0m"


# --- #73: brackets after an ASCII word ----------------------------------------


@pytest.mark.parametrize(
    ("text", "w", "expected"),
    [
        # main: ["これは", "API(エーピー", "アイ) のこと"]
        ("これは API(エーピーアイ) のこと", 12, ["これは API", "(エーピーア", "イ) のこと"]),
        # main: ["xx", "API(エー", "ピーア", "イ)"]
        ("xx API(エーピーアイ)", 8, ["xx API", "(エー", "ピーア", "イ)"]),
        ("xx f[あ]", 5, ["xx f", "[あ]"]),
        ("xx g{い}", 5, ["xx g", "{い}"]),
        ("説明HTML(ハイパーテキスト)です", 14, ["説明HTML(ハイ", "パーテキスト)", "です"]),
        # unchanged: a bracket before a word, or after a wide character
        ("言った(笑)", 4, ["言っ", "た", "(笑)"]),
        ("(see above) です", 6, ["(see", "above)", "です"]),
    ],
)
def test_wide_contents_break_before_bracket(text, w, expected):
    assert wrap(text, w) == expected


@pytest.mark.parametrize(
    ("text", "w", "expected"),
    [
        ("call foo.bar.baz() now", 16, ["call", "foo.bar.baz()", "now"]),
        ("使う print(x) です", 10, ["使う", "print(x)", "です"]),
        ("呼ぶ foo() を", 6, ["呼ぶ", "foo()", "を"]),
        ("arr[0] と dict{a}", 7, ["arr[0]", "と", "dict{a}"]),
        ("値は a[0] と b[1]", 6, ["値は", "a[0]", "と", "b[1]"]),
        ("f(g(x)) です", 7, ["f(g(x))", "です"]),
    ],
)
def test_ascii_contents_unchanged(text, w, expected):
    assert wrap(text, w) == expected


def test_nested_and_unclosed():
    # the outer bracket has wide contents, the inner one ASCII contents
    assert wrap("f(g(x)あ)", 5) == ["f", "(g(x)", "あ)"]
    # unclosed: the contents run to the end of the line
    assert wrap("abc(あいう", 4) == ["abc", "(あ", "いう"]
    assert wrap("abc(xyz", 4) == ["abc", "(xyz"]


def test_wide_contents_with_ansi_and_ruby():
    text = f"xx API({RED}エーピーアイ{RESET})"
    out = wrap(text, 8)
    assert out[0] == "xx API"
    assert "".join(out) == text
    # the bracket is no longer glued to API, so the ruby fits on its line
    assert wrap("API(漢字《かんじ》)", 16, ruby=True) == ["API", "(漢字《かんじ》)"]


def test_wide_contents_keep_all_unchanged():
    assert wrap("API(エーピーアイ) です", 17, keep_all=True) == ["API(エーピーアイ)", "です"]


# --- #77: phrase=True ----------------------------------------------------------


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ("東京", "都", False),  # kanji -> kanji
        ("ありが", "と", False),  # hiragana -> hiragana
        ("東京", "は", False),  # into hiragana (particle / okurigana)
        ("今日は", "東", True),  # hiragana -> kanji
        ("東京は", "い", True),  # after a particle
        ("東京で", "は", False),  # では
        ("大阪から", "き", True),
        ("東京", "タ", True),  # kanji -> katakana
        ("API", "の", False),
        ("テスト", "A", True),
        ("コー", "ヒ", False),
        ("コ", "ー", False),  # never before ー
        ("。", "あ", True),  # after punctuation
        ("ことは", "あ", False),  # は after hiragana is not taken as a particle
    ],
)
def test_phrase_break_rules(before, after, expected):
    assert _phrase_break(before, after) is expected


@pytest.mark.parametrize(
    ("text", "w", "expected"),
    [
        (
            "今日は東京都庁でありがとうございますと言われました。",
            20,
            ["今日は東京都庁で", "ありがとうございます", "と言われました。"],
        ),
        (
            "明日は大阪から新幹線で帰ります。",
            10,
            ["明日は", "大阪から", "新幹線で", "帰ります。"],
        ),
        ("hello 東京都庁です", 12, ["hello", "東京都庁です"]),
    ],
)
def test_phrase_examples(text, w, expected):
    assert wrap(text, w, phrase=True) == expected
    assert wrap(text, w) != expected


def test_phrase_falls_back_without_boundary():
    # one long kanji compound: no phrase boundary, break anywhere
    text = "東京特許許可局長今日急遽休暇許可拒否"
    assert wrap(text, 10, phrase=True) == wrap(text, 10)
    assert all(width(line) <= 10 for line in wrap(text, 10, phrase=True))


def test_phrase_keeps_half_of_the_line():
    # moving "言われま" would leave "と" alone on its line
    out = wrap("ございますと言われました。", 10, phrase=True)
    assert out == wrap("ございますと言われました。", 10)


def _bad_breaks(phrase: bool) -> tuple[int, int]:
    breaks = bad = 0
    for marked in CORPUS:
        text = marked.replace("/", "")
        ok = set()
        pos = 0
        for part in marked.split("/"):
            pos += len(part)
            ok.add(pos)
        for w in range(8, 31, 2):
            out = wrap(text, w, phrase=phrase)
            assert "".join(out) == text
            assert all(width(line) <= w for line in out)
            pos = 0
            for line in out[:-1]:
                pos += len(line)
                breaks += 1
                bad += pos not in ok
    return breaks, bad


def test_phrase_reduces_mid_word_breaks():
    _, before = _bad_breaks(False)
    _, after = _bad_breaks(True)
    assert after <= before * 0.5


def test_phrase_false_is_the_default():
    rng = random.Random(77)
    chars = "あいうえおかが東京都庁漢字カタカナー、。「」（）abc 123.,"
    for _ in range(300):
        text = "".join(rng.choices(chars, k=rng.randint(0, 60)))
        w = rng.randint(2, 20)
        assert wrap(text, w, phrase=False) == wrap(text, w)


# --- phrase=True with the other options -----------------------------------------

_CHARS = (
    "あいうえおかがはをにでとのも東京都庁漢字新幹線カタカナコーヒー"
    "、。「」『』（）・！？ー々ゃっabcXYZ 123.,()"
)


def _random_text(rng: random.Random) -> str:
    return "".join(rng.choices(_CHARS, k=rng.randint(0, 80)))


@pytest.mark.parametrize("rules", list(PRESETS))
@pytest.mark.parametrize("hanging", [False, True])
def test_phrase_properties(rules, hanging):
    rng = random.Random(len(rules) * 2 + hanging)
    r = PRESETS[rules]
    for _ in range(300):
        text = _random_text(rng)
        w = rng.randint(3, 24)
        out = wrap(text, w, phrase=True, rules=rules, hanging=hanging)
        base = wrap(text, w, rules=rules, hanging=hanging)
        # nothing but whitespace at the breaks is lost
        assert "".join(out).replace(" ", "") == "".join(base).replace(" ", "")
        for line in out:
            hang = 0
            if hanging:
                for ch in reversed(line):
                    if ch not in r.hangable:
                        break
                    hang += width(ch)
            assert width(line) - hang <= w


@pytest.mark.parametrize("rules", list(PRESETS))
def test_phrase_keeps_kinsoku(rules):
    # Without spaces and with every kinsoku block fitting on a line, the
    # default never breaks kinsoku, and neither may phrase=True.
    rng = random.Random(len(rules))
    r = PRESETS[rules]
    checked = 0
    for _ in range(600):
        text = _random_text(rng).replace(" ", "")
        w = rng.randint(6, 24)
        units = _glue(_atoms(text, 1, rules=r), False, 1, r)
        if any(u.width > w for u in units):
            continue
        checked += 1
        out = wrap(text, w, phrase=True, rules=rules)
        assert "".join(out) == text
        for prev, line in zip(out, out[1:], strict=False):
            assert line[0] not in r.no_start
            assert prev[-1] not in r.no_end
    assert checked > 100


def test_phrase_with_ansi():
    text = f"今日は{RED}東京都庁で{RESET}ありがとうございます"
    out = wrap(text, 14, phrase=True)
    assert [strip_ansi(line) for line in out] == wrap(strip_ansi(text), 14, phrase=True)
    out = wrap(text, 14, phrase=True, ansi_reflow=True)
    assert out[0].endswith(RESET)
    assert [strip_ansi(line) for line in out] == wrap(strip_ansi(text), 14, phrase=True)


def test_phrase_with_ruby():
    text = "今日は東京《とうきょう》都庁でありがとう"
    out = wrap(text, 24, phrase=True, ruby=True)
    assert "".join(out) == text
    assert all(width(line) <= 24 for line in out)
    assert not any("《" in line and "》" not in line for line in out)
    assert strip_ruby("".join(wrap(text, 8, phrase=True, ruby=True))) == strip_ruby(text)


def test_phrase_with_indent_and_max_lines():
    text = "明日は大阪から新幹線で帰ります。"
    out = wrap(text, 12, phrase=True, initial_indent="　", subsequent_indent="  ")
    assert all(width(line) <= 12 for line in out)
    assert out[0].startswith("　") and all(line.startswith("  ") for line in out[1:])
    assert "".join(line.lstrip("　 ") for line in out) == text
    out = wrap(text, 10, phrase=True, max_lines=2)
    assert out == ["明日は", "大阪から…"]


def test_phrase_with_keep_all():
    text = "今日は 東京都庁で ありがとう"
    assert wrap(text, 10, phrase=True, keep_all=True) == wrap(text, 10, keep_all=True)


def test_phrase_with_leading_whitespace():
    out = wrap("　今日は東京都庁で会議", 12, phrase=True)
    assert out[0] == "　今日は"
    assert all(width(line) <= 12 for line in out)


# --- the other entry points -------------------------------------------------------

TEXT = "明日は大阪から新幹線で帰ります。"
EXPECTED = ["明日は", "大阪から", "新幹線で", "帰ります。"]


def test_fill_shorten_rewrap():
    assert fill(TEXT, 10, phrase=True) == "\n".join(EXPECTED)
    assert shorten(TEXT, 10, phrase=True) == "明日は…"
    hard = "明日は大阪か\nら新幹線で帰\nります。\n"
    assert rewrap(hard, 10, phrase=True) == "\n".join(EXPECTED) + "\n"


def test_wrapper_and_table():
    assert KinsokuWrapper(width=10, phrase=True).wrap(TEXT) == EXPECTED
    out = table([[TEXT]], width=10, phrase=True)
    assert [line.rstrip() for line in out.splitlines()] == EXPECTED
    assert table([[TEXT]], width=10) != out


def test_cli_phrase(capsys, monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(TEXT + "\n"))
    assert main(["-w", "10", "--phrase"]) == 0
    assert capsys.readouterr().out == "\n".join(EXPECTED) + "\n"
    monkeypatch.setattr("sys.stdin", io.StringIO("明日は大阪か\nら新幹線で帰\nります。\n"))
    assert main(["-w", "10", "--rewrap", "--phrase"]) == 0
    assert capsys.readouterr().out == "\n".join(EXPECTED) + "\n"


@pytest.mark.parametrize("mode", ["--truncate", "--width-of", "--unwrap", "--table"])
def test_cli_phrase_rejected_elsewhere(mode, capsys, monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(TEXT + "\n"))
    with pytest.raises(SystemExit) as e:
        main([mode, "--phrase"])
    assert e.value.code == 2
    assert "--phrase cannot be used with" in capsys.readouterr().err


def test_bracket_at_line_start_then_word_bracket():
    # a bracket at the very start must not hide the later API( (#73)
    assert wrap("(a) API(エーピーアイ)", 8) == ["(a) API", "(エー", "ピーア", "イ)"]


def test_word_bracket_precheck_matches_regex():
    rng = random.Random(73)
    chars = "ab_1)]}([{ あ漢́️‍"
    for _ in range(3000):
        text = "".join(rng.choices(chars, k=rng.randint(0, 12)))
        # a superset of the regex (which allows escapes in between too)
        if _WORD_BRACKET_RE.search(text):
            assert _word_bracket(text)
