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
```

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

API: `width`, `char_width`, `strip_ansi`, `wrap`, `fill`, `shorten`, `truncate`, `pad`,
`KinsokuWrapper`, `dedent`, `indent`.
CLI: `kinsoku -w N [FILE...]`.

License: MIT
