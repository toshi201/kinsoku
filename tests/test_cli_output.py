"""Errors while writing the output (#67) and the --table width default (#68)."""

import os
import subprocess
import sys

import pytest

from kinsoku import width
from kinsoku.cli import main

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


def _env(**extra):
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("PYTHONIOENCODING", None)
    # With PYTHONUNBUFFERED, a partial write to a pipe is silently dropped
    # instead of raising BrokenPipeError (stdout has no BufferedWriter).
    env.pop("PYTHONUNBUFFERED", None)
    env.update(extra)
    return env


def _run_and_close_early(args, data: bytes):
    """Like ``kinsoku ARGS < data | head -1``: read one line, then close stdout."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "kinsoku", *args],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_env(),
    )
    assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
    proc.stdin.write(data)
    proc.stdin.close()
    first = proc.stdout.readline()
    proc.stdout.close()
    err = proc.stderr.read()
    proc.stderr.close()
    code = proc.wait(timeout=60)
    return code, first, err.decode("utf-8", "replace")


# --- #67: BrokenPipeError -------------------------------------------------

BIG = "".join(f"{i}\n" for i in range(200_000)).encode()


@pytest.mark.parametrize(
    "args, data",
    [
        (["-w", "40"], BIG),
        (["--width-of"], BIG),
        (["--truncate", "-w", "10"], BIG),
        (["--unwrap"], "".join(f"段落{i}\n\n" for i in range(100_000)).encode()),
        (["--table", "-w", "40"], b"a,b\n" + "".join(f"{i},x\n" for i in range(100_000)).encode()),
    ],
    ids=["wrap", "width-of", "truncate", "unwrap", "table"],
)
def test_broken_pipe_is_silent(args, data):
    code, first, err = _run_and_close_early(args, data)
    assert first
    assert err == ""
    assert code == 141


def test_broken_pipe_in_process(monkeypatch, capsys):
    def boom(*a, **k):
        raise BrokenPipeError(32, "Broken pipe")

    monkeypatch.setattr("kinsoku.cli._main", boom)
    assert main(["-w", "10"]) == 141
    assert capsys.readouterr().err == ""


# --- #67: KeyboardInterrupt -----------------------------------------------


def test_keyboard_interrupt_exits_130(monkeypatch, capsys):
    def interrupted(path, encoding):
        raise KeyboardInterrupt

    monkeypatch.setattr("kinsoku.cli._read_input", interrupted)
    assert main(["-w", "10"]) == 130
    assert "Traceback" not in capsys.readouterr().err


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_sigint_while_reading_stdin():
    import signal
    import time

    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import kinsoku.cli, sys; print('ready', flush=True); "
            "sys.exit(kinsoku.cli.main(['-w', '10']))",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_env(),
    )
    assert proc.stdout is not None
    assert proc.stdout.readline() == b"ready\n"
    time.sleep(0.2)
    proc.send_signal(signal.SIGINT)
    _, err = proc.communicate(timeout=30)
    assert proc.returncode == 130
    assert b"Traceback" not in err


# --- #67: UnicodeEncodeError ----------------------------------------------


@pytest.mark.parametrize("args", [["-w", "4"], ["--truncate", "-w", "4"], ["--tategaki", "3"]])
def test_unencodable_output(args):
    r = subprocess.run(
        [sys.executable, "-m", "kinsoku", *args],
        input="🎉\n".encode(),
        capture_output=True,
        env=_env(PYTHONIOENCODING="cp932"),
        timeout=60,
    )
    err = r.stderr.decode("ascii", "replace")
    assert r.returncode == 1
    assert "Traceback" not in err
    assert "kinsoku: error: cannot encode output as cp932 (try PYTHONIOENCODING=utf-8)" in err


# --- #68: --table width ---------------------------------------------------

CSV = "名前,説明,価格\nりんご,赤くて甘い果物。青森県が有名で、ふじという品種が人気,120\n"


def _table(argv, monkeypatch, capsys, tmp_path, columns="30"):
    f = tmp_path / "a.csv"
    f.write_text(CSV, encoding="utf-8")
    monkeypatch.setenv("COLUMNS", columns)
    code = main(["--table", *argv, str(f)])
    out, err = capsys.readouterr()
    return code, out, err


def test_table_default_width_follows_columns(monkeypatch, capsys, tmp_path):
    code, out, _ = _table([], monkeypatch, capsys, tmp_path)
    assert code == 0
    lines = out.splitlines()
    assert len(lines) > 3  # the long cell was wrapped
    assert max(width(line) for line in lines) <= 30


def test_table_explicit_width_wins_over_columns(monkeypatch, capsys, tmp_path):
    code, out, _ = _table(["-w", "40"], monkeypatch, capsys, tmp_path)
    assert code == 0
    assert 30 < max(width(line) for line in out.splitlines()) <= 40


def test_table_width_zero_means_no_limit(monkeypatch, capsys, tmp_path):
    code, out, _ = _table(["-w", "0"], monkeypatch, capsys, tmp_path)
    assert code == 0
    lines = out.splitlines()
    assert len(lines) == 3
    assert "赤くて甘い果物。青森県が有名で、ふじという品種が人気" in lines[2]


def test_table_negative_width_is_an_error(monkeypatch, capsys, tmp_path):
    with pytest.raises(SystemExit) as ei:
        _table(["-w", "-1"], monkeypatch, capsys, tmp_path)
    assert ei.value.code == 2
    assert "width must be > 0" in capsys.readouterr().err


@pytest.mark.parametrize("mode", [[], ["--truncate"], ["--rewrap"]])
def test_width_zero_is_still_an_error_outside_table(mode, capsys):
    with pytest.raises(SystemExit) as ei:
        main([*mode, "-w", "0"])
    assert ei.value.code == 2
    assert "width must be > 0" in capsys.readouterr().err
