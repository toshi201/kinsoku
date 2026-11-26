"""CLI robustness tests (#26, #27, #28)."""

import io

import pytest

from kinsoku.cli import main


def run(argv, capsys):
    code = main(argv)
    out, err = capsys.readouterr()
    return code, out, err


def run_err(argv, capsys):
    with pytest.raises(SystemExit) as ei:
        main(argv)
    out, err = capsys.readouterr()
    assert "Traceback" not in err
    return ei.value.code, out, err


def set_stdin(monkeypatch, data: bytes):
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(data), encoding="utf-8"))


# --- #26: multiple files -------------------------------------------------

def test_files_without_trailing_newline_are_not_merged(tmp_path, capsys):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("あいうえお", encoding="utf-8")
    b.write_text("かきくけこ\n", encoding="utf-8")
    code, out, _ = run(["-w", "20", str(a), str(b)], capsys)
    assert code == 0
    assert out == "あいうえお\nかきくけこ\n"


def test_truncate_multiple_files_without_trailing_newline(tmp_path, capsys):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("abc", encoding="utf-8")
    b.write_text("def", encoding="utf-8")
    _, out, _ = run(["--width-of", str(a), str(b)], capsys)
    assert out == "3\n3\n"


def test_dash_reads_stdin_between_files(tmp_path, capsys, monkeypatch):
    a = tmp_path / "a.txt"
    a.write_text("one", encoding="utf-8")
    set_stdin(monkeypatch, "two".encode())
    _, out, _ = run(["-w", "20", str(a), "-", str(a)], capsys)
    assert out == "one\ntwo\none\n"


# --- #27: friendly errors, --encoding ------------------------------------

def test_missing_file(tmp_path, capsys):
    missing = tmp_path / "nope.txt"
    code, out, err = run_err(["-w", "20", str(missing)], capsys)
    assert code == 1
    assert out == ""
    assert err == f"kinsoku: error: {missing}: No such file or directory\n"


def test_directory_is_io_error(tmp_path, capsys):
    code, _, err = run_err([str(tmp_path)], capsys)
    assert code == 1
    assert err.startswith(f"kinsoku: error: {tmp_path}: ")


def test_non_utf8_file_suggests_encoding(tmp_path, capsys):
    bad = tmp_path / "bad.txt"
    bad.write_bytes(b"\xff\xfeabc")
    code, _, err = run_err(["-w", "20", str(bad)], capsys)
    assert code == 1
    assert err.startswith(f"kinsoku: error: {bad}: cannot decode as utf-8")
    assert "--encoding" in err


def test_non_utf8_stdin(capsys, monkeypatch):
    set_stdin(monkeypatch, b"\xff\xfe")
    code, _, err = run_err(["-w", "20"], capsys)
    assert code == 1
    assert err.startswith("kinsoku: error: <stdin>: cannot decode")


def test_encoding_cp932_file(tmp_path, capsys):
    sj = tmp_path / "aozora.txt"
    sj.write_bytes("吾輩は猫である。名前はまだ無い。\r\n".encode("cp932"))
    code, out, _ = run(["-w", "16", "--encoding", "cp932", str(sj)], capsys)
    assert code == 0
    assert out == "吾輩は猫である。\n名前はまだ無い。\n"


def test_encoding_shift_jis_stdin(capsys, monkeypatch):
    set_stdin(monkeypatch, "あいう\n".encode("shift_jis"))
    _, out, _ = run(["--encoding", "shift_jis", "--width-of"], capsys)
    assert out == "6\n"


def test_unknown_encoding(capsys):
    code, _, err = run_err(["--encoding", "no-such-codec"], capsys)
    assert code == 2
    assert "unknown encoding: no-such-codec" in err


def test_truncate_value_error_is_friendly(capsys, monkeypatch):
    set_stdin(monkeypatch, "あいう\n".encode())
    code, _, err = run_err(["--truncate", "-w", "1", "--ambiguous-width", "2"], capsys)
    assert code == 2
    assert "kinsoku: error: placeholder is wider than width" in err


def test_help_mentions_encoding(capsys):
    code, out, _ = run_err(["--help"], capsys)
    assert code == 0
    assert "--encoding" in out and "cp932" in out


# --- #28: width, COLUMNS, exclusive modes, --placeholder -----------------

@pytest.mark.parametrize("w", ["0", "-3"])
def test_non_positive_width_is_error(w, capsys, monkeypatch):
    set_stdin(monkeypatch, "あいうえお\n".encode())
    code, _, err = run_err(["--truncate", "-w", w], capsys)
    assert code == 2
    assert "width must be > 0" in err


def test_columns_env_is_honored(capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "10")
    set_stdin(monkeypatch, "あいうえおかきくけこ\n".encode())
    _, out, _ = run([], capsys)
    assert out == "あいうえお\nかきくけこ\n"


