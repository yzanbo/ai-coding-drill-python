---
paths:
  - "apps/api/alembic/**/*"
  - "apps/api/app/db/**/*"
  - "apps/api/app/models/**/*"
---

# SQLAlchemy 2.0 + Alembic ルール（Postgres）

DB は Postgres、ORM は **SQLAlchemy 2.0（async）**、マイグレーションは **Alembic**。

- ジョブキューを Postgres に乗せる判断 → [ADR 0004](../../docs/adr/0004-postgres-as-job-queue.md)
- ORM / マイグレーションを SQLAlchemy + Alembic に確定した判断 → [ADR 0037](../../docs/adr/0037-sqlalchemy-alembic-for-database.md)

## ファイル構成（`apps/api/`）

```
apps/api/
├── alembic/
│   ├── versions/             # マイグレーション本体（Python ファイル、適用済みは削除禁止）
│   ├── env.py                # SQLAlchemy metadata と Alembic を接続
│   └── script.py.mako        # マイグレーションテンプレート
├── alembic.ini               # Alembic 設定
└── app/
    ├── db/
    │   ├── base.py           # `Base = declarative_base()` / `metadata` 定義
    │   ├── session.py        # AsyncEngine / AsyncSession ファクトリ
    │   └── seeds/            # シードデータ投入スクリプト
    └── models/               # SQLAlchemy モデル（機能別ファイル）
        ├── jobs.py
        ├── problems.py
        └── ...
```

## 採用方針

- **SQLAlchemy 2.0 系の新スタイル**（`Mapped[...]` / `mapped_column()`）を使う。1.x スタイル（`Column(...)` 直書き）は新規コードでは禁止
- **async I/O 必須**：`AsyncEngine` + `AsyncSession`、Repository / Service レイヤは `async def`
- セッションは FastAPI の依存性注入（`Depends(get_async_session)`）で取得、リクエスト単位で生成・破棄

## モデル定義のパターン

```python
# apps/api/app/models/jobs.py
from datetime import datetime
from sqlalchemy import BigInteger, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    queue: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String, nullable=False, server_default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    run_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    locked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String)
    last_error: Mapped[str | None] = mapped_column(String)
    result: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=text("NOW()")
    )
```

## クエリパターン（async）

```python
from sqlalchemy import select, update, delete, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.problems import Problem
from app.models.submissions import Submission
from app.models.jobs import Job


# SELECT 1 件
result = await session.execute(select(Problem).where(Problem.id == problem_id))
problem = result.scalar_one_or_none()

# SELECT 一覧（リレーション同時取得）
stmt = select(Problem).options(selectinload(Problem.submissions))
problems = (await session.execute(stmt)).scalars().all()

# INSERT（flush で生成 ID 確定）
new_submission = Submission(...)
session.add(new_submission)
await session.flush()
submission_id = new_submission.id

# UPDATE
await session.execute(
    update(Job)
    .where(Job.id == job_id)
    .values(state="running", locked_at=datetime.now(timezone.utc))
)

# DELETE
await session.execute(delete(Submission).where(Submission.id == submission_id))

# COUNT
count = await session.scalar(select(func.count()).select_from(Problem))

# トランザクショナル enqueue（解答 INSERT + ジョブ INSERT + NOTIFY）
async with session.begin():
    submission = Submission(...)
    session.add(submission)
    await session.flush()
    session.add(Job(type="grade", payload={"submission_id": str(submission.id)}, state="queued"))
    await session.execute(text("NOTIFY new_job, :id").bindparams(id=str(submission.id)))

# SKIP LOCKED でジョブ取得（参考、実際は Go ワーカー側で実行）
stmt = (
    select(Job)
    .where(Job.state == "queued", Job.run_at <= datetime.now(timezone.utc))
    .order_by(Job.run_at)
    .limit(1)
    .with_for_update(skip_locked=True)
)
```

### where 条件の必須ルール

- 認証済みエンドポイントでは「自分のリソースか」をチェックする（例：`Submission.user_id == current_user.id`）
- `col.in_(ids)` を使う前に `len(ids) == 0` を必ずガードする（空リストは Postgres 側で `IN ()` の構文エラーを誘発）

## カラム命名規則

| サフィックス | 型 | 用途 | 例 |
|---|---|---|---|
| `_at` | `TIMESTAMP(timezone=True)` | 日時 | `created_at`, `updated_at`, `graded_at`, `locked_at` |
| `_id` | UUID / BIGINT FK | 外部キー | `user_id`, `problem_id`, `submission_id` |

