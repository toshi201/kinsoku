# kinsoku 禁則

**日本語（CJK）をちゃんと折り返す、依存ゼロの Python ライブラリ & CLI。**

Japanese/CJK-aware text wrapping for Python with *kinsoku shori* (禁則処理) and
terminal display-width support. Zero dependencies. [English below](#english).

## なぜ？

標準ライブラリの `textwrap` は日本語が苦手です。

- 全角文字も「幅1」として数えるので、ターミナルで見ると倍の幅になる
- 「。」や「）」が行頭に来たり、「（」が行末に残ったりする
- 長い英単語と日本語が混ざった文を自然に折り返せない

```text
>>> textwrap.wrap(text, 20)          >>> kinsoku.wrap(text, 20)
吾輩は猫である。名前はまだ無い。どこで生   吾輩は猫である。名前
れたかとんと見当がつかぬ。何でも薄暗いじ   はまだ無い。どこで生
めじめした所で「ニャーニャー」泣いていた   れたかとんと見当がつ
事だけは記憶している。                     かぬ。何でも薄暗いじ
                                           めじめした所で
  ↑ 1行が40桁になっている                  「ニャーニャー」泣い
                                           ていた事だけは記憶し
                                           ている。
```

## インストール

```bash
pip install kinsoku
```

## 使い方

```python
import kinsoku

kinsoku.width("日本語abc")             # => 9  (表示幅)
kinsoku.wrap("あいう。えお", 6)          # => ['あい', 'う。え', 'お']   「。」は行頭に来ない
kinsoku.wrap("あいう。えお", 6, hanging=True)  # => ['あいう。', 'えお']  ぶら下げ
kinsoku.fill(text, 40)                 # 改行で結合した文字列
kinsoku.truncate("あいうえお", 6)        # => 'あい…'
kinsoku.pad("名前", 8, "center")         # => '  名前  '  表の整形に

# 段落頭の字下げ、行数制限
kinsoku.wrap("あいうえお\nかきく", 6, initial_indent="\u3000")
# => ['\u3000あい', 'うえお', '\u3000かき', 'く']
kinsoku.wrap("あいうえおかきくけこ", 6, max_lines=2)   # => ['あいう', 'えお…']
kinsoku.shorten("吾輩は猫である。名前はまだ無い。", 10)  # => '吾輩は猫…'

# 色付き文字列（ANSI エスケープ）もそのまま扱える
kinsoku.width("\x1b[31m赤い\x1b[0m文字")   # => 8
kinsoku.strip_ansi("\x1b[31m赤い\x1b[0m")  # => '赤い'

# 韓国語のように単語単位で改行したいとき
kinsoku.wrap("대한민국의 수도는 서울입니다", 12, keep_all=True)
# => ['대한민국의', '수도는', '서울입니다']
```

### オプション

| 引数 | 説明 |
| --- | --- |
| `hanging` | `、。,.` が右端からはみ出すのを許す（ぶら下げ組み） |
| `break_long_words` | 行幅より長い単語を強制的に分割する（既定 `True`） |
| `initial_indent` / `subsequent_indent` | 段落の1行目 / それ以外の行に付けるインデント |
| `max_lines` / `placeholder` | 最大行数。はみ出したら最終行を `placeholder`（既定 `…`）で終える |
| `keep_all` | スペースでだけ改行する（CSS の `word-break: keep-all`。韓国語向け） |
| `ambiguous_width` | East Asian Ambiguous 文字（`○` `△` `→` など）の幅。CJK環境なら `2` |

### CLI

```bash
cat novel.txt | kinsoku -w 40
kinsoku -w 40 --hanging README.txt
kinsoku --truncate -w 20 list.txt   # 各行を…で切り詰め
kinsoku --width-of file.txt          # 各行の表示幅を出力
kinsoku -w 40 -i "　" novel.txt      # 段落頭を全角スペースで字下げ
kinsoku -w 40 -n 3 summary.txt       # 3行まで
kinsoku -w 40 --rules zh-hans cn.txt # 中国語（簡体字）の禁則で折り返す
kinsoku --truncate -w 20 --placeholder ... list.txt  # 省略記号を変更
kinsoku -w 40 --encoding cp932 aozora.txt  # Shift_JIS（青空文庫など）を読む
kinsoku a.txt - b.txt                # - は標準入力。ファイルごとに独立して処理
```

`-w` を省略すると環境変数 `COLUMNS` → 端末幅 → 80 の順で幅を決めます。
`--truncate` と `--width-of` は同時に指定できず、折り返し専用のオプション（`-n` `--hanging` など）と組み合わせるとエラーになります。

## textwrap からの移行

`kinsoku.KinsokuWrapper` は `textwrap.TextWrapper` と同じ引数を受け付ける置き換え用クラスです。
`dedent` / `indent` も `kinsoku` から使えます（`textwrap` のものをそのまま再エクスポート）。

```python
# before
import textwrap
w = textwrap.TextWrapper(width=40, subsequent_indent="  ")
print(w.fill(text))
print(textwrap.indent(textwrap.dedent(doc), "> "))

# after
import kinsoku
w = kinsoku.KinsokuWrapper(width=40, subsequent_indent="  ", placeholder="…")
w.hanging = True                       # 属性は後から変更できる
print(w.fill(text))
print(kinsoku.indent(kinsoku.dedent(doc), "> "))
```

- `placeholder` の既定値は互換性のため textwrap と同じ `" [...]"`。日本語には `"…"` がおすすめ
- `expand_tabs` / `tabsize` は表示幅で計算（全角は2桁）
- `replace_whitespace=True`（既定）では textwrap と同様に改行も空白に置き換わるため、改行は段落区切りになりません。段落を保ちたいときは `replace_whitespace=False`
- 区切り位置の空白は常に削除されます（`drop_whitespace=False` は無効）。`fix_sentence_endings` / `break_on_hyphens` は受け付けますが無視します
- `hanging` / `keep_all` / `ambiguous_width` などの kinsoku 独自オプションはキーワード引数で指定できます

### 縦書き（tategaki）

`kinsoku.tategaki(text, height)` はテキストをターミナル用の縦書きに組みます。1列 `height` マス（1マス = 全角1文字 = 2桁）、列は右から左へ、改行ごとに新しい列になります。

```python
print(kinsoku.tategaki("吾輩は猫である。名前はまだ無い。\n「ニャーニャー」と泣いていた。", 6))
```

```text
い ニ ﹁ だ る 吾
て ャ ニ 無 ︒ 輩
い ｜ ャ い 名 は
た ﹂ ｜ ︒ 前 猫
︒ と 　 　 は で
　 泣 　 　 ま あ
```

```python
print(kinsoku.tategaki("令和8年12月25日", 5, halfwidth="pair"))   # 縦中横
```

```text
月 令
25 和
日 8 
　 年
　 12
```

- 括弧・句読点・長音などは縦書き用の字形に置き換えます（`「」`→`﹁﹂`、`（）`→`︵︶`、`、。`→`︑︒`、`…`→`︙`、`—`→`︱` など）。`ー` は `｜`（U+FF5C）、縦書き形のない `～` `〜` は `≀`（U+2240）で代用します
- 空きマスは全角スペース（U+3000）で埋めるので、どの行も同じ表示幅になります。列間は `gap`（既定 1）個の半角スペース
- 半角英数字は `halfwidth="fullwidth"`（既定）で全角に変換して1マスに1文字、`halfwidth="pair"` で2文字ずつ1マスに入れます（縦中横）
- 禁則：`。」ャ` などは列頭に、`「（` などは列末に来ないよう前後の文字を次の列へ追い出します。`hanging=True`（既定）では `、。，．` を列の下に1マスぶら下げ、そのときは全列が `height + 1` 行になります
- 結合文字・ゼロ幅文字は直前のマスに付け、ANSI エスケープ（色）は取り除きます
- CLI: `kinsoku --tategaki 10 [--gap 2] novel.txt`

### 言語別の禁則ルール

`rules` 引数（CLI は `--rules`）で禁則ルールのプリセットを切り替えられます。

| プリセット | 内容 |
| --- | --- |
| `ja`（既定） | 日本語。`NO_START` / `NO_END` / `HANGABLE` そのもの |
| `strict` | JIS X 4051 寄りの厳格な禁則。小書きの仮名・`ー`・`々` などの繰り返し記号も行頭禁則（現状 `ja` と同じ） |
| `loose` | CSS の `line-break: loose` 相当。小書きの仮名・`ー`・`々ゝヽ`・`〜` などが行頭に来てもよい |
| `zh-hans` | 中国語（簡体字）。`，。！？；：、…` `”’）》】` などが行頭禁則、`“‘（《【` などが行末禁則 |
| `zh-hant` | 中国語（繁体字）。`zh-hans` の規則（`「」『』` を含む）に加えて、小型の句読点 `﹐﹑﹒﹔﹕﹖﹗` などに対応 |
| `ko` | 韓国語。閉じ括弧・句読点（`.,!?)]}` を含む）が行頭禁則、開き括弧が行末禁則。仮名の規則はなし |

```python
kinsoku.wrap("あいッう", 4)                  # => ['あ', 'いッ', 'う']
kinsoku.wrap("あいッう", 4, rules="loose")   # => ['あい', 'ッう']
kinsoku.wrap("他说：“你好，世界。”", 8, rules="zh-hans")
# => ['他说：', '“你好，', '世界。”']

# 独自ルール: プリセットをもとに一部だけ変える（dataclasses.replace と同じ）
from kinsoku import KinsokuRules
ja = KinsokuRules.preset("ja")
rules = ja.replace(no_start=ja.no_start - {"ー"})   # 「ー」の行頭を許す
kinsoku.wrap("あいーう", 4, rules=rules)       # => ['あい', 'ーう']
```

`KinsokuRules(no_start=..., no_end=..., hangable=...)` は frozen な dataclass で、各フィールドには文字列などの文字の集まりを渡せます（`frozenset` に変換されます）。プリセットの一覧は `kinsoku.PRESETS` です。

### 色を行ごとに閉じる（ansi_reflow）

`ansi_reflow=True` にすると、色や装飾（SGR）・OSC 8 ハイパーリンクが有効なまま終わる行の末尾で
いったん閉じ（`\x1b[0m` / `\x1b]8;;\x1b\\`）、次の行の先頭で同じ状態を開き直します。
表のセルや1行ずつパディングして表示する場合でも、色がずれたり背景がはみ出したりしません。
インデントはスタイルの外側に置かれ、装飾のない行はそのままです。

```python
>>> wrap("\x1b[31mあいうえおか\x1b[0m", 6, ansi_reflow=True)
['\x1b[31mあいう\x1b[0m', '\x1b[31mえおか\x1b[0m']
>>> from kinsoku import ansi_reflow   # 折り返し済みの行リストにも使える
```

CLI では `--ansi-reflow`。

### 折り返しを戻す（unwrap / rewrap）

メールやターミナルからコピーした「すでに折り返されている文章」を段落に戻したり、別の幅で折り返し直したりできます。

```python
kinsoku.unwrap("吾輩は猫で\nある。名前\nはまだ無い。")
# => '吾輩は猫である。名前はまだ無い。'
kinsoku.unwrap("The quick\nbrown fox\n\nwell-\nknown")
# => 'The quick brown fox\n\nwell-known'
kinsoku.unwrap("\u3000一段落目の\n文です。\n\u3000二段落目\nです。", indent_marks_paragraph=True)
# => '\u3000一段落目の文です。\n\u3000二段落目です。'
kinsoku.rewrap("吾輩は猫で\nある。名前\nはまだ無い。", 8)
# => '吾輩は猫\nである。\n名前はま\nだ無い。'
```

- 空行（空白だけの行を含む）は段落の区切りとしてそのまま残します
- 改行の前後がどちらも全角（CJK）か、どちらかが `。」（` などの全角約物ならスペースなしで、それ以外はスペース1つで連結します
- 行末が「英字＋`-`」のときはハイフンを残したままスペースなしで連結します（`well-\nknown` → `well-known`）。本物のハイフンと区別できないため、ハイフンを削除することはしません
- `- ` `* ` `・` `1. ` などで始まる箇条書きらしい行は、常に新しい段落とみなします
- `indent_marks_paragraph=True` で、全角スペースや半角スペースで字下げされた行を段落の始まりとみなします（字下げは保持）
- ANSI エスケープは判定では無視し、出力にはそのまま残します。`\r\n` にも対応
- `rewrap(text, width, **kwargs)` は `unwrap` してから段落ごとに折り返します。`hanging` などの `wrap` の引数をそのまま渡せます

```bash
pbpaste | kinsoku --unwrap
kinsoku --rewrap -w 40 mail.txt
kinsoku --rewrap -w 40 --indent-marks-paragraph novel.txt
```

### 表を整形する（table）

CJK が混ざった表を表示幅で揃えます。`max_col_width` や `width`（表全体の幅）を超えるセルは、禁則つきで折り返します。

```python
rows = [
    ["東京", "日本の首都。人口は約1400万人で、世界有数の大都市です。", 1400],
    ["大阪", "「天下の台所」と呼ばれた商業の街。", 275],
    ["NYC", "New York City", 830],
]
print(kinsoku.table(rows, ["都市", "説明", "人口(万)"], width=36,
                    style="grid", align=["left", "left", "right"]))
```

```
┌──────┬────────────────┬──────────┐
│ 都市 │ 説明           │ 人口(万) │
├──────┼────────────────┼──────────┤
│ 東京 │ 日本の首都。人 │     1400 │
│      │ 口は約1400万人 │          │
│      │ で、世界有数の │          │
│      │ 大都市です。   │          │
├──────┼────────────────┼──────────┤
│ 大阪 │ 「天下の台所」 │      275 │
│      │ と呼ばれた商業 │          │
│      │ の街。         │          │
├──────┼────────────────┼──────────┤
│ NYC  │ New York City  │      830 │
└──────┴────────────────┴──────────┘
```

| 引数 | 説明 |
| --- | --- |
| `headers` | 見出し行（省略可） |
| `align` | `"left"`（既定）/ `"right"` / `"center"`、または列ごとのリスト |
| `max_col_width` | 列の最大幅（整数、または列ごとのリスト）。超えるセルは `kinsoku.wrap` で折り返す |
| `width` | 表全体の幅の上限。超える場合は一番広い列から順に（最小4まで）縮めて折り返す |
| `style` | `"simple"`（既定。見出し＋`-` の下線、列間は空白2つ）/ `"grid"`（罫線）/ `"markdown"` / `"plain"` |
| `ambiguous_width` | `2` のとき、罫線文字（`┌─│` は East Asian Ambiguous）を使うとずれるため、`grid` は ASCII の `+-\|` で描く |

- セルは `str()` で文字列にし、`None` は空欄になります。セル内の改行はそのまま複数行になります
- 行ごとに列数が違う場合は、足りないセルを空欄で補います
- ANSI の色付きセルも幅0として揃えます。折り返したセルは行ごとに色をリセットし、罫線に色がにじみません
- `markdown` では `|` をエスケープし、複数行のセルを `<br>` でつなぎます（`width` を指定しても各行の幅は揃いません）
- その他のキーワード引数（`hanging`、`keep_all` など）は `kinsoku.wrap` に渡されます

CLI では `--table` で CSV / TSV を表にします。区切り文字は1行目にタブがあればタブ、なければカンマ（`--delimiter` で指定可）。1行目は見出しとして扱います（`--no-header` で無効）。`-w` を指定すると表全体の幅の上限になります。

```bash
kinsoku --table --style grid -w 60 data.csv
cat data.tsv | kinsoku --table --style markdown
```

### ルビ記法

青空文庫・なろう形式のルビ（`｜漢字《かんじ》` / `漢字《かんじ》`）を `ruby=True` で認識し、
親文字とルビをひとかたまりとして扱います（途中で改行せず、前後の禁則も守ります）。

```python
kinsoku.wrap("あいう漢字《かんじ》。", 8, ruby=True, ruby_width="base")
# => ['あいう', '漢字《かんじ》。']
kinsoku.strip_ruby("｜東京《とうきょう》の漢字《かんじ》")  # => '東京の漢字'
kinsoku.ruby_to_html("漢字《かんじ》")  # => '<ruby>漢字<rt>かんじ</rt></ruby>'
```

- 親文字: `｜`（または半角 `|`）があればそこから `《` まで、なければ直前の漢字の連続（`々〆ヶ〇` を含む）
- `ruby_width="full"`（既定）: 記法をそのまま表示する前提で、`｜《》` とルビも幅に数える
- `ruby_width="base"`: 親文字の幅だけを数える（あとで本物のルビとして描画する場合）
- CLI: `kinsoku -w 40 --ruby [--ruby-width base] novel.txt`

## 仕様

- **行頭禁則**: `、。，．）」』】ー` 小書きの仮名 `ぁぃぅっゃ` `ァィゥッャ` `…・：；々` など
- **行末禁則**: `（「『【〔《“‘` など
- 禁則でつながった塊は、入る行がなければ次の行へ**追い出し**ます
- 塊そのものが行幅より広い場合だけ、禁則を極力守りつつ強制分割します（ベストエフォート）
- 半角スペース・全角スペースは改行可能位置。行末の空白は削除
- 既存の改行はそのまま保持（段落ごとに折り返し）
- 結合文字（`か゚`、`é`）、ゼロ幅文字、絵文字の幅も考慮
- ANSI エスケープ（色・OSC 8 ハイパーリンク）は幅0として扱い、途中で切らない

## 開発

```bash
pip install -e . pytest
pytest
```

---

## English

`kinsoku` wraps text by **display columns** (wide CJK chars count as 2) and
applies Japanese line-breaking rules:

- characters such as `、。」）ー` and small kana never start a line
- opening brackets such as `「（` never end a line
- latin words are kept intact; spaces (including U+3000) are break points
- optional hanging punctuation (`hanging=True`)
- ANSI escape sequences (colors, OSC 8 links) are zero-width and never split
- `initial_indent` / `subsequent_indent`, `max_lines` + `placeholder`
- `keep_all=True` breaks only at spaces (good for Korean)
- `KinsokuWrapper`: a drop-in replacement for `textwrap.TextWrapper` (same
  constructor arguments, mutable attributes, `.wrap()` / `.fill()`); `dedent`
  and `indent` are re-exported from `textwrap`
- `tategaki(text, height)`: vertical (top-to-bottom, right-to-left) layout for
  terminals with vertical presentation forms, kinsoku and hanging punctuation
  (CLI: `--tategaki HEIGHT`)
- `rules=` selects a kinsoku preset (`ja` (default), `strict`, `loose`,
  `zh-hans`, `zh-hant`, `ko`; CLI `--rules`) or takes a custom
  `KinsokuRules(no_start, no_end, hangable)`, e.g.
  `KinsokuRules.preset("ja").replace(...)`
- `ansi_reflow=True` closes active colors / OSC 8 links at each line end and
  reopens them on the next line (also `ansi_reflow(lines)`, CLI `--ansi-reflow`)
- `unwrap()` joins hard-wrapped lines back into paragraphs (no space between CJK
  characters, one space for latin text, blank lines kept); `rewrap(text, width)`
  unwraps and wraps again. CLI: `--unwrap`, `--rewrap`
- `table(rows, headers)` renders aligned tables (styles `simple`, `grid`, `markdown`, `plain`) with kinsoku wrapping inside cells, a `width` budget, per-column `align` and ANSI-safe cells; `kinsoku --table` formats CSV/TSV input
- `ruby=True` keeps ruby notation (`｜漢字《かんじ》`, `漢字《かんじ》`) unbroken;
  `ruby_width="full"` (default) or `"base"`; plus `strip_ruby` / `ruby_to_html`

API: `width`, `char_width`, `strip_ansi`, `wrap`, `fill`, `shorten`, `truncate`, `pad`,
`KinsokuWrapper`, `dedent`, `indent`, `tategaki`, `KinsokuRules`, `PRESETS`, `ansi_reflow`, `unwrap`, `rewrap`, `table`,
`strip_ruby`, `ruby_to_html`.
CLI: `kinsoku -w N [FILE...]` (`-` = stdin; width defaults to `$COLUMNS`/terminal/80;
`--encoding cp932` for Shift_JIS input; `--placeholder` for `--truncate` / `-n`).

License: MIT
