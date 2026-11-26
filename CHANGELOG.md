# Changelog

## 0.3.0

### ⚠️ 互換性に関わる変更

0.2.0 と同じ入力でも結果が変わるものがあります。アップデートの前に確認してください。

- **対応する Python を 3.10 以上にした**（0.2.0 は 3.8 以上）。3.10〜3.14 でテストしています
- **`wrap` が段落頭の空白（全角の字下げ、半角のインデント）を保持するようになった**（#21、#40）
  - `wrap(" あいう", 10)` → 0.2.0: `['あいう']`、0.3.0: `[' あいう']`
  - 先頭の空白のあとに最初の語が入らないときは、textwrap と同じく空白を捨てる。CLI の折り返しと `--rewrap` も同じ
- **タブを表示幅で展開するようになった**（`wrap`、`width`、`pad`、`truncate`。#29、#41、#40、#42）
  - 各関数に `tabsize`（既定 8）を追加。`width("a\tb")` → 0.2.0: `2`、0.3.0: `9`
  - `pad` と `truncate` はタブを展開した文字列を返す。`char_width("\t")` は 0 のまま
- **引数のチェックを統一した**（#30、#42）
  - `width` / `char_width` / `wrap` / `fill` / `shorten` / `truncate` / `pad` などが、同じ条件で同じメッセージの `ValueError` を出す
  - 0.2.0 では通っていた `ambiguous_width=3`、`pad(text, -1)` もエラーになる。`pad` と `truncate` の幅は 0 以上、それ以外は 1 以上
  - `pad` の `align` は、すき間がなくても検証する。`"<"` `">"` `"^"` も受け付ける
- **`unwrap` / `rewrap` で、和文と英数字の境目にスペースを入れないのを既定にした**（#49、#54）
  - `"Python\nを使う"` → `"Pythonを使う"`。スペースを入れたいときは `cjk_latin_space=True`（CLI は `--cjk-latin-space`）
- **CLI: モードごとに使えないオプションを指定すると、エラー（終了コード 2）にした**（#28、#47、#33、#53）
  - 0.2.0 では黙って無視されていた `kinsoku --truncate -n 2` や `kinsoku --width-of --hanging` がエラーになる。`--truncate` と `--width-of` は同時に使えない
  - `-w 0` はエラー（0.2.0 では既定幅として扱われていた）。ただし `--table -w 0` は「幅の上限なし」（#68）
- **CLI: 複数のファイルを渡すと、末尾に改行のないファイルには改行を補ってからつなぐ**（#26、#33）
  - 0.2.0 では、ファイルの最後の行と次のファイルの最初の行が1行につながっていた
- **CLI: `-w` を省略したときの幅に `COLUMNS` を使う**（#28、#33）
  - 0.2.0 は `COLUMNS` を見ず、端末でなければ 80 だった。0.3.0 は `COLUMNS` → 端末の幅 → 80 の順に使う
- **CLI: 出力時のエラーの終了コード**（#67、#72）
  - `| head` などで出力先が閉じられたときは、何も表示しないで終了コード 141。Ctrl-C は 130。出力のエンコードに失敗したときは 1
- **文字の幅の数え方が変わった**（#23、#38、#44、#55）
  - 絵文字の ZWJ 列・肌の色・国旗・キーキャップ・VS16 つきの文字を1クラスタ、幅 2 として数える（`width("❤️")` → 0.2.0: `1`、0.3.0: `2`。`width("👨‍👩‍👧")` → `6` から `2`）。`wrap` / `truncate` はクラスタの途中で切らない
  - NFD（分解形）のハングルを1音節1クラスタ、幅 2 として数える（0.2.0 では幅 3 など）
- **折り返す位置が変わった**（下の「修正」も参照）
  - 半角カナ・半角約物に禁則を適用した。`wrap("ｱｲｳ｡ｴｵ", 3)` → 0.2.0: `['ｱｲｳ', '｡ｴｵ']`、0.3.0: `['ｱｲ', 'ｳ｡ｴ', 'ｵ']`（#24、#39）
  - 小数・バージョン番号・桁区切り・URL・ファイル名（`3.14`、`v1.2.3`、`1,000`、`https://…`）や、`foo.bar()`、`print(x)` を途中で割らない（#22、#39、#65、#70）
  - 和文の中の半角クォート（`"`、`'`）を、開きは次の文字に、閉じは前の文字にくっつける（#52、#57、#60、#62）。`KinsokuRules` に `quotes` を追加
  - `max_lines` / `shorten` の placeholder を付けるとき、英単語の途中で切らずに単語ごと落とす（textwrap と同じ。#50、#56）
- UTF-8 で読むとき、CLI が入力の先頭の BOM を取り除く（#48、#53）

### 新機能

