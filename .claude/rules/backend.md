---
paths:
  - "apps/api/**/*"
---

# バックエンド開発ルール（FastAPI）

FastAPI（Python、版数 SSoT は [mise.toml](../../mise.toml)）の API サーバ。詳細な選定理由は [ADR 0034](../../docs/adr/0034-fastapi-for-backend.md)。ORM は SQLAlchemy 2.0（async）+ Alembic（→ [ADR 0037](../../docs/adr/0037-sqlalchemy-alembic-for-database.md)）。パッケージ管理は uv（→ [ADR 0035](../../docs/adr/0035-uv-for-python-package-management.md)）、コード品質は ruff + pyright + pip-audit + deptry（→ [ADR 0020](../../docs/adr/0020-python-code-quality.md)）。

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
├── services/                # ビジネスロジック + 認可 + Pydantic 詰め替え（DB クエリは repositories/ に委譲、ADR 0044）
├── repositories/            # SQLAlchemy クエリ実装（ORM オブジェクトを返す、ADR 0044）
├── deps/                    # 依存性注入（Depends で使う関数群、認証ガード等）
└── observability/           # OpenTelemetry セットアップ、構造化ログ、メトリクス
```

> **Repository レイヤを採用**（[ADR 0044](../../docs/adr/0044-backend-repository-pattern-adoption.md) が SSoT）。Router → Service → Repository → ORM の 3 層分離。Repository は SQLAlchemy クエリの実装に責務を限定し、ORM オブジェクトを返す。Service はビジネスロジック + 認可チェック + トランザクション境界 + Pydantic 詰め替えに責務を限定し、SQLAlchemy を直接触らない。ROI 観点では本 Backend は薄い責務（auth + CRUD + job enqueue + 結果取得）で Repository が delegating wrapper になりがちだが、**ポートフォリオで設計パターンの理解を可視化する**判断で ROI を上書きしている（→ [01-roadmap.md: ビジョン](../../docs/requirements/5-roadmap/01-roadmap.md#ビジョン変わらない北極星)）。テスト戦略は「Service の単体テスト（Repository を `AsyncMock` でスタブ化）+ Repository の結合テスト（実 DB で SQL 挙動を検証）」を組み合わせる（→ [ADR 0038](../../docs/adr/0038-test-frameworks.md) / [ADR 0044](../../docs/adr/0044-backend-repository-pattern-adoption.md)）。

### 設計方針

- **「admin/customer」のような分割は採用しない**。同じリソースを扱うエンドポイントが分散しロジックが重複するため
- 認証の有無は `Depends` の差分で制御する。エンドポイントのパス分割ではなく、依存ガードで認証要否を切り替える
- **横断的な部品は責務に近い場所に置く**。例：`get_current_user` は `app/deps/auth.py`、`get_async_session` は `app/deps/db.py`
- 純粋なユーティリティ（共通レスポンスモデル / 定数）は `app/core/` または `app/schemas/common/` に。サービス・ビジネスロジックを `core/` に置いてはならない

### レイヤ間の import 方向

新規機能を追加する時、各レイヤから何を import してよいかを下記の表で固定する。全ての機能実装はこの契約に従う。

#### 各レイヤの import 可 / 禁止

| レイヤ | import してよい | import 禁止 |
|---|---|---|
| `routers/` | `services` / `schemas` / `deps` / `core` | `models` / `db` / `repositories` を直接（health_check のような trivial ケースは明示的例外） |
| `services/` | `repositories` / 他の `services` / `schemas` / `models`（型注釈のみ）/ `core` | `routers` / `deps` / `main` / `db` を直接（DB クエリは repositories 経由、→ [ADR 0044](../../docs/adr/0044-backend-repository-pattern-adoption.md)） |
| `repositories/` | `models` / `db` / `core` | `services` / `routers` / `schemas` / `deps` |
| `deps/` | `services` / `db` / `core` | `routers` / `main` |
| `schemas/` | `core` のみ | 上位レイヤ全て |
| `models/` | `db.base` / `core` | 上位レイヤ全て |
| `db/` | `core` | 上位レイヤ全て |
| `core/` | （何も import しない、終端） | 全て |
| `observability/` | `core`（設定値の参照のみ） | 業務レイヤ全て |

#### 補足ルール

- **依存は一方向**：A → B かつ B → A を作らない。`services/` 内の機能間も同じ（例：`grading` → `submissions` の向きに揃え、逆向き import を作らない）
- **副作用は直接 import で繋がない**：通知・発火等は FastAPI の `BackgroundTasks` または domain event 経由で起動し、別 router / service を直接 import しない
- **`schemas/` を終端に保つ**：TS / Go への型生成（[ADR 0006](../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）の境界を壊さないため、`schemas/` から業務レイヤを import しない

#### OK / NG 例

```python
# ✅ OK: routers は services 経由で DB に触れる（services が repository を呼ぶ）
# app/routers/problems.py
from app.services.problems import ProblemService
from app.schemas.problems import ProblemResponse
from app.deps.auth import get_current_user
```

```python
# ✅ OK: services が repository を呼んで ORM を取り、schemas に詰め替える
# app/services/problems.py
from app.repositories.problems import ProblemRepository
from app.schemas.problems import ProblemResponse


