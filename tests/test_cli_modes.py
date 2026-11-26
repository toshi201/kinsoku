"""CLI: which options each mode accepts (#47) and BOM handling (#48)."""

import io
import re

import pytest

from kinsoku.cli import _MODE_OPTIONS, _OPTIONS, main

BOM = b"\xef\xbb\xbf"

# mode flag -> argv that selects it ("" is plain wrapping)
MODES = {
    "": [],
    "--truncate": ["--truncate"],
    "--width-of": ["--width-of"],
    "--tategaki": ["--tategaki", "4"],
    "--table": ["--table"],
    "--unwrap": ["--unwrap"],
    "--rewrap": ["--rewrap"],
}

# dest -> argv giving the option a non-default value
OPTION_ARGV = {
    "width": ["-w", "10"],
    "hanging": ["--hanging"],
    "no_break_long_words": ["--no-break-long-words"],
    "keep_all": ["--keep-all"],
    "indent": ["-i", "　"],
    "subsequent_indent": ["-s", "　"],
    "max_lines": ["-n", "2"],
    "ambiguous_width": ["--ambiguous-width", "2"],
    "rules": ["--rules", "ko"],
    "ansi_reflow": ["--ansi-reflow"],
    "ruby": ["--ruby"],
    "ruby_width": ["--ruby-width", "base"],
    "tabsize": ["--tabsize", "4"],
    "gap": ["--gap", "2"],
    "indent_marks_paragraph": ["--indent-marks-paragraph"],
    "cjk_latin_space": ["--cjk-latin-space"],
    "delimiter": ["--delimiter", ","],
    "no_header": ["--no-header"],
    "style": ["--style", "grid"],
    "placeholder": ["--placeholder", "..."],
    "phrase": ["--phrase"],
}
FLAG = {dest: opt for opt, dest, _ in _OPTIONS}

ALLOWED = [(m, d) for m in MODES for d in OPTION_ARGV if d in _MODE_OPTIONS[m]]
REJECTED = [(m, d) for m in MODES for d in OPTION_ARGV if d not in _MODE_OPTIONS[m]]


def set_stdin(monkeypatch, data: bytes):
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(data), encoding="utf-8"))


def run_err(argv, capsys):
    with pytest.raises(SystemExit) as ei:
        main(argv)
    out, err = capsys.readouterr()
    assert "Traceback" not in err
    return ei.value.code, out, err


def test_option_table_covers_every_option():
    assert set(OPTION_ARGV) == set(FLAG)
    assert set(MODES) == set(_MODE_OPTIONS)


# accepted in every mode, or select the mode themselves
NOT_MODE_DEPENDENT = {
    "--help",
    "--version",
    "--encoding",
    "--truncate",
    "--width-of",
    "--tategaki",
    "--table",
    "--unwrap",
    "--rewrap",
}


def test_every_cli_option_is_classified(capsys):
    # a new option must be added to _OPTIONS (and _MODE_OPTIONS), so that
    # using it with the wrong mode is an error rather than silently ignored
    with pytest.raises(SystemExit):
        main(["--help"])
    flags = set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", capsys.readouterr().out))
    assert flags - NOT_MODE_DEPENDENT == set(FLAG.values())


# --- #47: rejected combinations ----------------------------------------------


@pytest.mark.parametrize("mode,dest", REJECTED, ids=[f"{m or 'wrap'}:{d}" for m, d in REJECTED])
def test_rejected_combination(mode, dest, capsys, monkeypatch):
    set_stdin(monkeypatch, "あいう\n".encode())
    code, out, err = run_err([*MODES[mode], *OPTION_ARGV[dest]], capsys)
    assert code == 2
    assert out == ""
    if mode:
        assert f"kinsoku: error: {FLAG[dest]} cannot be used with {mode}\n" in err
    else:
        assert f"kinsoku: error: {FLAG[dest]} requires --" in err


@pytest.mark.parametrize("mode,dest", ALLOWED, ids=[f"{m or 'wrap'}:{d}" for m, d in ALLOWED])
def test_allowed_combination(mode, dest, capsys, monkeypatch):
    set_stdin(monkeypatch, "あいう,えお\nか,き\n".encode())
    assert main([*MODES[mode], *OPTION_ARGV[dest]]) == 0
    assert capsys.readouterr().out != ""


