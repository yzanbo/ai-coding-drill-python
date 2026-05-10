# 02. Python 環境構築（🔴 未着手）

> **守備範囲**：Python ランタイム取得から apps/api を DB + 品質ゲート付きで動かすまでの 12 ステップ。本フェーズが終わると、Python の lint / typecheck がローカル + CI 両方で緑になり、依存自動更新が週次で来る。各 step は **1 PR 相当の atomic な作業単位**に分割してあり、step 単位で commit / レビューを進められる。
> **前提フェーズ**：[01-foundation.md](./01-foundation.md) 完了済（mise.toml + GitHub Actions 雛形 + Dependabot 雛形）
> **次フェーズ**：[03-nextjs.md](./03-nextjs.md)

---

## 1. Python 最新安定版を調査して pin → mise install

**目的**：Python の最新安定版（stable / GA、RC・beta は不採用）を調査し、`mise.toml` と `README.md` の 2 箇所のみを書き換えて pin 化、そのうえで実体化する。本プロジェクトのバージョン方針（[.claude/CLAUDE.md: バージョン方針](../../../../.claude/CLAUDE.md#バージョン方針)）に従い、**mise.toml に書かれた既存版数に追従するのではなく、毎回その時点の最新安定版を調査してから書き換える**。

**作業内容**：
1. **最新安定版を調査**：[python.org/downloads](https://www.python.org/downloads/) で latest stable の minor 版（例 `3.14.x`）を確認
2. **`mise.toml` を書き換え**：`[tools]` セクションの `python = "<X.Y>"` を最新の minor に更新（`X.Y` のみ pin、patch は mise が解決）
3. **`README.md` を書き換え**：「技術スタック概要」表の言語ランタイム行の Python 版数を同じ minor に更新
4. **`mise install python` を実行**：mise が patch 含む実 binary をダウンロード・展開
5. **`python --version` で動作確認**：`<X.Y>.<patch>` が表示されることを確認

**コマンド例**：
```bash
# 1〜3. 最新安定版を調査して mise.toml と README.md を編集（手作業 or AI assist）
# 4. インストール
mise install python
# 5. 動作確認
python --version  # 例：Python 3.14.4
```

**前提**：[01-foundation.md: 3. mise 導入](./01-foundation.md#3-mise-導入-)（mise CLI が動作）

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

**前提**：本ファイルの「1. Python 最新安定版を調査して pin → mise install」

**関連 ADR**：[ADR 0035](../../../adr/0035-uv-for-python-package-management.md) / [ADR 0020](../../../adr/0020-python-code-quality.md)

---

## 3. docker-compose.yml（Postgres + Redis）配置

**目的**：ローカル開発用ミドルウェアを `docker-compose.yml` 1 ファイルで再現可能にする。**この時点から `docker-compose.yml` が Postgres / Redis 版数の SSoT** — README / 他ドキュメントは具体版数を書かずここを参照する。

**作業内容**：
1. **最新安定版を調査**：[Docker Hub: postgres](https://hub.docker.com/_/postgres) と [Docker Hub: redis](https://hub.docker.com/_/redis) で latest stable の alpine tag（例 `18.3-alpine` / `8.6-alpine`）を確認
2. **ルートに `docker-compose.yml` 配置**：Postgres と Redis のサービス定義、`postgres:<x.y>-alpine` / `redis:<x.y>-alpine` を image に pin、healthcheck を `pg_isready` / `redis-cli ping` で設定、永続ボリュームを宣言
3. **`README.md` を書き換え**：「技術スタック概要」表のデータストア行を最新版数に更新

**完了確認**：
```bash
docker compose up -d                                    # 起動
docker compose ps                                       # postgres / redis が "healthy" になる
docker compose exec postgres psql -U postgres -c "\l"   # データベース一覧（ai_coding_drill が出る）
docker compose exec redis redis-cli ping                # PONG が返る
docker compose down                                     # 停止
```

**前提**：本ファイルの「2. apps/api 環境構築」（apps/api workspace が動く必要はないが、次 step 以降で利用する）

**関連 ADR**：[ADR 0004](../../../adr/0004-postgres-as-job-queue.md) / [ADR 0037](../../../adr/0037-sqlalchemy-alembic-for-database.md)

> **位置づけ**：DB は Worker（R1）も同じスキーマに jobs テーブルを追加する形で参加する共有資源。最初の使用者である Python フェーズに bundle してある。

---

## 4. SQLAlchemy セッション + 設定モジュール

**目的**：FastAPI から Postgres へ async で接続できる最小セットを揃える。`pydantic-settings` ベースの `Settings` で環境変数（`DATABASE_URL` 等）を読み、`AsyncEngine` + `AsyncSession` を生成する。

**作業内容**：
1. `apps/api/app/core/config.py` に `Settings`（pydantic-settings）を定義：`DATABASE_URL` / `REDIS_URL` 等を `.env` 経由で読み取れるように
2. `apps/api/app/db/session.py` に `AsyncEngine` + `async_sessionmaker` + `get_async_session` 依存関数を実装
3. ルート（または `apps/api/`）に `.env.example` を配置（`DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ai_coding_drill` 等）
4. `apps/api/app/main.py` から設定ロードを動作確認（`Settings()` がエラーなくインスタンス化される）

**完了確認**：
```bash
docker compose up -d
cd apps/api && mise exec -- uv run python -c "from app.core.config import Settings; print(Settings())"
```

**前提**：本ファイルの「3. docker-compose.yml 配置」

**関連 ADR**：[ADR 0037](../../../adr/0037-sqlalchemy-alembic-for-database.md)

---

## 5. 最小 SQLAlchemy モデル（health_check テーブル）

**目的**：SQLAlchemy 2.0 の `Mapped[T]` / `mapped_column()` 新スタイル（→ [.claude/rules/alembic-sqlalchemy.md](../../../../.claude/rules/alembic-sqlalchemy.md)）を 1 つ通して、Alembic autogenerate の入力源を作る。

**作業内容**：
1. `apps/api/app/db/base.py` に `class Base(DeclarativeBase)` を定義（全モデルの共通親）
2. `apps/api/app/models/health_check.py` に `HealthCheck` モデル（`id: UUID` / `created_at: TIMESTAMP(timezone=True)`）を定義
3. `apps/api/app/models/__init__.py` で `from app.models.health_check import HealthCheck` を re-export（Alembic が拾えるように）

**完了確認**：
```bash
cd apps/api && mise exec -- uv run python -c "from app.models import HealthCheck; print(HealthCheck.__table__)"
```

**前提**：本ファイルの「4. SQLAlchemy セッション + 設定モジュール」

**関連 ADR**：[ADR 0037](../../../adr/0037-sqlalchemy-alembic-for-database.md)

---

## 6. Alembic init + 初版マイグレーション

**目的**：Alembic を `apps/api/alembic/` に配置し、`HealthCheck` モデルから自動生成した初版マイグレーションを `upgrade head` で適用する。

**設計判断（async 対応）**：app/db/session.py は `postgresql+asyncpg://` の AsyncEngine を使うが、Alembic は autogenerate / online migration を **`async_engine_from_config` 経由の async runner** で実行する（`alembic init -t async` または手動で env.py を async 化）。同期ドライバへの URL 置換（`+asyncpg` → `+psycopg`）は依存追加が増えるため採用しない。

**作業内容**：
1. `cd apps/api && mise exec -- uv run alembic init -t async alembic`（**`-t async` テンプレートを使う**ことで env.py が `async_engine_from_config` ベースで生成される）
2. `apps/api/alembic.ini` の `sqlalchemy.url` を空にし、`apps/api/alembic/env.py` で `get_settings().database_url` から読み込むよう修正
3. `apps/api/alembic/env.py` の `target_metadata` を `app.db.base.Base.metadata` に差し替え（`from app.models import *` も追加して全モデルを autogenerate に拾わせる）
4. `mise exec -- uv run alembic revision --autogenerate -m "create health_check table"` で初版生成
5. 生成された `apps/api/alembic/versions/<hash>_create_health_check_table.py` を目視確認（余計な diff が無いか）
6. `mise exec -- uv run alembic upgrade head` で適用

**完了確認**：
```bash
docker compose up -d
cd apps/api && mise exec -- uv run alembic upgrade head
docker compose exec postgres psql -U postgres ai_coding_drill -c "\dt"   # health_check + alembic_version が表示される
```

**前提**：本ファイルの「5. 最小 SQLAlchemy モデル」

**関連 ADR**：[ADR 0037](../../../adr/0037-sqlalchemy-alembic-for-database.md)

---

## 7. 薄い CRUD エンドポイント + pytest 疎通

**目的**：FastAPI router → SQLAlchemy session → Postgres の経路を end-to-end で 1 周通し、SQLAlchemy + Alembic + asyncpg 運用未経験箇所のつまずきを早期に洗い出す（リスクレジスタ対応）。

**設計判断**：本プロジェクトは backend.md の方針（→ [.claude/rules/backend.md: ディレクトリ構成](../../../../.claude/rules/backend.md#ディレクトリ構成-appsapiapp)）に従い **Service が AsyncSession から SQLAlchemy 2.0 を直接呼ぶ単層構成** を採用する。ただし health_check は trivial（INSERT 1 行 / SELECT 1 行）なので、本 step では **router に直接 SQLAlchemy 操作を書く**（`app/services/` 配置はしない）。実機能（auth / problems / submissions 等）から `app/services/<feature>.py` を導入する運用とする。

**作業内容**：
1. `apps/api/app/routers/health.py` に `POST /health` / `GET /health` を実装：
   - `Depends(get_async_session)` で `AsyncSession` を取得
   - `POST` は `HealthCheck()` を `session.add()` + `session.commit()` + `session.refresh()`、`{id, created_at}` を返す
   - `GET` は `select(HealthCheck).order_by(HealthCheck.created_at.desc()).limit(10)` の結果を返す
2. `apps/api/app/main.py` で `app.include_router(health.router)` 登録
3. `apps/api/tests/test_health.py` に integration テスト：
   - `@pytest.mark.integration` 付き（マーカー宣言は **step 2 の pyproject.toml `[tool.pytest.ini_options]` で済み**）
   - httpx + ASGITransport（in-process 通信、外部 HTTP 不要）で `POST` → `GET` の往復を検証
   - DB は docker-compose の Postgres（`@pytest.fixture` で各テストごとに DELETE で初期化）
4. `mise exec -- uv run pytest -m integration` で疎通確認

**完了確認**：
```bash
docker compose up -d
cd apps/api && mise exec -- uv run alembic upgrade head
mise exec -- uv run pytest -m integration              # health の往復テストがパス
mise exec -- uv run fastapi dev &                      # サーバ起動（mise run api:dev と等価）
curl -X POST http://localhost:8000/health              # 200 OK + {"id": "...", "created_at": "..."}
open http://localhost:8000/docs                        # Swagger UI に POST/GET /health が表示
```

**前提**：本ファイルの「6. Alembic init + 初版マイグレーション」

**関連 ADR**：[ADR 0037](../../../adr/0037-sqlalchemy-alembic-for-database.md) / [ADR 0038](../../../adr/0038-test-frameworks.md)

---

## 8. mise.toml の Python タスク稼働確認

**目的**：[01-foundation.md](./01-foundation.md) で mise.toml に**先回りで定義済み**の `api:*` タスク群が、apps/api の実体（pyproject.toml + uv.lock + app/）が揃ったこの時点で正しく動作することを確認する。

**前提済の登録タスク**（[mise.toml](../../../../mise.toml) の `[tasks."api:*"]`、本 step では追記しない）：
- `api:dev` — FastAPI 開発サーバ（`uv run fastapi dev`）
- `api:test` — `uv run pytest`
- `api:lint` / `api:lint-fix` — `uv run ruff check [.|--fix]`
- `api:format` — `uv run ruff format`
- `api:typecheck` — `uv run pyright`
- `api:audit` — `uv run pip-audit`
- `api:deps-check` — `uv run deptry .`
- `api:db-migrate` / `api:db-revision` — Alembic 操作
- `api:openapi-export` / `api:job-schemas-export` — 型同期パイプライン用（R0 時点ではスクリプト未実装、step 11 以降で整備）

**作業内容**：
1. `mise tasks | grep ^api:` で全 `api:*` タスクが list されることを確認
2. **動作するもの**を順に起動：
   - `mise run api:lint` → `All checks passed!`
   - `mise run api:typecheck` → `0 errors, 0 warnings`
   - `mise run api:test` → 集めたテストが pass（step 7 まで進んでいれば integration テストもパス）
   - `mise run api:db-migrate` → `alembic upgrade head` が no-op で抜ける
3. **動作しないもの**（スクリプト未実装系）：
   - `api:openapi-export` / `api:job-schemas-export` は R0 時点では `scripts/export_*.py` が無いため exit 1。step 11（GitHub Actions）でも CI に組み込まない。後続フェーズで雛形作成

**完了確認**：上記 4 タスクが緑で抜ける。

**関連 ADR**：[ADR 0039](../../../adr/0039-mise-for-task-runner-and-tool-versions.md)

---

## 9. lefthook.yml に Python 用 pre-commit 追加

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

**前提**：本ファイルの「8. mise.toml の Python タスク稼働確認」

---

## 10. lefthook.yml に Python 用 pre-push 追加

**目的**：push 直前に **動的検証（テスト）** を発火させ、pre-commit の静的検査と CI の間にあるギャップを埋める。「commit は緑だが CI で fail する」事故を `git push` の段階で先回りして潰す。

**追記内容**（`pre-push` セクション）：

```yaml
pre-push:
  commands:
    api-pytest:
      glob: "apps/api/**/*.py"
      root: apps/api
      run: mise exec -- uv run pytest
      fail_text: |
        pytest が失敗（push をブロック）。Postgres 未起動が原因なら
          docker compose up -d
          git push
```

**設計判断**：
- **glob で API コード変更時のみ発火**：`apps/api/**/*.py` を絞って、Frontend / Worker / docs のみの push では pytest を起動しない。API コード変更時は **必ず** integration を含むフルテストが走る
- **graceful skip は採用しない**：DB 未起動なら pytest が fail して push をブロックする運用にする。「ローカル緑 = 全テスト通過」の保証を強くしたいため。回避策は単純で `docker compose up -d` の 1 行で済む（→ `fail_text` で誘導）
- **`mise exec --` 経由**：pre-commit と同じ理由（Git フックの非対話シェルに対する shims 解決）
- **integration マーカーで分離**：`apps/api/pyproject.toml` の `[tool.pytest.ini_options]` で **step 2 の時点で** `markers = ["integration: requires running Postgres"]` を宣言済。DB 必要なテストには `@pytest.mark.integration` を付ける運用

**完了確認**：
```bash
# DB 起動状態：pytest フル実行 → 緑で push 通過
docker compose up -d
mise exec -- lefthook run pre-push        # api-pytest 緑

# DB 停止状態：pytest が DB 接続不可で fail → push がブロックされる（期待動作）
docker compose down
mise exec -- lefthook run pre-push        # api-pytest exit 1 + fail_text 表示
```

**前提**：本ファイルの「9. lefthook.yml に Python 用 pre-commit 追加」+「3. docker-compose.yml 配置」

**関連 ADR**：[ADR 0038](../../../adr/0038-test-frameworks.md)

---

## 11. GitHub Actions に Python ジョブ追加

**目的**：[01-foundation.md: 4. GitHub Actions ワークフロー雛形](./01-foundation.md#4-github-actions-ワークフロー雛形-) で整備したワークフローに Python 用ジョブを追加し、hook bypass された逸脱もリモートで弾く。

**追記内容**（[.github/workflows/ci.yml](../../../../.github/workflows/ci.yml)）：
- 新規ジョブ 5 種：`api-lint` / `api-typecheck` / `api-audit` / `api-deps-check` / `api-test`
  - 各ジョブで `actions/checkout` → `jdx/mise-action`（SHA pin、内部で `mise install` 実行）→ `mise run api:<task>`
  - `api-test` のみ Postgres を **GitHub Actions の `services` 機能**で立て、`alembic upgrade head` 後に `pytest`（unit + integration）を実行
- `ci-success` の `needs:` に上記 5 ジョブを追加

**設計判断（`api-test` を CI に含める）**：pre-push hook は `--no-verify` でバイパスされ得るため、CI が **最後の砦**として integration テストも回す。hook と CI の二重防御で「ローカル緑 = 全テスト通過」の保証を hook bypass 時にもリモートで再現する。

**Postgres 版数の同期**：CI の services の `image: postgres:<x.y>-alpine` は `docker-compose.yml` と版数を揃える運用とする（手動同期）。R0 時点では片方を更新したらもう片方も書き換える。後続フェーズで両者を同期する仕組みを検討。

**完了確認**：
- PR を作ると `api-lint` / `api-typecheck` / `api-audit` / `api-deps-check` / `api-test` の 5 ジョブが並列で走る
- いずれかが失敗すると `ci-success` も赤になり、Branch protection で merge がブロックされる

**前提**：本ファイルの「8. mise.toml の Python タスク稼働確認」+「9. lefthook.yml に Python 用 pre-commit 追加」+「10. lefthook.yml に Python 用 pre-push 追加」（CI ジョブは `mise run api:*` を呼ぶため、ローカルでタスクが動くことが必須）

**関連 ADR**：[ADR 0026](../../../adr/0026-github-actions-incremental-scope.md) / [ADR 0031](../../../adr/0031-ci-success-umbrella-job.md) / [ADR 0038](../../../adr/0038-test-frameworks.md)

---

## 12. dependabot.yml に Python（pip）エコシステムを追加

**目的**：apps/api の Python 依存（`apps/api/pyproject.toml` + `apps/api/uv.lock`）を Dependabot の週次自動更新対象に含める。

**追記内容**：[.github/dependabot.yml](../../../../.github/dependabot.yml) の `updates:` 配列に以下のエントリを追加する。

```yaml
updates:
  # … 既存の他エコシステム（github-actions 等）はそのまま …

  - package-ecosystem: pip
    directory: /apps/api
    schedule:
      interval: weekly
      day: monday
      time: "06:00"
      timezone: Asia/Tokyo
    open-pull-requests-limit: 10
    labels:
      - dependencies
      - python
    commit-message:
      prefix: build
      prefix-development: build
      include: scope
    ignore:
      - dependency-name: "*"
        update-types:
          - version-update:semver-major
    groups:
      # FastAPI / Starlette / Pydantic は連動して更新する必要がある
      fastapi:
        patterns:
          - fastapi
          - starlette
          - pydantic
          - pydantic-*
      # SQLAlchemy / Alembic はペアで更新（ADR 0037）
      sqlalchemy:
        patterns:
          - sqlalchemy
          - alembic
```

**各設定値の意図**：

| key | 値 | 意図 |
|---|---|---|
| `package-ecosystem` | `pip` | PEP 621 の `pyproject.toml` 経由で更新（Dependabot は uv.lock を完全には扱えないが、`pyproject.toml` の version 制約を上げる PR は作れる） |
| `directory` | `/apps/api` | monorepo 内の apps/api を対象に限定 |
| `schedule` | `weekly` / `monday` / `06:00 Asia/Tokyo` | 週次・月曜朝の集中レビュー運用 |
| `open-pull-requests-limit` | `10` | レビュー処理量に対する上限 |
| `labels` | `dependencies` / `python` | PR フィルタリング用 |
| `commit-message` | `prefix: build` / `prefix-development: build` / `include: scope` | commit `build(deps): ...` 形式に揃える（commitlint 互換） |
| `ignore` | `*` の `version-update:semver-major` | メジャー更新は破壊的変更を伴うため自動 PR から除外、手動運用（→ [ADR 0028](../../../adr/0028-dependabot-auto-update-policy.md)） |
| `groups.fastapi` | `fastapi` / `starlette` / `pydantic` / `pydantic-*` | FastAPI 系は連動更新が必要なため 1 PR にまとめる |
| `groups.sqlalchemy` | `sqlalchemy` / `alembic` | ORM とマイグレーションはペア更新（→ [ADR 0037](../../../adr/0037-sqlalchemy-alembic-for-database.md)） |

**運用補足**：Dependabot が `pyproject.toml` の version を上げた PR を作成したら、開発者側で `cd apps/api && uv lock --upgrade-package <pkg>` を実行して `uv.lock` を再生成・rebase する。

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
