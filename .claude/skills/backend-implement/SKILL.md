---
name: backend-implement
description: 要件 .md を読み込んで NestJS API を実装する
argument-hint: "[feature-name] (例: problem-generation, grading)"
---

# 要件ベースのバックエンド実装

引数 `$ARGUMENTS` を機能名として解釈する。

## 手順

### 1. 要件の読み込み

- 機能要件：`docs/requirements/4-features/$ARGUMENTS.md`
- ベース要件：[01-overview.md](../../../docs/requirements/1-vision/01-overview.md)、[02-architecture.md](../../../docs/requirements/2-foundation/02-architecture.md)、[01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md)、[02-api-conventions.md](../../../docs/requirements/3-cross-cutting/02-api-conventions.md)
- 関連 ADR：[docs/adr/](../../../docs/adr/)
- バックエンドルール：[.claude/rules/backend.md](../../rules/backend.md)、[.claude/rules/drizzle.md](../../rules/drizzle.md)

ファイルが存在しない場合は、ユーザーに `/new-requirements` で先に作成することを提案する。

### 2. 現状の確認

- 要件のステータスチェックボックスを確認
- 関連する既存コード（コントローラ、サービス、スキーマ）を確認
- 共有スキーマ `packages/shared-types/schemas/` と Zod 型生成状況を確認
- 要件に対して未実装の部分を特定する

### 3. 実装方針の提示

要件に基づいて実装方針をユーザーに提示する：

- 変更するファイルの一覧
- 新規作成するファイルの一覧
- スキーマ変更の有無（Drizzle マイグレーション必要か）
- LLM プロバイダ抽象化への影響（→ [ADR 0007](../../../docs/adr/0007-llm-provider-abstraction.md)）
- ジョブキュー（jobs テーブル）への影響
- 実装の順序（スキーマ → サービス → コントローラ → DTO → テスト）

ユーザーの承認を待ってから実装に着手する。

### 4. 実装

[.claude/rules/backend.md](../../rules/backend.md) のコーディング規約に従って実装する。重要なポイント：

- Module 構成：機能別フラット（`apps/api/src/<feature>/`）
- DI / Module / Guard / Interceptor によるレイヤード設計
- Drizzle クエリ：リレーショナルクエリ（`db.query.*`）と CRUD（`db.insert/update/delete`）を使い分け
- ジョブ投入はトランザクショナルに（INSERT submissions + INSERT jobs + NOTIFY）
- LLM 呼び出しは `LlmProvider` 抽象化レイヤ経由
- エラーは NestJS 組み込み例外、メッセージは日本語
- `any` 禁止、Drizzle 推論型（`typeof table.$inferSelect`）を使う

### 5. スキーマ変更時の手順

1. `apps/api/src/drizzle/schema/` を修正
2. `pnpm db:generate` でマイグレーション SQL 生成
3. 生成 SQL を確認してコミット
4. `pnpm db:migrate` で適用
5. [01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md) の ER 図・テーブル定義も更新

### 6. 共有スキーマ・プロンプト変更時

- 新規ジョブタイプ追加 → `packages/shared-types/schemas/job.schema.json` 更新 + 型再生成
- 新規プロンプト → `packages/prompts/<role>/*.yaml` 追加（→ [.claude/rules/prompts.md](../../rules/prompts.md)）

### 7. ステータス更新

実装完了後、`docs/requirements/4-features/$ARGUMENTS.md` のステータスチェックボックスを更新する：

```markdown
## ステータス
- [x] 要件定義完了
- [x] バックエンド実装完了    ← ここをチェック
- [ ] フロントエンド実装完了
- [ ] 採点ワーカー実装完了
- [ ] テスト完了
```

### 8. 動作確認

- `pnpm typecheck` で型エラーがないこと
- `pnpm lint` で Biome の警告がないこと
- ローカルで Swagger UI（http://localhost:3001/api/docs）から手動疎通確認

問題があれば修正してから完了とする。
