import dataclasses

import pytest

from kinsoku import HANGABLE, NO_END, NO_START, PRESETS, KinsokuRules, shorten, wrap
from kinsoku.cli import main

ALL = ("ja", "strict", "loose", "zh-hans", "zh-hant", "ko")


# --- presets -----------------------------------------------------------------

def test_preset_names():
    assert tuple(PRESETS) == ALL


def test_ja_preset_matches_module_constants():
    ja = KinsokuRules.preset("ja")
    assert ja.no_start == NO_START
    assert ja.no_end == NO_END
    assert ja.hangable == HANGABLE


def test_default_is_ja():
    text = "あいッう「かき」くけこ、さしすー"
    for w in range(2, 12):
        assert wrap(text, w) == wrap(text, w, rules="ja")
        assert wrap(text, w) == wrap(text, w, rules=PRESETS["ja"])


def test_strict_keeps_small_kana_choon_and_iteration_marks_off_line_start():
    strict = PRESETS["strict"]
    for ch in "ッっャゃァぁㇰーゝゞヽヾ々〻":
        assert ch in strict.no_start
    assert wrap("あいッう", 4, rules="strict") == ["あ", "いッ", "う"]
    assert wrap("あ時々", 4, rules="strict") == ["あ", "時々"]


def test_loose_lets_small_kana_and_iteration_marks_start_a_line():
    assert wrap("あいッう", 4, rules="ja") == ["あ", "いッ", "う"]
    assert wrap("あいッう", 4, rules="loose") == ["あい", "ッう"]
    assert wrap("あ時々", 4, rules="loose") == ["あ時", "々"]
    loose = PRESETS["loose"]
    for ch in "ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶㇰㇿー々〻":
        assert ch not in loose.no_start
    # ordinary closing punctuation is still no-start
    for ch in "、。」）！？":
        assert ch in loose.no_start
    assert wrap("あいう。", 4, rules="loose") == ["あい", "う。"]


@pytest.mark.parametrize("name", ["zh-hans", "zh-hant"])
def test_chinese_punctuation(name):
    rules = PRESETS[name]
    for ch in "，。！？；：、…”’」』）》〉】〗〕":
        assert ch in rules.no_start, ch
    for ch in "“‘「『（《〈【〖〔":
        assert ch in rules.no_end, ch
    # no Japanese kana rules
    assert "ッ" not in rules.no_start
    lines = wrap("他说：“你好，世界。”", 8, rules=name)
    assert lines == ["他说：", "“你好，", "世界。”"]
    for line in lines:
        assert line[0] not in rules.no_start
        assert line[-1] not in rules.no_end


def test_chinese_middle_dot_differs_from_ja():
    # U+00B7 MIDDLE DOT (used in Chinese names) is no-start for Chinese only
    assert wrap("ab·cd", 2, rules="ja") == ["ab", "·c", "d"]
    assert wrap("ab·cd", 2, rules="zh-hans") == ["a", "b·", "cd"]


def test_zh_hant_small_form_variants():
    assert wrap("我爱你﹐中国", 6, rules="zh-hans") == ["我爱你", "﹐中国"]
    assert wrap("我爱你﹐中国", 6, rules="zh-hant") == ["我爱", "你﹐中", "国"]


def test_chinese_hanging():
    assert wrap("我爱你，中国。", 6, rules="zh-hans", hanging=True) == ["我爱你，", "中国。"]


def test_korean():
    ko = PRESETS["ko"]
    for ch in ".,!?)]}”’」』）》〉】":
        assert ch in ko.no_start, ch
    for ch in "([{“‘「『（《〈【":
        assert ch in ko.no_end, ch
    # no kana rules
    assert "ッ" not in ko.no_start and "ー" not in ko.no_start
    assert wrap("あいッう", 4, rules="ko") == ["あい", "ッう"]
    assert wrap("안녕 (세계)!", 6, rules="ko") == ["안녕", "(세", "계)!"]
    assert wrap("서울 (한국)", 6, rules="ko", keep_all=True) == ["서울", "(한국)"]


# --- custom rules --------------------------------------------------------------

def test_custom_rules_from_strings():
    rules = KinsokuRules(no_start="x", no_end="", hangable="")
    assert rules.no_start == frozenset("x")
    assert isinstance(rules.no_end, frozenset)
    # 'x' cannot start a line, so 'うx' moves together
    assert wrap("あいうxえ", 6, rules=rules) == ["あい", "うxえ"]
    # without the rule nothing special happens; even 。 may start a line
    empty = KinsokuRules()
    assert wrap("あいう。", 6, rules=empty) == ["あいう", "。"]


def test_custom_rules_derived_from_preset():
    ja = KinsokuRules.preset("ja")
    no_choon = ja.replace(no_start=ja.no_start - {"ー"})
    assert "ー" not in no_choon.no_start
    assert no_choon.no_end == ja.no_end
    assert wrap("あいーう", 4, rules="ja") == ["あ", "いー", "う"]
    assert wrap("あいーう", 4, rules=no_choon) == ["あい", "ーう"]
    # dataclasses.replace works too, and the preset itself is untouched
    same = dataclasses.replace(ja, hangable="")
    assert same.hangable == frozenset()
    assert ja.hangable == HANGABLE


def test_rules_are_frozen_and_hashable():
    rules = KinsokuRules.preset("ko")
    with pytest.raises(dataclasses.FrozenInstanceError):
        rules.no_start = frozenset()
    assert hash(rules) == hash(KinsokuRules(rules.no_start, rules.no_end, rules.hangable))
    with pytest.raises(TypeError):
        PRESETS["xx"] = rules


def test_max_lines_placeholder_uses_rules():
    # '(' is no-end for ko, so it is dropped before the placeholder
    assert wrap("ab(cd ef", 4, max_lines=1, rules="ko") == ["ab…"]
    assert shorten("「あいうえお", 4, rules="zh-hant") == "…"


# --- errors ---------------------------------------------------------------------

def test_unknown_preset():
    with pytest.raises(ValueError) as e:
        wrap("abc", 10, rules="fr")
    msg = str(e.value)
    assert "'fr'" in msg
    for name in ALL:
        assert name in msg
    with pytest.raises(ValueError):
        KinsokuRules.preset("JA ")


def test_bad_rules_type():
    with pytest.raises(TypeError):
        wrap("abc", 10, rules=None)


# --- cli ------------------------------------------------------------------------

def test_cli_rules(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("あいッう\n", encoding="utf-8")
    assert main(["-w", "4", str(f)]) == 0
    assert capsys.readouterr().out == "あ\nいッ\nう\n"
    assert main(["-w", "4", "--rules", "loose", str(f)]) == 0
    assert capsys.readouterr().out == "あい\nッう\n"


def test_cli_rules_invalid(capsys):
    with pytest.raises(SystemExit):
        main(["--rules", "fr"])
    assert "invalid choice" in capsys.readouterr().err



# --- KinsokuWrapper ---------------------------------------------------------------

def test_wrapper_rules_via_extra():
    from kinsoku import KinsokuWrapper

    text = "あいうえーおか"
    w = KinsokuWrapper(8, rules="zh-hans")
    assert w.extra == {"rules": "zh-hans"}
    # "ー" may start a line under zh-hans, but not under the default "ja".
    assert w.wrap(text) == wrap(text, 8, rules="zh-hans") == ["あいうえ", "ーおか"]
    assert w.fill(text) == "あいうえ\nーおか"
    assert KinsokuWrapper(8).wrap(text) == ["あいう", "えーおか"]
    with pytest.raises(ValueError):
        KinsokuWrapper(8, rules="fr").wrap(text)
