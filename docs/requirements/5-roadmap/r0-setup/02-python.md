# 02. Python 環境構築（🔴 未着手）

> **守備範囲**：Python ランタイム取得から apps/api を DB + 品質ゲート付きで動かすまでの 7 ステップ。本フェーズが終わると、Python の lint / typecheck がローカル + CI 両方で緑になり、依存自動更新が走り始める。
> **前提フェーズ**：[01-foundation.md](./01-foundation.md) 完了済（mise.toml + GitHub Actions 雛形 + Dependabot 雛形）
> **次フェーズ**：[03-nextjs.md](./03-nextjs.md)

---

## 1. mise install python

**目的**：[01-foundation.md: 3. mise 導入](./01-foundation.md#3-mise-導入-) の `mise.toml` で pin 済の Python（具体版数の SSoT は [mise.toml](../../../../mise.toml)）を実体化する。

**コマンド**：
```bash
mise install python
```

**完了確認**：
```bash
python --version  # mise.toml で pin した版数が表示される
```

**前提**：[01-foundation.md: 3. mise 導入](./01-foundation.md#3-mise-導入-)（mise.toml に `python = "<最新安定版>"` が pin されている）

**関連 ADR**：[ADR 0039](../../../adr/0039-mise-for-task-runner-and-tool-versions.md)

---

## 2. apps/api 環境構築

**目的**：`uv` で apps/api workspace を初期化し、FastAPI 雛形と静的検査ツールを揃える。**この時点から `apps/api/pyproject.toml` + `apps/api/uv.lock` が Python 依存版数（FastAPI / Pydantic / SQLAlchemy / ruff / pyright 等）の SSoT** — README / 他ドキュメントに具体版数を重複記載しない。

**作業内容**：
1. `uv init apps/api`（workspace 初期化、`pyproject.toml` + `uv.lock` 生成）
2. FastAPI 雛形作成（`apps/api/app/main.py` 等の最小構成。FastAPI / uvicorn / Pydantic / SQLAlchemy / Alembic / asyncpg を `uv add` で導入。**版数は最新安定版を採用、以降の SSoT は `apps/api/pyproject.toml`**）
3. 静的検査ツールを `uv add --dev` で導入：ruff / pyright / pip-audit / deptry（同上、版数 SSoT は `pyproject.toml`）
4. `apps/api/pyproject.toml` の `[tool.ruff]` `[tool.pyright]` に最低限の設定を記述

**完了確認**：
```bash
cd apps/api && uv sync                # lockfile に従って同期
uv run ruff check .                   # ruff が動く
uv run pyright .                      # pyright が動く
```

**前提**：本ファイルの「1. mise install python」

**関連 ADR**：[ADR 0035](../../../adr/0035-uv-for-python-package-management.md) / [ADR 0020](../../../adr/0020-python-code-quality.md)

---

## 3. DB 基盤

**目的**：Postgres + Redis をローカルで立て、SQLAlchemy 2.0 (async) + Alembic 初版で薄い CRUD を 1 周通す。リスクレジスタの「SQLAlchemy + Alembic 運用未経験箇所での詰まり」を早期に洗い出す。

**作業内容**：
1. ルートに `docker-compose.yml` 配置（Postgres + Redis、最新安定版を image tag に pin。**この時点から `docker-compose.yml` が版数の SSoT** — README / 他ドキュメントは具体版数を書かずここを参照する）
2. `apps/api/app/db/session.py` で `AsyncSession` セットアップ（`postgresql+asyncpg://...`）
3. `apps/api/app/models/` に SQLAlchemy 2.0 モデル定義（最低 1 テーブル、例：health_check）
4. `alembic init` + 初版マイグレーション生成 + `alembic upgrade head`
5. 薄い CRUD エンドポイントを 1 つ作って `pytest` で疎通確認

**完了確認**：
```bash
docker compose up -d                                  # Postgres + Redis 起動
cd apps/api && uv run alembic upgrade head            # マイグレーション適用
docker compose exec postgres psql -U postgres -c "\dt"  # テーブル作成確認
```

**前提**：本ファイルの「2. apps/api 環境構築」

**関連 ADR**：[ADR 0004](../../../adr/0004-postgres-as-job-queue.md) / [ADR 0037](../../../adr/0037-sqlalchemy-alembic-for-database.md)

> **位置づけ**：DB は Worker（R1）も同じスキーマに jobs テーブルを追加する形で参加する共有資源。最初の使用者である Python フェーズに bundle してある。

---

## 4. mise.toml に Python タスク追記

**目的**：apps/api 配下のツール起動経路を `mise run api:*` に統一する。

**追記するタスク（最低限）**：
- `api:dev` — FastAPI 開発サーバ（`uvicorn --reload`）
- `api:test` — `uv run pytest`
- `api:lint` — `uv run ruff check .`
- `api:format` — `uv run ruff format .`
- `api:typecheck` — `uv run pyright .`
- `api:audit` — `uv run pip-audit`
- `api:deps-check` — `uv run deptry .`
- `api:db-migrate` — `uv run alembic upgrade head`
- `api:db-revision -- "<msg>"` — `uv run alembic revision --autogenerate -m "<msg>"`
- `api:openapi-export` — FastAPI から `apps/api/openapi.json` を書き出し（型同期パイプライン構築フェーズで本格使用、R0 では雛形のみ）

**完了確認**：
```bash
mise tasks | grep api:
mise run api:lint   # ruff が起動
```

**関連 ADR**：[ADR 0039](../../../adr/0039-mise-for-task-runner-and-tool-versions.md)

---

## 5. lefthook.yml に Python 用 pre-commit 追加

**目的**：ローカル commit 時に Python の lint / typecheck を自動発火させ、規約逸脱を hook で弾く。

**追記内容**：
- `pre-commit` セクションに以下を追加：
  - `ruff-check`：ステージ済 `*.py` に `mise exec -- ruff check --fix` を実行（`stage_fixed: true`）
  - `pyright`：ステージ済 `*.py` に `mise exec -- pyright` を実行
- `mise exec --` 経由で起動する理由は [lefthook.yml の commit-msg 設定コメント](../../../../lefthook.yml) と同じ（Git フックの非対話シェルに対する shims 解決）

**完了確認**：
```bash
echo "x: int = 'string'" > apps/api/app/_test.py     # 型エラーを仕込む
git add apps/api/app/_test.py && git commit -m "test"  # pre-commit が exit 1 で止まる
git restore --staged apps/api/app/_test.py && rm apps/api/app/_test.py
```

**前提**：本ファイルの「4. mise.toml に Python タスク追記」

---

## 6. lefthook.yml に Python 用 pre-push 追加

**目的**：push 直前に **動的検証（テスト）** を発火させ、pre-commit の静的検査と CI の間にあるギャップを埋める。「commit は緑だが CI で fail する」事故を `git push` の段階で先回りして潰す。

**追記内容**（`pre-push` セクション）：

```yaml
pre-push:
  commands:
    pytest:
      run: |
        if pg_isready -h localhost -p 5432 -q; then
          mise exec -- pytest apps/api
        else
          echo "⚠ Postgres not running. Skipping integration tests (run 'docker compose up -d' first)."
          mise exec -- pytest apps/api -m "not integration"
        fi
```

**設計判断**：
- **DB graceful skip**：Postgres が立っていない場合は integration テストをスキップして unit テストのみ実行。spurious fail を回避（DB 起動忘れで push がブロックされない）
- **`mise exec --` 経由**：pre-commit と同じ理由（Git フックの非対話シェルに対する shims 解決）
- **integration マーカーで分離**：`apps/api/pyproject.toml` の `[tool.pytest.ini_options]` で `markers = ["integration: requires running Postgres"]` を宣言し、DB 必要なテストには `@pytest.mark.integration` を付ける運用とする

**完了確認**：
```bash
# DB 起動状態でのフル実行
docker compose up -d && git push   # pre-push 通過

# DB 停止状態での graceful skip 確認
docker compose down && git push    # integration スキップで通過
```

**前提**：本ファイルの「5. lefthook.yml に Python 用 pre-commit 追加」+「3. DB 基盤」（pg_isready が使える）

**関連 ADR**：[ADR 0038](../../../adr/0038-test-frameworks.md)

---

## 7. GitHub Actions に Python ジョブ追加

**目的**：[01-foundation.md: 4. GitHub Actions ワークフロー雛形](./01-foundation.md#4-github-actions-ワークフロー雛形-) で整備したワークフローに Python 用ジョブを追加し、hook bypass された逸脱もリモートで弾く。

**追記内容**（[.github/workflows/ci.yml](../../../../.github/workflows/ci.yml)）：
- 新規ジョブ：`api-lint`、`api-typecheck`、`api-audit`、`api-deps-check`
  - 各ジョブで `mise install` → `mise run api:<task>` を実行
  - `actions/checkout` + `jdx/mise-action` を SHA ピン止めで使用
- `ci-success` の `needs:` に上記 4 ジョブを追加

**完了確認**：
- PR を作ると `api-lint` 〜 `api-deps-check` が走る
- いずれかが失敗すると `ci-success` も赤になり、Branch protection で merge がブロックされる

**前提**：本ファイルの「5. lefthook.yml に Python 用 pre-commit 追加」+「6. lefthook.yml に Python 用 pre-push 追加」（ローカル品質ゲートが緑）

**関連 ADR**：[ADR 0026](../../../adr/0026-github-actions-incremental-scope.md) / [ADR 0031](../../../adr/0031-ci-success-umbrella-job.md)

---

## 8. dependabot.yml の `pip` コメントアウト解除

**目的**：apps/api の Python 依存（`apps/api/pyproject.toml` + `apps/api/uv.lock`）を Dependabot の週次自動更新対象に含める。

**作業内容**（[.github/dependabot.yml](../../../../.github/dependabot.yml)）：
- `pip` ブロックのコメントアウトを解除
- `directory: /apps/api` を指定
- `version-update:semver-major` を `ignore` に追加（メジャー更新は手動運用、→ [ADR 0028](../../../adr/0028-dependabot-auto-update-policy.md)）

**完了確認**：
- 翌週月曜 06:00 JST に `build(deps)` / `build(deps-dev)` の自動 PR が生成される
- もしくは GitHub UI から `Insights → Dependency graph → Dependabot` で手動 trigger で確認

**関連 ADR**：[ADR 0028](../../../adr/0028-dependabot-auto-update-policy.md)

---

## このフェーズ完了時点で揃うもの

- 🟢 apps/api が `mise run api:dev` で起動し、`/docs`（Swagger UI）が見える
- 🟢 Postgres + Redis がローカルで立ち、薄い CRUD が DB 経由で動く
- 🟢 ruff / pyright / pip-audit / deptry がローカル + CI 両方で動く
- 🟢 規約違反コミットが pre-commit hook で弾かれる
- 🟢 Python 依存の自動更新 PR が週次で来る

次は [03-nextjs.md](./03-nextjs.md) で apps/web を同じパターンで構築する。
