# apps/api

Python / FastAPI バックエンド。**実装着手前の skeleton**。

## 役割（[ADR 0034](../../docs/adr/0034-fastapi-for-backend.md) / [ADR 0040](../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）

- 認証（GitHub OAuth、[ADR 0011](../../docs/adr/0011-github-oauth-with-extensible-design.md)）
- 問題 CRUD
- ジョブ enqueue（採点ジョブ / 問題生成ジョブを Postgres に登録、[ADR 0004](../../docs/adr/0004-postgres-as-job-queue.md)）
- **LLM 呼び出しは行わない**（Worker 側に集約、[ADR 0040](../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）

## 実装着手時に揃えるもの

- `pyproject.toml`（uv 管理、[ADR 0035](../../docs/adr/0035-uv-for-python-package-management.md)）
- `app/`（FastAPI アプリ本体、Pydantic SSoT は `app/schemas/`、機能別フラット構成は [.claude/rules/backend.md](../../.claude/rules/backend.md) と [02-architecture.md](../../docs/requirements/2-foundation/02-architecture.md#backend-apifastapi--python)、[ADR 0006](../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
- `alembic/`（マイグレーション、`apps/api/alembic/` 直下、[ADR 0037](../../docs/adr/0037-sqlalchemy-alembic-for-database.md)）
- `tests/`（pytest + httpx、[ADR 0038](../../docs/adr/0038-test-frameworks.md)）
- `openapi.json`（FastAPI 自動生成、HTTP API 境界の Frontend 向け型生成 SSoT、[ADR 0006](../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
- `job-schemas/`（Pydantic `model.model_json_schema()` 出力、Job キュー境界の Worker 向け型生成 SSoT、[ADR 0006](../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）

## 起動

`mise run api:dev` 等は実装着手後に有効化される（タスク定義は [mise.toml](../../mise.toml) に既記載）。