- ID は UUID（`server_default=text("gen_random_uuid()")`）、ジョブのみ `BigInteger` autoincrement
- 日時は **`TIMESTAMP(timezone=True)` で UTC**、表示時に JST 変換（zoneinfo / pendulum）
- 状態カラム：`state`（マシン的、`jobs.state`）/ `status`（ユーザー視点、`submissions.status`）を使い分け
- JSON カラム：`JSONB` を使う、ペイロードのスキーマは Pydantic で定義し `apps/api/job-schemas/` に JSON Schema として書き出す（→ [ADR 0006](../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）

## Alembic マイグレーション

### スキーマ変更時の手順

1. `apps/api/app/models/` のモデルを修正
2. `mise run api:db-revision -- "<変更内容の要約>"` でマイグレーション雛形を生成（autogenerate）
3. 生成された `apps/api/alembic/versions/<rev>_<slug>.py` を確認し、必要なら手で修正（autogenerate が拾えない `CREATE EXTENSION` / `CREATE INDEX CONCURRENTLY` 等を補う）
4. `mise run api:db-migrate` でマイグレーション適用
5. 生成された Python ファイルを git にコミット（適用済みファイルの編集・削除は禁止）

### autogenerate の限界

Alembic の autogenerate は以下を**検出しない**ため手動補完が必要：

- インデックス名の rename
- `CHECK` 制約の rename
- 列の型変更（一部のみ）
- 関数・ビュー・拡張（`CREATE EXTENSION`）
- データマイグレーション（`UPDATE ... SET ...`）

### コンフリクト発生時

マージ時に `alembic/versions/` でコンフリクトが発生した場合：

1. **`*.py` ファイル**：ファイル名（`<rev>_<slug>.py`）が異なるためファイル単位ではコンフリクトしない
2. **`down_revision`** が同じ親を指して分岐する場合は、`alembic merge heads -m "merge"` で merge revision を生成
3. すでに適用済みの revision ファイルは削除しない

## Postgres 固有の機能

### `jobs` テーブル

ジョブキュー実装の中核（→ [01-data-model.md](../../docs/requirements/3-cross-cutting/01-data-model.md)、[ADR 0004](../../docs/adr/0004-postgres-as-job-queue.md)）。

- `id BIGSERIAL` — その他のテーブルが UUID を使うのに対し、ジョブだけ数値 ID（処理順序を直感的に扱うため）
- `payload JSONB` — ジョブごとのデータ。スキーマは Pydantic で定義し `apps/api/job-schemas/` に JSON Schema として書き出す
- インデックス：`(queue, state, run_at)` — ワーカーの取得クエリ高速化に必須

### `LISTEN/NOTIFY`

FastAPI が `INSERT INTO jobs` と同じトランザクションで `NOTIFY new_job, '<jobId>'` を発火する。Go ワーカー側が `LISTEN` で受信。

```python
from sqlalchemy import text

async with session.begin():
    session.add(Job(...))
    await session.flush()
    await session.execute(text("NOTIFY new_job, :id").bindparams(id=str(job.id)))
```

### `pgvector` 拡張（R7）

将来的に RAG・重複検出を実装する際に有効化（→ [01-data-model.md: 将来拡張の想定](../../docs/requirements/3-cross-cutting/01-data-model.md)）。Alembic マイグレーションで明示的に有効化：

```python
def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
```

## トランザクション分離レベル

- 既定：`READ COMMITTED`（Postgres デフォルト）
- ジョブ取得（`SELECT FOR UPDATE SKIP LOCKED`）は既定で問題なし
- 厳密な整合性が必要な集計等：`SERIALIZABLE` を AsyncEngine 接続単位で指定

```python
from sqlalchemy.ext.asyncio import async_sessionmaker

engine_serializable = engine.execution_options(isolation_level="SERIALIZABLE")
SessionSerializable = async_sessionmaker(bind=engine_serializable, expire_on_commit=False)
```

## マイグレーション操作コマンド（mise）

タスク命名は `<scope>:<sub>:<verb>` 階層コロン形式（→ [ADR 0039](../../docs/adr/0039-mise-for-task-runner-and-tool-versions.md)）：

```bash
mise run api:db-migrate                 # alembic upgrade head（未適用 revision を全適用）
mise run api:db-revision -- "<msg>"     # alembic revision --autogenerate -m "<msg>"
```

その他の Alembic 直接操作（必要時のみ）：

```bash
cd apps/api
uv run alembic downgrade -1             # 1 つ前に戻す（ローカル限定、本番禁止）
uv run alembic history                  # revision 履歴表示
uv run alembic current                  # 現在の revision 確認
uv run alembic merge heads -m "merge"   # 分岐した head を統合
```

## 既存 revision ファイルの編集

- 適用済みの revision は原則編集しない
- ただし、本番環境への反映前なら追記が許容される（例：インデックス追加忘れ）
- 適用後は新しい revision を追加する

## ローカル DB の初期化（全データリセット）

```bash
docker compose exec postgres dropdb -U postgres ai_coding_drill
docker compose exec postgres createdb -U postgres ai_coding_drill
mise run api:db-migrate
# シードは別途スクリプト：cd apps/api && uv run python -m app.db.seeds
```

## シードデータの管理

- シードは `apps/api/app/db/seeds/` に配置（Python スクリプト）
- 開発に必要な最小限のデータ：カテゴリマスタ、テスト問題数件、テストユーザー
- 投入順序は FK 依存順
- 本番環境への投入は別途運用手順で対応（シードと本番データを分離）
