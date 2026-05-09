---
name: backend-implement
description: 要件 .md を読み込んで FastAPI を実装する
argument-hint: "[feature-name] (例: problem-generation, grading)"
---

# 要件ベースのバックエンド実装

引数 `$ARGUMENTS` を機能名として解釈する。

## 手順

### 1. 要件の読み込み

- 機能要件：`docs/requirements/4-features/$ARGUMENTS.md`
- ベース要件：[01-overview.md](../../../docs/requirements/1-vision/01-overview.md)、[02-architecture.md](../../../docs/requirements/2-foundation/02-architecture.md)、[01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md)、[02-api-conventions.md](../../../docs/requirements/3-cross-cutting/02-api-conventions.md)
- 関連 ADR：[docs/adr/](../../../docs/adr/)
- バックエンドルール：[.claude/rules/backend.md](../../rules/backend.md)、[.claude/rules/alembic-sqlalchemy.md](../../rules/alembic-sqlalchemy.md)

ファイルが存在しない場合は、ユーザーに `/new-requirements` で先に作成することを提案する。

### 2. 現状の確認

- 要件のステータスチェックボックスを確認
- 関連する既存コード（router / service / repository / SQLAlchemy モデル / Pydantic スキーマ）を確認
- HTTP API 境界の artifact（`apps/api/openapi.json`）と Job キュー境界の artifact（`apps/api/job-schemas/`）の生成状況を確認（→ [ADR 0006](../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
- 要件に対して未実装の部分を特定する

### 3. 実装方針の提示

要件に基づいて実装方針をユーザーに提示する：

- 変更するファイルの一覧
- 新規作成するファイルの一覧
- スキーマ変更の有無（Alembic マイグレーション必要か）
- ジョブキュー（jobs テーブル）への影響
- LLM 呼び出しは Worker 側に閉じる（→ [ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）。Backend は enqueue + 結果取得のみ
- 実装の順序（モデル → Pydantic スキーマ → repository → service → router → テスト）

ユーザーの承認を待ってから実装に着手する。

### 4. 実装

[.claude/rules/backend.md](../../rules/backend.md) のコーディング規約に従って実装する。重要なポイント：

- ディレクトリ構成：機能別フラット（`apps/api/app/{models,schemas,repositories,services,routers}/<feature>.py`）
- async I/O 必須：`AsyncSession` + `async def`
- SQLAlchemy 2.0 新スタイル（`Mapped[T]` / `mapped_column()`）、1.x スタイル禁止
- Pydantic スキーマが SSoT。Router の `response_model` を必ず明示し、OpenAPI 出力を確実にする
- ジョブ投入はトランザクショナルに（`async with session.begin():` 内で `INSERT submissions` + `INSERT jobs` + `NOTIFY new_job`）
- エラーは `app/core/exceptions.py` の handler 経由で HTTPException に変換、メッセージは日本語
- `Any` 禁止、SQLAlchemy `Mapped[T]` / Pydantic / `TypedDict` で型付け

### 5. スキーマ変更時の手順

1. `apps/api/app/models/<feature>.py` の SQLAlchemy モデルを修正
2. `mise run api:db-revision -- "<msg>"` でマイグレーション雛形生成（autogenerate）
3. 生成された `apps/api/alembic/versions/<rev>_<slug>.py` を確認、autogenerate 拾い漏れ（インデックス rename / 拡張 / データ移行）を手で補完
4. 適用：`mise run api:db-migrate`
5. [01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md) の ER 図・テーブル定義も更新

詳細は [.claude/rules/alembic-sqlalchemy.md](../../rules/alembic-sqlalchemy.md)。

### 6. 共有 artifact 変更時

- HTTP API 境界（FastAPI ルートの追加・変更）→ `mise run api:openapi-export` で `apps/api/openapi.json` を更新 → Web 側は `mise run web:types-gen` で TS / Zod / HTTP クライアントを再生成
- Job キュー境界（`app/schemas/jobs/*.py` の Pydantic）→ `mise run api:job-schemas-export` で `apps/api/job-schemas/*.json` を更新 → Worker 側は `mise run worker:types-gen` で Go struct を再生成
- 詳細は [ADR 0006](../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)
- 新規プロンプトは Worker 配下（`apps/workers/<name>/prompts/*.yaml`、→ [ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md) / [.claude/rules/prompts.md](../../rules/prompts.md)）

### 7. ステータス更新

実装完了後、`docs/requirements/4-features/$ARGUMENTS.md` のステータスチェックボックスを更新する：

```markdown
## ステータス
- [x] 要件定義完了
- [x] バックエンド実装完了    ← ここをチェック
- [ ] フロントエンド実装完了
- [ ] 採点 Worker 実装完了
- [ ] テスト完了
```

### 8. 動作確認

- `mise run api:typecheck` で pyright エラーなし
- `mise run api:lint` で ruff 警告なし
- `mise run api:audit` で pip-audit 検出なし
- `mise run api:deps-check` で deptry 警告なし
- ローカルで Swagger UI（http://localhost:8000/docs）から手動疎通確認

問題があれば修正してから完了とする。