def test_default_width_is_80_without_columns(capsys, monkeypatch):
    monkeypatch.delenv("COLUMNS", raising=False)
    monkeypatch.setattr(
        "shutil.get_terminal_size", lambda fallback=(80, 24): __import__("os").terminal_size(fallback)
    )
    set_stdin(monkeypatch, ("あ" * 45 + "\n").encode())
    _, out, _ = run([], capsys)
    assert out == "あ" * 40 + "\n" + "あ" * 5 + "\n"


def test_explicit_width_beats_columns(capsys, monkeypatch):
    monkeypatch.setenv("COLUMNS", "4")
    set_stdin(monkeypatch, "あいうえお\n".encode())
    _, out, _ = run(["-w", "6"], capsys)
    assert out == "あいう\nえお\n"


def test_truncate_and_width_of_are_exclusive(capsys):
    code, _, err = run_err(["--truncate", "--width-of"], capsys)
    assert code == 2
    assert "not allowed with argument" in err


@pytest.mark.parametrize("mode", ["--truncate", "--width-of"])
@pytest.mark.parametrize(
    "opt",
    [["--hanging"], ["-n", "2"], ["--keep-all"], ["--no-break-long-words"],
     ["-i", "　"], ["-s", "  "]],
)
def test_wrap_only_options_rejected_in_other_modes(mode, opt, capsys):
    code, _, err = run_err([mode, *opt], capsys)
    assert code == 2
    assert f"cannot be used with {mode}" in err


def test_placeholder_rejected_with_width_of(capsys):
    code, _, err = run_err(["--width-of", "--placeholder", "..."], capsys)
    assert code == 2
    assert "--placeholder cannot be used with --width-of" in err


def test_placeholder_with_truncate(capsys, monkeypatch):
    set_stdin(monkeypatch, "あいうえおかきくけこ\n".encode())
    _, out, _ = run(["--truncate", "-w", "10", "--placeholder", "..."], capsys)
    assert out == "あいう...\n"


def test_placeholder_with_max_lines(capsys, monkeypatch):
    set_stdin(monkeypatch, "あいうえおかきくけこさしすせそ\n".encode())
    _, out, _ = run(["-w", "10", "-n", "1", "--placeholder", ">>"], capsys)
    assert out == "あいうえ>>\n"


def test_default_placeholder_unchanged(capsys, monkeypatch):
    set_stdin(monkeypatch, "あいうえおかきくけこ\n".encode())
    _, out, _ = run(["--truncate", "-w", "10"], capsys)
    assert out == "あいうえ…\n"


# --- tategaki / unwrap / rewrap / table in the mode group -------------------


@pytest.mark.parametrize(
    "other",
    [["--truncate"], ["--width-of"], ["--unwrap"], ["--rewrap"], ["--table"]],
)
def test_tategaki_is_exclusive_with_other_modes(tmp_path, capsys, other):
    f = tmp_path / "a.txt"
    f.write_text("あいう\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        main(["--tategaki", "2", *other, str(f)])
    assert e.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err


def test_unwrap_rewrap_truncate_are_exclusive(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("あいう\n", encoding="utf-8")
    for combo in (["--unwrap", "--rewrap"], ["--rewrap", "--truncate"],
                  ["--unwrap", "--width-of"]):
        with pytest.raises(SystemExit) as e:
            main([*combo, str(f)])
        assert e.value.code == 2
        assert "not allowed with argument" in capsys.readouterr().err


@pytest.mark.parametrize(
    "opt",
    [["-n", "2"], ["-i", "　"], ["-s", "　"], ["--keep-all"],
     ["--no-break-long-words"], ["--hanging"], ["--placeholder", "..."]],
)
def test_tategaki_rejects_wrap_only_options(tmp_path, capsys, opt):
    f = tmp_path / "a.txt"
    f.write_text("あいう\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        main(["--tategaki", "2", *opt, str(f)])
    assert e.value.code == 2
    assert "cannot be used with --tategaki" in capsys.readouterr().err


def test_gap_requires_tategaki(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_text("あいう\n", encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        main(["--gap", "2", str(f)])
    assert e.value.code == 2
    assert "--gap requires --tategaki" in capsys.readouterr().err
    assert main(["--tategaki", "3", "--gap", "2", str(f)]) == 0
    assert capsys.readouterr().out == "あ\nい\nう\n"


def test_tategaki_reads_files_per_file_with_encoding(tmp_path, capsys):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_bytes("あい".encode("cp932"))  # no final newline
    b.write_bytes("うえ\n".encode("cp932"))
    assert main(["--tategaki", "2", "--encoding", "cp932", str(a), str(b)]) == 0
    assert capsys.readouterr().out == "う あ\nえ い\n"
    with pytest.raises(SystemExit) as e:
        main(["--tategaki", "2", str(a)])
    assert e.value.code == 1
    assert "cannot decode as utf-8" in capsys.readouterr().err
    with pytest.raises(SystemExit) as e:
        main(["--tategaki", "2", str(tmp_path / "missing.txt")])
    assert e.value.code == 1
    assert "missing.txt" in capsys.readouterr().err
