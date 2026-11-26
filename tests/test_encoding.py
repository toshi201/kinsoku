"""--encoding auto and kinsoku.detect_encoding (#78)."""

import io

import pytest

import kinsoku
from kinsoku import detect_encoding
from kinsoku.cli import main

TEXT = "吾輩は猫である。名前はまだ無い。\nどこで生れたかとんと見当がつかぬ。\n"


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


# --- detect_encoding ------------------------------------------------------


def test_public():
    assert kinsoku.detect_encoding is detect_encoding
    assert "detect_encoding" in kinsoku.__all__


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (TEXT.encode("utf-8"), "utf-8"),
        (TEXT.encode("utf-8-sig"), "utf-8-sig"),
        (TEXT.encode("utf-16"), "utf-16"),
        (TEXT.encode("utf-16-le").join([b"\xff\xfe", b""]), "utf-16"),
        (b"\xfe\xff" + TEXT.encode("utf-16-be"), "utf-16"),
        (TEXT.encode("utf-32"), "utf-32"),
        (TEXT.encode("cp932"), "cp932"),
        (TEXT.encode("euc-jp"), "euc-jp"),
    ],
)
def test_detect(data, expected):
    enc = detect_encoding(data)
    assert enc == expected
    assert data.decode(enc) == TEXT


def test_empty_and_ascii_are_utf8():
    assert detect_encoding(b"") == "utf-8"
    assert detect_encoding(b"hello, world\n") == "utf-8"


@pytest.mark.parametrize(
    "text",
    ["あ", "ア", "。", "日本", "東京", "カナ", "「本」", "１２３", "aあ"],
)
@pytest.mark.parametrize("enc", ["cp932", "euc-jp"])
def test_short_text(text, enc):
    data = text.encode(enc)
    assert data.decode(detect_encoding(data)) == text


def test_short_valid_utf8_wins():
    # EUC-JP "猫" is C7 AD, which is also valid UTF-8 ("ǭ"): UTF-8 is tried
    # first, so very short input like this is a known limit of the guess.
    assert detect_encoding("猫".encode("euc-jp")) == "utf-8"
    assert detect_encoding("猫が".encode("euc-jp")) == "euc-jp"


def test_short_half_width_kana_cp932():
    assert detect_encoding("ｱｲｳ".encode("cp932")) == "cp932"


def test_cp932_vendor_chars():
    # NEC special characters only exist in cp932
    text = "①②③　№㈱"
    assert detect_encoding(text.encode("cp932")) == "cp932"


def test_euc_jp_with_half_width_kana():
    text = "ﾃｽﾄです。"
    assert detect_encoding(text.encode("euc-jp")) == "euc-jp"


def test_undecodable():
    with pytest.raises(UnicodeDecodeError):
        detect_encoding(b"\x80\xa0\xfd")


# --- CLI ------------------------------------------------------------------


@pytest.mark.parametrize("enc", ["utf-8", "utf-8-sig", "utf-16", "cp932", "euc-jp"])
def test_cli_file(tmp_path, capsys, enc):
    f = tmp_path / "a.txt"
    f.write_bytes(TEXT.encode(enc))
    code, out, err = run(["-w", "80", "--encoding", "auto", str(f)], capsys)
    assert code == 0
    assert out == TEXT
    assert err == ""


@pytest.mark.parametrize("enc", ["cp932", "utf-16"])
def test_cli_file_crlf(tmp_path, capsys, enc):
    f = tmp_path / "aozora.txt"
    f.write_bytes("吾輩は猫である。名前はまだ無い。\r\n".encode(enc))
    code, out, _ = run(["-w", "16", "--encoding", "auto", str(f)], capsys)
    assert code == 0
    assert out == "吾輩は猫である。\n名前はまだ無い。\n"


def test_cli_per_file(tmp_path, capsys):
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_bytes("あいう\n".encode("cp932"))
    b.write_bytes("かきく\n".encode("euc-jp"))
    code, out, err = run(["--width-of", "--encoding", "AUTO", "-v", str(a), str(b)], capsys)
    assert code == 0
    assert out == "6\n6\n"
    assert err == (
        f"kinsoku: detected encoding: cp932 ({a})\nkinsoku: detected encoding: euc-jp ({b})\n"
    )


@pytest.mark.parametrize("enc", ["cp932", "euc-jp", "utf-8"])
def test_cli_stdin(capsys, monkeypatch, enc):
    set_stdin(monkeypatch, "あいう\n".encode(enc))
    code, out, err = run(["--width-of", "--encoding", "auto", "--verbose"], capsys)
    assert code == 0
    assert out == "6\n"
    assert err == f"kinsoku: detected encoding: {enc} (<stdin>)\n"


def test_cli_stdin_text_stream(capsys, monkeypatch):
    # stdin replaced by a text stream: nothing to detect
    monkeypatch.setattr("sys.stdin", io.StringIO("﻿あいう\n"))
    code, out, err = run(["--width-of", "--encoding", "auto", "-v"], capsys)
    assert code == 0
    assert out == "6\n"
    assert err == ""


def test_cli_no_verbose_is_quiet(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_bytes("あいう\n".encode("cp932"))
    _, _, err = run(["--width-of", "--encoding", "auto", str(f)], capsys)
    assert err == ""


def test_cli_verbose_without_auto_is_quiet(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_bytes("あいう\n".encode("cp932"))
    _, out, err = run(["--width-of", "--encoding", "cp932", "-v", str(f)], capsys)
    assert out == "6\n"
    assert err == ""


def test_cli_default_is_still_utf8(tmp_path, capsys):
    f = tmp_path / "a.txt"
    f.write_bytes("あいう\n".encode("cp932"))
    code, _, err = run_err([str(f)], capsys)
    assert code == 1
    assert "cannot decode as utf-8" in err


def test_cli_undecodable(tmp_path, capsys):
    f = tmp_path / "bad.bin"
    f.write_bytes(b"\x80\xa0\xfd")
    code, out, err = run_err(["--encoding", "auto", str(f)], capsys)
    assert code == 1
    assert out == ""
    assert err == (
        f"kinsoku: error: {f}: cannot detect the encoding "
        "(not UTF-8, cp932 or euc-jp; try --encoding)\n"
    )


def test_cli_undecodable_stdin(capsys, monkeypatch):
    set_stdin(monkeypatch, b"ab\xa0\xfd")
    code, _, err = run_err(["--encoding", "auto"], capsys)
    assert code == 1
    assert err.startswith("kinsoku: error: <stdin>: cannot detect the encoding")


def test_help_mentions_auto_and_verbose(capsys):
    _, out, _ = run_err(["--help"], capsys)
    assert "auto" in out and "--verbose" in out
