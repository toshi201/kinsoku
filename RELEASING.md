# リリース手順

kinsoku は GitHub Actions（`.github/workflows/release.yml`）から PyPI の
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/)（OIDC）で公開します。
API トークンは使いません。

## バージョンの管理

バージョンの情報源は `src/kinsoku/__init__.py` の `__version__` だけです。
`pyproject.toml` は `dynamic = ["version"]` と `[tool.hatch.version]` でこの値を読み込みます。

## 通常のリリース

1. `src/kinsoku/__init__.py` の `__version__` を新しいバージョン（例: `0.3.0`）に上げる
2. `CHANGELOG.md` に新しいバージョンの節を追加する
3. 上記をプルリクエストにして `main` にマージし、CI が通ることを確認する
4. GitHub の Releases から新しいリリースを作成する
   - タグ: `vX.Y.Z`（例: `v0.3.0`。`__version__` と一致させる）
   - ターゲット: `main`
   - リリースノートには `CHANGELOG.md` の該当節を貼る
5. 「Publish release」を押すと `release: published` イベントで Release ワークフローが走り、
   テスト → ビルド（sdist / wheel、`twine check`）→ PyPI への公開 が行われる
6. https://pypi.org/project/kinsoku/ で新しいバージョンが公開されたことを確認する

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
