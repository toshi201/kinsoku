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
```

### オプション

| 引数 | 説明 |
| --- | --- |
| `hanging` | `、。,.` が右端からはみ出すのを許す（ぶら下げ組み） |
| `break_long_words` | 行幅より長い単語を強制的に分割する（既定 `True`） |
| `ambiguous_width` | East Asian Ambiguous 文字（`○` `△` `→` など）の幅。CJK環境なら `2` |

### CLI

```bash
cat novel.txt | kinsoku -w 40
kinsoku -w 40 --hanging README.txt
kinsoku --truncate -w 20 list.txt   # 各行を…で切り詰め
kinsoku --width-of file.txt          # 各行の表示幅を出力
```

## 仕様

- **行頭禁則**: `、。，．）」』】ー` 小書きの仮名 `ぁぃぅっゃ` `ァィゥッャ` `…・：；々` など
- **行末禁則**: `（「『【〔《“‘` など
- 禁則でつながった塊は、入る行がなければ次の行へ**追い出し**ます
- 塊そのものが行幅より広い場合だけ、禁則を極力守りつつ強制分割します（ベストエフォート）
- 半角スペース・全角スペースは改行可能位置。行末の空白は削除
- 既存の改行はそのまま保持（段落ごとに折り返し）
- 結合文字（`か゚`、`é`）、ゼロ幅文字、絵文字の幅も考慮

## 開発

```bash
pip install -e . pytest
pytest
```

Issue / PR 大歓迎です！

---

## English

`kinsoku` wraps text by **display columns** (wide CJK chars count as 2) and
applies Japanese line-breaking rules:

- characters such as `、。」）ー` and small kana never start a line
- opening brackets such as `「（` never end a line
- latin words are kept intact; spaces (including U+3000) are break points
- optional hanging punctuation (`hanging=True`)

API: `width`, `char_width`, `wrap`, `fill`, `truncate`, `pad`. CLI: `kinsoku -w N [FILE...]`.

License: MIT
