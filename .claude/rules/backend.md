---
paths:
  - "apps/api/**/*"
---

# バックエンド開発ルール（FastAPI）

FastAPI（Python 3.13）の API サーバ。詳細な選定理由は [ADR 0034](../../docs/adr/0034-fastapi-for-backend.md)。ORM は SQLAlchemy 2.0（async）+ Alembic（→ [ADR 0037](../../docs/adr/0037-sqlalchemy-alembic-for-database.md)）。パッケージ管理は uv（→ [ADR 0035](../../docs/adr/0035-uv-for-python-package-management.md)）、コード品質は ruff + pyright + pip-audit + deptry（→ [ADR 0020](../../docs/adr/0020-python-code-quality.md)）。

## ディレクトリ構成（`apps/api/app/`）

機能別フラット構成（→ [02-architecture.md](../../docs/requirements/2-foundation/02-architecture.md#backend-apifastapi--python)）：

```
apps/api/app/
├── main.py                  # FastAPI アプリ生成 + ルータ束ねる
├── core/                    # 設定 / セキュリティ / 例外ハンドラ等の横断ユーティリティ
│   ├── config.py            # pydantic-settings ベース
│   ├── security.py          # セッション・OAuth ユーティリティ
│   └── exceptions.py        # 共通例外 + handler
├── db/                      # SQLAlchemy エンジン / セッション / シード
├── models/                  # SQLAlchemy モデル（機能別ファイル）
├── schemas/                 # Pydantic モデル（**SSoT、HTTP API + Job キューの両境界に展開**、ADR 0006）
├── routers/                 # APIRouter（機能別、controller 相当）
│   ├── auth.py
│   ├── problems.py
│   ├── submissions.py
│   ├── grading.py
│   └── ...
├── services/                # ビジネスロジック（router から呼ぶ）
├── repositories/            # SQLAlchemy クエリの集約（service から呼ぶ、※下記 Note 参照）
├── deps/                    # 依存性注入（Depends で使う関数群、認証ガード等）
└── observability/           # OpenTelemetry セットアップ、構造化ログ、メトリクス
```

> **Note：Repository レイヤの要否は実装着手時に再判断**（保留）。要件側の SSoT は [02-architecture.md: Backend API 設計スタイル](../../docs/requirements/2-foundation/02-architecture.md#backend-apifastapi--python) で「Repository レイヤは設けない（Service が SQLAlchemy を直接呼ぶ）」と書かれており、本ファイルおよび `backend-new-module` SKILL の Repository 前提と齟齬がある。R1 着手時に決着させて片側に統一する。当面は本ファイルの Service / Repository 2 層構成を「目安」として読み、実装が要件側に寄せて確定したらこの Note を削除する。

### 設計方針

- **「admin/customer」のような分割は採用しない**。同じリソースを扱うエンドポイントが分散しロジックが重複するため
- 認証の有無は `Depends` の差分で制御する。エンドポイントのパス分割ではなく、依存ガードで認証要否を切り替える
- **横断的な部品は責務に近い場所に置く**。例：`get_current_user` は `app/deps/auth.py`、`get_async_session` は `app/deps/db.py`
- 純粋なユーティリティ（共通レスポンスモデル / 定数）は `app/core/` または `app/schemas/common/` に。サービス・ビジネスロジックを `core/` に置いてはならない

### 循環依存の防止

- **モジュール間の依存は一方向に保つ**。A → B かつ B → A の関係を作らない
- 依存の方向：`grading/` → `submissions/`, `problems/` のように上位の業務ロジックが下位のマスタ系を参照する
- 副作用（通知送信等）は FastAPI の `BackgroundTasks` または domain event で発火し、router / service の直接 import を避ける

## API ルートと認証

- REST リソース単位のパス設計（例：`/problems`, `/submissions`, `/auth/github`）
- Swagger UI：`/docs`、Redoc：`/redoc`、OpenAPI 3.1 JSON：`/openapi.json`（FastAPI 自動生成、→ [ADR 0006](../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
- 認証：Authlib + GitHub OAuth、セッションは Cookie + Redis（→ [ADR 0011](../../docs/adr/0011-github-oauth-with-extensible-design.md)）
- 全ルートデフォルト認証必須（`get_current_user` を APIRouter の `dependencies=[Depends(...)]` でグローバル適用）。public は個別 router で `dependencies=[]` 上書き
- レート制限：`slowapi` + Redis ストレージ（Sliding Log 方式、→ [01-non-functional.md](../../docs/requirements/2-foundation/01-non-functional.md)）

## データベース（Postgres + SQLAlchemy 2.0 async）

- AsyncEngine + AsyncSession、Repository / Service レイヤは `async def`
- セッション取得：`session: AsyncSession = Depends(get_async_session)`（リクエスト単位で生成・破棄）
- タイムゾーン：`TIMESTAMP(timezone=True)` で UTC 保持、表示時に JST 変換（zoneinfo）
- IDs：UUID（`server_default=text("gen_random_uuid()")`）または BigInteger（`jobs.id` のみ autoincrement）
- 全テーブルに `created_at`、必要に応じて `updated_at`。**ハードデリート方針**（ソフトデリートは原則使わない、必要なら個別に検討）
- スキーマ定義 / クエリパターン / Alembic 運用の詳細は [.claude/rules/alembic-sqlalchemy.md](./alembic-sqlalchemy.md) と [01-data-model.md](../../docs/requirements/3-cross-cutting/01-data-model.md)

### where 条件の必須ルール

- 認証済みエンドポイントでは「自分のリソースか」を必ずチェックする（例：`Submission.user_id == current_user.id`）
- `col.in_(ids)` を使う前に `len(ids) == 0` を必ずガード

### ページネーションパターン

`PaginationMeta`（`app/schemas/common/pagination.py`）を Pydantic モデルとして定義し、レスポンスに同梱：

```python
from app.schemas.common.pagination import PaginationMeta, Page

return Page[ProblemResponse](
    data=items,
    meta=PaginationMeta(total=total, page=page, limit=limit, last_page=math.ceil(total / limit)),
)
```

## ジョブキュー（Postgres `jobs` テーブル）

- ジョブ投入は `INSERT INTO jobs` + `NOTIFY new_job, <jobId>` を**同一トランザクション**で実行（→ [ADR 0004](../../docs/adr/0004-postgres-as-job-queue.md)）
- ペイロードは JSONB、スキーマは `app/schemas/jobs/<job_type>.py` の Pydantic モデルで定義
- Pydantic から `model.model_json_schema()` で個別 JSON Schema を `apps/api/job-schemas/` に書き出し、Worker 側 quicktype に渡す（→ [ADR 0006](../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
- Worker 側の取得・処理は Go で実装（→ [.claude/rules/worker.md](./worker.md)）

## LLM 呼び出し

**LLM 呼び出しは Worker 側に閉じ込め、Backend は呼ばない**（→ [ADR 0040](../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）：

- 採点 LLM（judge）→ `apps/workers/grading/`
- 問題生成 LLM → `apps/workers/generation/`（将来追加）

Backend の責務はジョブ enqueue + 結果取得 API のみ。`anthropic` / `google-genai` 等の LLM SDK を `apps/api/` 配下に置かない。

## コーディング規約

### コードスタイル

- ruff（lint + format）、設定は `apps/api/pyproject.toml`（→ [ADR 0020](../../docs/adr/0020-python-code-quality.md)）
- 型チェックは pyright（basic で開始、コードが安定したら strict 化を検討）
- **`Any` 利用不可**。SQLAlchemy の `Mapped[T]` / Pydantic モデル / `TypedDict` で型付けする
- import は ruff の `isort` ルールで自動整列。手動整列禁止
- モジュール名（ファイル・パッケージ名）は snake_case、クラス名は PascalCase。テーブル名は複数形のまま

### Router

- ビジネスロジックは Service に委譲する。Router はリクエスト/レスポンスの橋渡しのみ
- 各 router は `APIRouter(prefix="/problems", tags=["problems"])` で prefix + tags を付ける（Swagger グループ化）
- パスパラメータ：UUID は `Annotated[UUID, Path(...)]`、整数は `Annotated[int, Path(ge=1)]`
- レスポンスモデルは `response_model=ProblemResponse` で必ず明示（OpenAPI 出力に効く）
- ステータスコードは `status_code=status.HTTP_201_CREATED` 等を明示

### Pydantic スキーマ（SSoT）

- 命名：`<Model>Create`, `<Model>Update`, `<Model>Response`, `<Model>Query`（DTO の suffix）
- すべての境界（HTTP request / response / Job payload）は `app/schemas/` 配下の Pydantic モデルが SSoT
- `model_config = ConfigDict(from_attributes=True)` で SQLAlchemy モデルから組み立て可能に
- バリデーションは `field_validator` / `model_validator` を使う。ベタな関数バリデータは避ける

### Service

- Repository を呼び出してビジネスロジックを構築。直接 SQLAlchemy を呼ばない（Repository に集約）
- トランザクション境界は Service が握る：`async with session.begin():`
- 認証済みエンドポイントでは「自分のリソースか」を必ずチェック
- エラーは FastAPI の `HTTPException` ではなくドメイン例外を投げ、`app/core/exceptions.py` の handler で HTTPException に変換する
- ロガー：`logger = logging.getLogger(__name__)`（OpenTelemetry が自動で trace_id を注入）

### Repository

- SQLAlchemy のクエリはここに集約（Service から SQLAlchemy を直接触らない）
- 戻り値は SQLAlchemy モデルのまま（Service / Router 側で Pydantic に詰め替える）

## 新規機能の追加パターン

`/backend-new-module` スキルを使うか、手動なら：

1. `apps/api/app/models/<feature>.py` — SQLAlchemy モデル
2. `apps/api/app/schemas/<feature>.py` — Pydantic スキーマ（Create/Update/Response/Query）
3. `apps/api/app/repositories/<feature>.py` — クエリ集約
4. `apps/api/app/services/<feature>.py` — ビジネスロジック
5. `apps/api/app/routers/<feature>.py` — APIRouter
6. `apps/api/app/main.py` で `app.include_router(...)`
7. スキーマ変更があれば `mise run api:db-revision -- "<msg>"` でマイグレーション生成 → `mise run api:db-migrate`

```
apps/api/app/
├── models/problems.py         # class Problem(Base): ...
├── schemas/problems.py        # ProblemCreate / ProblemUpdate / ProblemResponse / ProblemQuery
├── repositories/problems.py   # async def list_problems(...) 等
├── services/problems.py       # ProblemService
└── routers/problems.py        # router = APIRouter(prefix="/problems", tags=["problems"])
```

### モジュール間の依存

- 他モジュールの service を利用する場合は import + `Depends(get_xxx_service)` で取得
- service 側は他 service を import して直接呼ぶ（依存方向を一方向に保つ）

## テスト

- ユニットテスト（`tests/unit/test_*.py`）：pytest + pytest-asyncio。Repository をモックで注入し Service を検証
- 結合テスト（`tests/integration/test_*.py`）：pytest + httpx.AsyncClient + 実 DB（Testcontainers または docker-compose の test 環境）
- E2E（`tests/e2e/`）：実 Postgres + 実 Redis を立てて FastAPI を起動、httpx で叩く
- テスト関数名・docstring は日本語（`test_正常系_問題一覧取得` / `"""異常系: 不正な UUID は 422 を返す"""`）

### E2E テストの実行方法

```bash
docker compose -f docker-compose.test.yml up -d   # 専用 Postgres / Redis を起動
mise run api:test -- tests/e2e/                   # E2E のみ実行
docker compose -f docker-compose.test.yml down -v # 環境破棄
```

## データベース操作

```bash
mise run api:db-migrate                  # alembic upgrade head（未適用 revision を適用）
mise run api:db-revision -- "<msg>"      # alembic revision --autogenerate
```

詳細は [.claude/rules/alembic-sqlalchemy.md](./alembic-sqlalchemy.md)。

## 技術選定

新規コードで使うライブラリ：

- HTTP framework：`fastapi`
- ORM：`sqlalchemy[asyncio]` + `asyncpg`
- マイグレーション：`alembic`
- バリデーション / 設定：`pydantic` + `pydantic-settings`
- 認証：`authlib`（GitHub OAuth）+ `itsdangerous`（セッション署名）
- レート制限：`slowapi`
- 日付操作：標準 `datetime` + `zoneinfo`（必要なら `pendulum`）
- HTTP クライアント：`httpx`（async）
- LLM SDK：使わない（Backend では呼ばない、Worker 側に閉じる、→ ADR 0040）
- メール送信：MVP では不要（R6 以降で必要なら検討）

## ツーリング

| 用途 | ツール | mise タスク |
|---|---|---|
| パッケージ管理 / 仮想環境 | uv | `mise install` で投入、`uv add <pkg>` |
| lint + format | ruff | `mise run api:lint` / `mise run api:format` |
| 型チェック | pyright | `mise run api:typecheck` |
| 脆弱性スキャン | pip-audit | `mise run api:audit` |
| 依存衛生（未使用検出） | deptry | `mise run api:deps-check` |
| テスト | pytest + pytest-asyncio + httpx | `mise run api:test` |