- `KinsokuWrapper`：`textwrap.TextWrapper` 互換のクラス。`dedent` / `indent` も公開（#7）
- 言語別の禁則ルールのプリセット（`ja` / `strict` / `loose` / `zh-hans` / `zh-hant` / `ko`）と `KinsokuRules`、`PRESETS`。`wrap(..., rules=...)`、CLI の `--rules`（#8）
- `ansi_reflow`：ANSI の色・OSC 8 リンクを行ごとに閉じて次の行で開き直す。`wrap(..., ansi_reflow=True)`、CLI の `--ansi-reflow`（#13）
- ルビ記法（青空文庫・なろう形式）に対応：`wrap(..., ruby=True)`、`ruby_width`、`strip_ruby`、`ruby_to_html`、CLI の `--ruby` / `--ruby-width`（#15）
  - 行に入らないルビ（句読点・括弧と合わせて入らない場合を含む）は、ルビを外して親文字を折り返す（#51、#59、#63、#56、#62、#71）
- `table`：CJK の幅に対応した表の整形。CLI の `--table`、`--delimiter`、`--no-header`、`--style`（#19）
  - 折り返したセルの OSC 8 リンクを行ごとに閉じる（#46、#54）。CLI の `--table` は、`-w` がなければ端末の幅を上限にする（#68、#72）
- `unwrap` / `rewrap`：ハードラップされた文章を段落に戻す・折り返し直す。`indent_marks_paragraph`、CLI の `--unwrap` / `--rewrap` / `--indent-marks-paragraph`（#20）
- `tategaki`：縦書きの表示。CLI の `--tategaki` / `--gap`。絵文字や NFD のハングルは1マスに入れる（#32、#45、#55）
- CLI（#26、#27、#28、#33）
  - 複数のファイルを、ファイルごとに末尾の改行を補ってからつなぐ。`-` で標準入力
  - `--encoding`（例: `--encoding cp932`）、`--placeholder`、`--tabsize`（`--tabsize` は #29、#40）
  - ファイルが見つからない・デコードできないときは、トレースバックではなく `kinsoku: error: ...` を表示する
  - 既定の幅を `COLUMNS` → 端末の幅 → 80 の順に決める
- 型情報（`py.typed`）を同梱した（#5、#61）

### 修正

- 行末・行頭で削った空白にくっついていた ANSI エスケープを捨てずに残す（#16、#40）
- エスケープだけの段落にインデントを付けない（#34、#40）
- `truncate` で、切った位置で開いている SGR と OSC 8 リンクを閉じる。何も開いていなければ `\x1b[0m` を付けない（#25、#37）
- `KinsokuWrapper` で、段落頭の空白のせいで最初の単語が割れないようにした（#31、#37）
- 半角カナの濁点・半濁点（`ﾞ` `ﾟ`）を直前の文字と分けない（#24、#39）
- 英文の閉じていないクォートのあとにある、和文のクォートの開き・閉じを正しく判定する（#60、#62）
- CLI: `--truncate` で `--tabsize` が無視されていたのを直した（#47、#53）

### 性能

- `wrap` と `width` を高速化した（#17）
- 長い英数字の強制分割が2乗の時間になっていたのを、線形にした（20万文字で 57.6 秒 → 0.075 秒。#43、#57）
- `unwrap` / `rewrap` を段落の長さに対して線形時間にした（1MB の1段落の `rewrap` で 35.5 秒 → 0.92 秒。#66、#74）

### 開発

- ベンチマーク（`benchmarks/bench.py`）を追加した（#17、#57、#74）
- hypothesis によるプロパティベースのテストを追加した（#35）
- CI を Python 3.10〜3.14 にした。lint（ruff）と型チェック（`mypy --strict`）のジョブを追加した（#5、#61）
- PyPI への公開を GitHub Actions の Trusted Publishing で行うようにした（`RELEASING.md`、#18）
- バージョンの情報源を `src/kinsoku/__init__.py` の `__version__` だけにした（`pyproject.toml` は dynamic version。#18）
- `pyproject.toml` に `[project.urls]`、`authors`、classifiers を追加し、dev の extra で ruff と mypy のバージョンを固定した（#69）

## 0.2.0

- ANSI escape sequences (SGR colors, OSC 8 hyperlinks) are zero-width and never split
- `strip_ansi()` and `shorten()`
- `initial_indent` / `subsequent_indent` (indent is per paragraph)
- `max_lines` / `placeholder`
- `keep_all` option for space-only breaking (Korean)
- CLI: `--keep-all`, `-i/--indent`, `-s/--subsequent-indent`, `-n/--max-lines`

## 0.1.0

- Initial release: `width`, `char_width`, `wrap`, `fill`, `truncate`, `pad`, CLI
