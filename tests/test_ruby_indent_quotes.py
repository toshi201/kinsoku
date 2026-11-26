"""#59: ruby units vs. the width left after the indent; #60: quotes after an
unclosed English quote."""

import pytest

from kinsoku import KinsokuWrapper, fill, rewrap, shorten, strip_ruby, width, wrap

# --- #59: a ruby unit must fit in the width the line has left ---------------

RUBY_TEXTS = [
    "｜吾輩《わがはい》は猫である。名前はまだ無い。",
    " ｜吾輩《わがはい》は猫である。",
    "　｜東京特許許可局《とうきょうとっきょきょかきょく》に行った。",
    "猫《ねこ》である。｜吾輩《わがはい》の、漢字《かんじ》の読み。",
    "  ｜魔法少女《マジカルガール》が、｜変身《へんしん》した。",
]
INDENTS = [("", ""), ("  ", ""), ("", "  "), ("　", "　"), ("    ", "  ")]


def test_issue_example():
    lines = rewrap(" ｜吾輩《わがはい》は猫である。", 18, ruby=True).splitlines()
    assert all(width(line) <= 18 for line in lines)
    assert lines[0] == " 吾輩は猫である。"


def test_wrap_with_indent_drops_ruby():
    lines = wrap("｜吾輩《わがはい》は猫である。", 18, ruby=True, initial_indent="  ")
    assert lines == ["  吾輩は猫である。"]


def test_ruby_kept_when_it_fits_the_next_line():
    # does not fit after the first-line indent, but fits on the next line
    lines = wrap("あ｜吾輩《わがはい》", 18, ruby=True, initial_indent="  ")
    assert lines == ["  あ", "｜吾輩《わがはい》"]


def test_ruby_kept_when_it_fits():
    assert wrap("｜吾輩《わがはい》は猫", 20, ruby=True, initial_indent="  ") == [
        "  ｜吾輩《わがはい》",
        "は猫",
    ]


@pytest.mark.parametrize("text", RUBY_TEXTS)
@pytest.mark.parametrize(("ii", "si"), INDENTS)
@pytest.mark.parametrize("w", range(6, 40))
def test_wrap_fill_never_overflow(text, ii, si, w):
    lines = wrap(text, w, ruby=True, initial_indent=ii, subsequent_indent=si)
    assert all(width(line) <= w for line in lines), lines
    assert strip_ruby("".join(lines)).replace(" ", "").replace("　", "") == strip_ruby(
        text
    ).replace(" ", "").replace("　", "")
    assert fill(text, w, ruby=True, initial_indent=ii, subsequent_indent=si) == "\n".join(lines)


@pytest.mark.parametrize("text", RUBY_TEXTS)
@pytest.mark.parametrize("ii", ["", "  ", "　"])
@pytest.mark.parametrize("w", range(6, 40))
def test_rewrap_never_overflows(text, ii, w):
    out = rewrap(text, w, ruby=True, initial_indent=ii)
    assert all(width(line) <= w for line in out.splitlines()), out


@pytest.mark.parametrize("text", RUBY_TEXTS)
@pytest.mark.parametrize("ii", ["", "  ", "　"])
@pytest.mark.parametrize("w", range(6, 40))
def test_shorten_and_max_lines_never_overflow(text, ii, w):
    assert width(shorten(text, w, ruby=True, initial_indent=ii)) <= w
    lines = wrap(text, w, ruby=True, initial_indent=ii, max_lines=2)
    assert all(width(line) <= w for line in lines), lines


@pytest.mark.parametrize("text", RUBY_TEXTS)
@pytest.mark.parametrize(("ii", "si"), INDENTS)
@pytest.mark.parametrize("w", range(6, 40))
def test_wrapper_never_overflows(text, ii, si, w):
    kw = dict(width=w, initial_indent=ii, subsequent_indent=si, ruby=True)
    lines = KinsokuWrapper(**kw).wrap(text)
    assert all(width(line) <= w for line in lines), lines
    lines = KinsokuWrapper(max_lines=2, placeholder="…", **kw).wrap(text)
    assert all(width(line) <= w for line in lines), lines


def test_break_long_words_false_keeps_ruby():
    lines = wrap(
        " ｜吾輩《わがはい》は猫", 18, ruby=True, initial_indent=" ", break_long_words=False
    )
    assert "｜吾輩《わがはい》" in "".join(lines)


# --- #60: an unclosed English quote does not flip later quotes --------------

ISSUE_60 = 'He said "hello. それから彼は"テスト"と言った。'


@pytest.mark.parametrize("w", range(4, 40))
def test_quotes_after_unclosed_english_quote(w):
    lines = wrap(ISSUE_60, w)
    assert "".join(lines).replace(" ", "") == ISSUE_60.replace(" ", "")
    for line in lines:
        # the opening quote of "テスト" never ends a line, its closing one
        # never starts a line
        assert not line.endswith('は"'), lines
        assert not line.startswith('"と'), lines
    assert any('"テ' in line for line in lines)
    assert any('ト"' in line for line in lines)


@pytest.mark.parametrize(
    "text",
    [
        'He said "hello! それから彼は"テスト"と言った。',
        'He said "hello? 彼は"テスト"と言った。',
        'He said "hello。彼は"テスト"と言った。',
    ],
)
@pytest.mark.parametrize("w", range(4, 30))
def test_other_sentence_ends(text, w):
    for line in wrap(text, w):
        assert not line.endswith('は"'), line
        assert not line.startswith('"と'), line


@pytest.mark.parametrize(
    "text",
    [
        '"hello世界"です。',  # opened by English text, closed in Japanese
        '彼は"テスト。です"と言った。',  # a Japanese quote spans a sentence end
        '彼は"hello world"と言った。',
        '"a" 彼は"テスト"と言った。',
    ],
)
@pytest.mark.parametrize("w", range(4, 20))
def test_pairs_still_match(text, w):
    lines = wrap(text, w)
    for line in lines:
        assert not line.startswith('"です'), lines
        assert not line.startswith('"と'), lines
        assert not line.endswith('は"'), lines


ENGLISH = 'He said "hello. Then key:"value" and "y z" ok.'


@pytest.mark.parametrize(
    ("w", "expected"),
    [
        (8, ["He said", '"hello.', "Then", "key:", '"value"', 'and "y', 'z" ok.']),
        (12, ["He said", '"hello. Then', 'key:"value"', 'and "y z"', "ok."]),
        (20, ['He said "hello. Then', 'key:"value" and "y', 'z" ok.']),
    ],
)
def test_english_only_unchanged(w, expected):
    # same as before #60 (#57 review: key:"value" stays one word)
    assert wrap(ENGLISH, w) == expected