class ProblemService:
    def __init__(self, session):
        self.session = session
        self.repo = ProblemRepository(session)         # Repository を保持

    async def get_by_id(self, id_):
        obj = await self.repo.get_by_id(id_)           # クエリは repository に委譲
        return ProblemResponse.model_validate(obj)     # Pydantic 詰め替えは service の責務
```

```python
# ❌ NG: routers が models / db / repositories を直接触る（trivial 例外を除く）
# app/routers/problems.py
from app.models.problems import Problem                # NG
from app.db.session import get_async_session           # NG（取得は deps/db.py 経由）
from app.repositories.problems import ProblemRepository # NG（DB アクセスは services 経由、ADR 0044）
```

```python
# ❌ NG: services が SQLAlchemy を直接呼ぶ（DB クエリは repository に切り出す、ADR 0044）
# app/services/problems.py
from sqlalchemy import select
from app.models.problems import Problem


class ProblemService:
    async def list_all(self):
        stmt = select(Problem)                         # NG（self.repo.list_all() を呼ぶ）
        result = await self.session.execute(stmt)      # NG
```

```python
# ❌ NG: services が routers / deps を import（逆流）
# app/services/problems.py
from app.routers.submissions import router           # NG
from app.deps.auth import get_current_user           # NG（current_user は引数で受け取る）
```

```python
# ❌ NG: repositories が schemas / services を import（境界違反、ADR 0044）
# app/repositories/problems.py
from app.schemas.problems import ProblemResponse     # NG（戻り値は ORM、変換は service）
from app.services.problems import ProblemService     # NG（逆流）
```

```python
# ❌ NG: schemas が業務レイヤを import（終端違反、型生成の境界が壊れる）
# app/schemas/problems.py
from app.services.problems import ProblemService     # NG
from app.models.problems import Problem              # NG（from_attributes は型情報を必要としない）
```

## API ルートと認証

- REST リソース単位のパス設計（例：`/problems`, `/submissions`, `/auth/github`）
- Swagger UI：`/docs`、Redoc：`/redoc`、OpenAPI 3.1 JSON：`/openapi.json`（FastAPI 自動生成、→ [ADR 0006](../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
- 認証：Authlib + GitHub OAuth、セッションは Cookie + Redis（GitHub OAuth 採用は → [ADR 0011](../../docs/adr/0011-github-oauth-with-extensible-design.md)、Cookie + Redis セッションストアの採用根拠（JWT / Postgres セッションテーブル不採用の比較含む）は → [ADR 0047](../../docs/adr/0047-session-store-on-redis.md)）
- 全ルートデフォルト認証必須（`get_current_user` を APIRouter の `dependencies=[Depends(...)]` でグローバル適用）。public は個別 router で `dependencies=[]` 上書き
- レート制限：`slowapi` + Redis ストレージ（Sliding Log 方式、→ [01-non-functional.md](../../docs/requirements/2-foundation/01-non-functional.md)）

## データベース（Postgres + SQLAlchemy 2.0 async）

- AsyncEngine + AsyncSession、Service レイヤは `async def`
- セッション取得：`session: Annotated[AsyncSession, Depends(get_async_session)]`（リクエスト単位で生成・破棄、`Depends()` を default 引数に置く旧スタイルは ruff の B008 違反のため禁止）
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

- `AsyncSession` を `__init__` で受け取り、対応する `<Feature>Repository` を `self.repo = <Feature>Repository(session)` でインスタンス化する
- **SQLAlchemy を直接呼ばない**：クエリ実装は Repository に委譲、Service は Repository メソッドを呼ぶ（→ [ADR 0044](../../docs/adr/0044-backend-repository-pattern-adoption.md)）
- トランザクション境界は Service が握る：`async with session.begin():` ブロック内で Repository メソッドを呼ぶ
- SQLAlchemy モデル（Repository から受け取った ORM オブジェクト）から Pydantic レスポンスへの詰め替えは Service 内で行う（`<Args>Response.model_validate(obj)`）
- 認証済みエンドポイントでは「自分のリソースか」を必ずチェック（`Submission.user_id == current_user.id` を Repository メソッドの引数として渡すか、Service 側で取得後にガード）
- エラーは FastAPI の `HTTPException` ではなくドメイン例外を投げ、`app/core/exceptions.py` の handler で HTTPException に変換する
- ロガー：`logger = logging.getLogger(__name__)`（OpenTelemetry が自動で trace_id を注入）。観測性スタック（Loki / Tempo / Prometheus + Sentry）の構成は [ADR 0041](../../docs/adr/0041-observability-stack-grafana-and-sentry.md) を参照

### Repository

- `AsyncSession` を `__init__` で受け取る（Service が DI で渡す）
- SQLAlchemy 2.0 のクエリ（`select` / `insert` / `update` / `delete` + `await session.execute(...)`）の実装に責務を限定
- **戻り値は ORM オブジェクト**（`Problem` / `list[Problem]` 等）。Pydantic への詰め替えは Service が行う
- **ビジネスロジック・トランザクション制御・Pydantic 変換は持たない**（持つと Service との責務分離が崩れる）
- 1 集約 1 ファイル：`app/repositories/<feature>.py`、クラス名は `<Feature>Repository`（命名は本ファイル §コーディング規約 の命名規則に準拠）
- 複雑な JOIN・eager loading（`selectinload` / `joinedload`）・パフォーマンスチューニングも Repository に集約する
- 詳細な選定根拠とトレードオフは [ADR 0044](../../docs/adr/0044-backend-repository-pattern-adoption.md) を参照

## 新規機能の追加パターン

`/backend-new-module` スキルを使うか、手動なら：

1. `apps/api/app/models/<feature>.py` — SQLAlchemy モデル
2. `apps/api/app/schemas/<feature>.py` — Pydantic スキーマ（Create/Update/Response/Query）
3. `apps/api/app/repositories/<feature>.py` — Repository（SQLAlchemy クエリ集約、ORM オブジェクトを返す、→ [ADR 0044](../../docs/adr/0044-backend-repository-pattern-adoption.md)）
4. `apps/api/app/services/<feature>.py` — Service（Repository を呼ぶ、ビジネスロジック + 認可 + Pydantic 詰め替え）
5. `apps/api/app/routers/<feature>.py` — APIRouter
6. `apps/api/app/main.py` で `app.include_router(...)`
7. スキーマ変更があれば `mise run api:db-revision -- "<msg>"` でマイグレーション生成 → `mise run api:db-migrate`

```
apps/api/app/
├── models/problems.py         # class Problem(Base): ...
├── schemas/problems.py        # ProblemCreate / ProblemUpdate / ProblemResponse / ProblemQuery
├── repositories/problems.py   # ProblemRepository（SQLAlchemy クエリを集約、ORM を返す）
├── services/problems.py       # ProblemService（Repository を呼ぶ、Pydantic 詰め替え）
└── routers/problems.py        # router = APIRouter(prefix="/problems", tags=["problems"])
```

### モジュール間の依存

- 他モジュールの service を利用する場合は import + `Depends(get_xxx_service)` で取得
- service 側は他 service を import して直接呼ぶ（依存方向を一方向に保つ）

## テスト

- ユニットテスト（`tests/unit/test_*.py`）：pytest + pytest-asyncio。**Service の単体テストでは Repository を `AsyncMock` でスタブ化**してビジネスロジック分岐（バリデーション・計算・分岐・認可・Pydantic 詰め替え）を網羅。Repository を明示的なインタフェース境界として置く設計のため、モックでも false positive を生まない（→ [ADR 0044](../../docs/adr/0044-backend-repository-pattern-adoption.md)）
- 結合テスト（`tests/integration/test_*.py`）：pytest + httpx.AsyncClient + 実 DB（Testcontainers または docker-compose の test 環境）。**Repository は実 DB に対して SQL 挙動を検証**、Router レベルは実 Service / 実 Repository / 実 DB で動作確認
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
