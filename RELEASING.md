# リリース手順

kinsoku は GitHub Actions（`.github/workflows/release.yml`）から PyPI の
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/)（OIDC）で公開します。
API トークンは使いません。

## バージョンの管理

バージョンの情報源は `src/kinsoku/__init__.py` の `__version__` だけです。
`pyproject.toml` は `dynamic = ["version"]` と `[tool.hatch.version]` でこの値を読み込みます。

## 通常のリリース

1. `src/kinsoku/__init__.py` の `__version__` を新しいバージョン（例: `0.3.0`）に上げる。
   `pyproject.toml` のバージョンは書き換えない（dynamic version なので自動で追従する）
2. `CHANGELOG.md` に新しいバージョンの節を追加する
   - 前のリリースのあとに `main` にマージされたプルリクエストを、漏れなく見直す
     （例: `git log --oneline v0.2.0..main`）
   - 「互換性に関わる変更」を先頭に書き、続けて「新機能」「修正」「性能」「開発」に分ける。
     各項目には issue かプルリクエストの番号を付ける
   - 同じ入力で結果が変わるもの（折り返す位置・幅・エラーになる条件・CLI の終了コードなど）は、
     バグ修正であっても「互換性に関わる変更」に書く
3. 上記をプルリクエストにして `main` にマージし、CI が通ることを確認する
4. GitHub の Releases から新しいリリースを作成する
   - タグ: `vX.Y.Z`（例: `v0.3.0`）。「Choose a tag」で新しいタグを入力して作成する
   - ターゲット: `main`
   - リリースノートには `CHANGELOG.md` の該当節を貼る
5. 「Publish release」を押すと `release: published` イベントで Release ワークフローが走り、
   テスト → ビルド（タグと `__version__` の一致の確認、sdist / wheel、`twine check --strict`）
   → PyPI への公開 が行われる
   - タグが `v` + `__version__` と一致しないときは、ビルドの段階で失敗して公開されない
   - `pypi` environment に「Required reviewers」を設定している場合は、
     Actions の画面で承認すると公開に進む
6. https://pypi.org/project/kinsoku/ で新しいバージョンが公開されたことを確認し、
   `pip install -U kinsoku` と `kinsoku --version` で動作を確かめる

公開に失敗したときは、原因を直したうえで Actions の画面から失敗したジョブを再実行する
（PyPI に同じバージョンを2回アップロードすることはできないので、一度公開に成功したバージョンは
作り直せない。直すときはバージョンを上げる）。

## TestPyPI への試験公開

Actions タブで「Release」ワークフローを選び、「Run workflow」（`workflow_dispatch`）を実行すると
TestPyPI に公開されます。同じバージョンは一度しかアップロードできないため、
TestPyPI で何度も試す場合はバージョンを変えてください。

```sh
pip install --index-url https://test.pypi.org/simple/ kinsoku
```

## ローカルでのビルド確認

```sh
python -m venv .tmp/venv
.tmp/venv/bin/pip install build twine
.tmp/venv/bin/python -m build --outdir .tmp/dist
.tmp/venv/bin/twine check --strict .tmp/dist/*
```

`kinsoku-X.Y.Z.tar.gz` と `kinsoku-X.Y.Z-py3-none-any.whl` ができ、X.Y.Z が `__version__` と一致することを確かめる。
別の venv に wheel を入れて、`kinsoku --version` が新しいバージョンになることも確かめるとよい。

```sh
python -m venv .tmp/check
.tmp/check/bin/pip install .tmp/dist/kinsoku-*.whl
.tmp/check/bin/kinsoku --version
```

## 初回のみ必要な設定

### 1. GitHub の environment を作成する

リポジトリの Settings → Environments で次の 2 つを作成します。

- `pypi`
- `testpypi`

`pypi` には「Required reviewers」を設定し、公開前に承認を挟むことを推奨します。
また「Deployment branches and tags」でタグ `v*` のみに制限するとより安全です。

### 2. PyPI に Trusted Publisher を登録する

プロジェクトがまだ PyPI に存在しない場合は「pending publisher」として登録します
（既に存在する場合はプロジェクトの Manage → Publishing から登録します）。

1. https://pypi.org/manage/account/publishing/ を開く
2. 「Add a new pending publisher」の GitHub タブで次を入力する

   | 項目 | 値 |
   | --- | --- |
   | PyPI Project Name | `kinsoku` |
   | Owner | `toshi201` |
   | Repository name | `kinsoku` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

### 3. TestPyPI に Trusted Publisher を登録する

TestPyPI は PyPI とは別アカウントです。
https://test.pypi.org/manage/account/publishing/ で同様に pending publisher を登録します。

| 項目 | 値 |
| --- | --- |
| PyPI Project Name | `kinsoku` |
| Owner | `toshi201` |
| Repository name | `kinsoku` |
| Workflow name | `release.yml` |
| Environment name | `testpypi` |

pending publisher は最初の公開に成功した時点で通常の Trusted Publisher に切り替わります。