@pytest.mark.parametrize("mode", list(MODES), ids=lambda m: m or "wrap")
def test_defaults_are_never_rejected(mode, capsys, monkeypatch):
    # explicitly passing a default value counts as "not given"
    set_stdin(monkeypatch, "あいう\n".encode())
    argv = [
        *MODES[mode],
        "--rules",
        "ja",
        "--ambiguous-width",
        "1",
        "--tabsize",
        "8",
        "--style",
        "simple",
        "--ruby-width",
        "full",
    ]
    assert main(argv) == 0


def test_issue_examples(capsys, monkeypatch):
    set_stdin(monkeypatch, "あいうえおかきくけこ\n".encode())
    code, _, err = run_err(["--unwrap", "-w", "4", "-n", "1"], capsys)
    assert code == 2
    assert "kinsoku: error: --width cannot be used with --unwrap" in err
    code, _, err = run_err(["--style", "grid"], capsys)
    assert code == 2
    assert "kinsoku: error: --style requires --table" in err
    code, _, err = run_err(["--table", "--ruby"], capsys)
    assert "kinsoku: error: --ruby cannot be used with --table" in err


def test_gap_message_is_unchanged(capsys, monkeypatch):
    set_stdin(monkeypatch, "あいう\n".encode())
    _, _, err = run_err(["--gap", "2"], capsys)
    assert "kinsoku: error: --gap requires --tategaki\n" in err


# --- #47: combinations that now do something ---------------------------------


def test_tategaki_ruby_strips_annotations(capsys, monkeypatch):
    set_stdin(monkeypatch, "｜吾輩《わがはい》は猫である。\n".encode())
    assert main(["--tategaki", "6", "--ruby"]) == 0
    out = capsys.readouterr().out
    assert "わ" not in out and "｜" not in out
    assert out == main_out(["--tategaki", "6"], "吾輩は猫である。\n", capsys, monkeypatch)


def main_out(argv, text, capsys, monkeypatch):
    set_stdin(monkeypatch, text.encode())
    assert main(argv) == 0
    return capsys.readouterr().out


def test_table_rules_still_allowed(capsys, monkeypatch):
    out = main_out(
        ["--table", "--rules", "zh-hans", "-w", "20"], "a,b\n你好,世界\n", capsys, monkeypatch
    )
    assert "你好" in out


def test_truncate_tabsize_is_used(capsys, monkeypatch):
    a = main_out(["--truncate", "-w", "6", "--tabsize", "2"], "a\tbcdefgh\n", capsys, monkeypatch)
    b = main_out(["--truncate", "-w", "6"], "a\tbcdefgh\n", capsys, monkeypatch)
    assert a != b


# --- #48: BOM -----------------------------------------------------------------


def test_bom_csv_header(tmp_path, capsys):
    f = tmp_path / "bom.csv"
    f.write_bytes(BOM + "名前,値\nA,1\n".encode())
    assert main(["--table", "--style", "grid", str(f)]) == 0
    out = capsys.readouterr().out
    assert "﻿" not in out
    assert out.splitlines()[1] == "│ 名前 │ 値 │"


def test_bom_stripped_from_every_file(tmp_path, capsys, monkeypatch):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_bytes(BOM + "あいう\n".encode())
    b.write_bytes(BOM + "えお\n".encode())
    set_stdin(monkeypatch, BOM + "かき\n".encode())
    assert main(["-w", "20", str(a), "-", str(b)]) == 0
    assert capsys.readouterr().out == "あいう\nかき\nえお\n"


def test_bom_stdin(capsys, monkeypatch):
    out = main_out(["-w", "6"], "﻿あいうえおかき\n", capsys, monkeypatch)
    assert out == "あいう\nえおか\nき\n"


def test_bom_stdin_without_buffer(capsys, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("﻿あい\n"))
    assert main(["--width-of"]) == 0
    assert capsys.readouterr().out == "4\n"


