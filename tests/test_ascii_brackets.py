"""ASCII brackets after an ASCII word stay inside the word (#65)."""

import base64
import random
import textwrap
import time

import pytest

from kinsoku import PRESETS, KinsokuWrapper, strip_ansi, wrap

RED = "\x1b[31m"
RESET = "\x1b[0m"


# --- the reproductions of the issue ------------------------------------------


@pytest.mark.parametrize(
    ("text", "width", "expected"),
    [
        ("call foo.bar.baz() now", 16, ["call", "foo.bar.baz()", "now"]),
        ("使う print(x) です", 10, ["使う", "print(x)", "です"]),
        ("呼ぶ foo() を", 8, ["呼ぶ", "foo() を"]),
        ("呼ぶ foo() を", 6, ["呼ぶ", "foo()", "を"]),
        ("arr[0] と dict{a}", 7, ["arr[0]", "と", "dict{a}"]),
    ],
)
def test_issue_examples(text, width, expected):
    assert wrap(text, width) == expected


def test_textwrap_replacement():
    assert KinsokuWrapper(width=16).wrap("call foo.bar.baz() now") == [
        "call",
        "foo.bar.baz()",
        "now",
    ]


# --- code fragments ----------------------------------------------------------


@pytest.mark.parametrize("word", ["foo()", "print(x)", "a[0]", "f{x}", "dict{a}"])
@pytest.mark.parametrize("width", range(5, 12))
def test_three_brackets_behave_alike(word, width):
    text = f"xx {word} yy"
    if len(word) <= width:
        assert any(word in line for line in wrap(text, width))


@pytest.mark.parametrize(
    "word",
    [
        "foo.bar.baz()",
        "main(argv)",
        "a[b(c)]",
        "f(x)(y)",
        "foo().bar()",
        "m[0][1]",
        "obj.items()[0]",
        "x{y[z(1)]}",
    ],
)
def test_code_word_is_not_split(word):
    width = len(word)
    assert wrap(f"ab {word} cd", width) == ["ab", word, "cd"]
    assert wrap(f"日本語 {word} です", width) == ["日本語", word, "です"]


def test_spaces_inside_brackets_are_still_break_points():
    assert wrap("call func(a, b) now", 8) == ["call", "func(a,", "b) now"]
    assert wrap("x print(a, b)", 8) == ["x", "print(a,", "b)"]


def test_long_word_is_still_split():
    lines = wrap("aaaaaaaaaa(bbbbbbbbbb)", 8)
    assert "".join(lines) == "aaaaaaaaaa(bbbbbbbbbb)"
    assert all(len(line) <= 8 for line in lines)
    # kinsoku: never a line ending with "(" or starting with ")"
    assert all(not line.endswith("(") and not line.startswith(")") for line in lines)


def test_long_word_kept_without_break_long_words():
    assert wrap("x foo.bar.baz() y", 5, break_long_words=False) == [
        "x",
        "foo.bar.baz()",
        "y",
    ]


def test_infix_after_closing_bracket():
    # "." between ")" and a word character stays inside the word (#39)
    assert wrap("x foo().bar y", 9) == ["x", "foo().bar", "y"]
    # ... but a sentence end is still punctuation
    assert wrap("call f(x). Then", 6) == ["call", "f(x).", "Then"]


def test_quotes_inside_brackets():
    assert wrap('使う print("x") です', 12) == ["使う", 'print("x")', "です"]
    assert wrap("使う f('a') です", 8) == ["使う", "f('a')", "です"]


# --- brackets before a word: unchanged ---------------------------------------


def test_english_parenthesis():
    assert wrap("see (see above) ok", 8) == ["see (see", "above)", "ok"]
    assert wrap("a (b) c", 3) == ["a", "(b)", "c"]


@pytest.mark.parametrize(
    ("text", "width", "expected"),
    [
        ("言った(笑)です", 4, ["言っ", "た", "(笑)", "です"]),
        ("これは(注)です", 6, ["これは", "(注)で", "す"]),
        ("値は(1)です", 4, ["値は", "(1)", "です"]),
    ],
)
def test_parenthesis_in_japanese(text, width, expected):
    assert wrap(text, width) == expected


# --- ANSI escapes --------------------------------------------------------------


@pytest.mark.parametrize(
    "word",
    [
        f"print{RED}(x){RESET}",
        f"{RED}print{RESET}(x)",
        f"print({RED}x{RESET})",
        f"{RED}foo.bar.baz(){RESET}",
    ],
)
def test_ansi_inside_word(word):
    plain = strip_ansi(word)
    lines = wrap(f"使う {word} です", len(plain))
    assert [strip_ansi(line) for line in lines] == ["使う", plain, "です"]


# --- presets -------------------------------------------------------------------


@pytest.mark.parametrize("rules", ["zh-hans", "zh-hant"])
def test_zh(rules):
    assert wrap("使用 print(x) 函数", 10, rules=rules) == ["使用", "print(x)", "函数"]
    assert wrap("调用 foo.bar.baz() 了", 13, rules=rules) == ["调用", "foo.bar.baz()", "了"]
    assert wrap("这是(注)说明", 4, rules=rules) == ["这是", "(注)", "说明"]


def test_ko():
    assert wrap("사용 print(x) 함수", 10, rules="ko") == ["사용", "print(x)", "함수"]
    assert wrap("배열 arr[0] 과 dict{a}", 7, rules="ko") == ["배열", "arr[0]", "과", "dict{a}"]
    assert wrap("참고 (see above) 끝", 8, rules="ko") == ["참고", "(see", "above)", "끝"]


@pytest.mark.parametrize("rules", list(PRESETS))
def test_all_presets(rules):
    assert wrap("call foo.bar.baz() now", 16, rules=rules) == ["call", "foo.bar.baz()", "now"]


# --- same as textwrap for ASCII text whose words fit --------------------------

_WORDS = [
    "foo",
    "foo()",
    "print(x)",
    "a[0]",
    "f{x}",
    "foo.bar.baz()",
    "main(argv)",
    "x.y",
    "1,000",
    "v1.2.3",
    "end.",
    "(see",
    "above)",
]


def test_matches_textwrap():
    rnd = random.Random(65)
    for _ in range(500):
        text = " ".join(rnd.choice(_WORDS) for _ in range(rnd.randint(1, 12)))
        width = rnd.randint(13, 30)
        assert wrap(text, width) == textwrap.wrap(text, width), (text, width)


# --- speed (#43) -----------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        base64.b64encode(random.Random(0).randbytes(150_000)).decode()[:200_000],
        "f(" * 100_000,
        "a(" * 50_000 + ")" * 50_000,
        "x[0]" * 50_000,
    ],
)
def test_long_words_are_fast(text):
    t0 = time.perf_counter()
    lines = wrap(text, 80)
    assert time.perf_counter() - t0 < 10.0
    assert "".join(lines) == text