@pytest.mark.parametrize("enc", ["utf-8", "UTF8", "utf_8", "utf-8-sig"])
def test_bom_stripped_with_explicit_utf8(enc, tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_bytes(BOM + "あい\n".encode())
    assert main(["--encoding", enc, "--width-of", str(f)]) == 0
    assert capsys.readouterr().out == "4\n"


def test_only_leading_bom_is_removed(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_bytes(BOM + "あ﻿い\n".encode())
    assert main(["--unwrap", str(f)]) == 0
    assert capsys.readouterr().out == "あ﻿い\n"


def test_other_encoding_is_respected(tmp_path, capsys):
    # utf-16 decodes its own BOM; explicit non-UTF-8 encodings are used as given
    f = tmp_path / "a.txt"
    f.write_bytes("あい\n".encode("utf-16"))
    assert main(["--encoding", "utf-16", "--width-of", str(f)]) == 0
    assert capsys.readouterr().out == "4\n"
    g = tmp_path / "b.txt"
    g.write_bytes(BOM + b"a\n")
    assert main(["--encoding", "latin-1", "--unwrap", str(g)]) == 0
    assert capsys.readouterr().out == "ï»¿a\n"


# --- review of #53: --rewrap accepts --ruby / --ruby-width --------------------

RUBY_TEXT = (
    " ｜吾輩《わがはい》は猫である。名前は\nまだ無い。どこで生れたかとんと\n見当がつかぬ。\n"
)


def test_rewrap_ruby_keeps_annotations_whole(capsys, monkeypatch):
    import kinsoku

    # Wide enough for the indented ruby unit: the notation stays whole.
    out = main_out(["--rewrap", "-w", "19", "--ruby"], RUBY_TEXT, capsys, monkeypatch)
    assert out.splitlines()[0] == " ｜吾輩《わがはい》"
    assert out == kinsoku.rewrap(RUBY_TEXT, 19, ruby=True)


def test_rewrap_ruby_never_splits_notation(capsys, monkeypatch):
    import kinsoku

    # Too narrow for the ruby unit: without --ruby the notation is cut
    # mid-way; with --ruby it is never cut (an over-wide unit drops its
    # annotation and wraps the base text instead, see #51).
    plain = main_out(["--rewrap", "-w", "12"], RUBY_TEXT, capsys, monkeypatch)
    assert "《わがはい》" not in plain
    out = main_out(["--rewrap", "-w", "12", "--ruby"], RUBY_TEXT, capsys, monkeypatch)
    assert out == kinsoku.rewrap(RUBY_TEXT, 12, ruby=True)
    for line in out.splitlines():
        assert line.count("《") == line.count("》")
        assert "｜" not in line or "《" in line


def test_rewrap_ruby_width_is_passed(capsys, monkeypatch):
    import kinsoku

    out = main_out(
        ["--rewrap", "-w", "12", "--ruby", "--ruby-width", "base"], RUBY_TEXT, capsys, monkeypatch
    )
    assert out == kinsoku.rewrap(RUBY_TEXT, 12, ruby=True, ruby_width="base")


# --- #54: --cjk-latin-space only with --unwrap / --rewrap ---------------------


@pytest.mark.parametrize(
    "mode", ["", "--truncate", "--width-of", "--tategaki", "--table"], ids=lambda m: m or "wrap"
)
def test_cjk_latin_space_rejected_elsewhere(mode, capsys, monkeypatch):
    set_stdin(monkeypatch, "あいう\n".encode())
    code, out, err = run_err([*MODES[mode], "--cjk-latin-space"], capsys)
    assert code == 2 and out == ""
    if mode:
        assert f"--cjk-latin-space cannot be used with {mode}" in err
    else:
        assert "--cjk-latin-space requires --unwrap or --rewrap" in err


@pytest.mark.parametrize("mode", ["--unwrap", "--rewrap"])
def test_cjk_latin_space_is_used(mode, capsys, monkeypatch):
    text = "日本語と\nEnglish\nの混在\n"
    assert (
        main_out([mode, "--cjk-latin-space"], text, capsys, monkeypatch)
        == "日本語と English の混在\n"
    )
    assert main_out([mode], text, capsys, monkeypatch) == "日本語とEnglishの混在\n"
