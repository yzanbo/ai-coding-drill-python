---
paths:
  - "apps/api/drizzle/**/*"
  - "apps/api/src/drizzle/**/*"
---

# Drizzle マイグレーションルール（Postgres）

DB は Postgres、ORM は Drizzle。

- ジョブキューを Postgres に乗せる判断 → [ADR 0004](../../docs/adr/0004-postgres-as-job-queue.md)
- ORM に Drizzle を採用した判断（Prisma 不採用） → [ADR 0017](../../docs/adr/0017-drizzle-orm-over-prisma.md)

## 採用バージョンの確定タイミング（実装着手時に必ず実施）

[ADR 0017](../../docs/adr/0017-drizzle-orm-over-prisma.md) 起票時点（2026-05-03）で Drizzle は **v1.0 stable 未到達**（npm `latest` は v0.45.x、v1.0 は RC 段階）。**1.0 ベータ・RC 期間中に複数の破壊的変更**（`.enableRLS()` 廃止、casing API リワーク等）が発生しているため、実装着手時に以下を必ず実施する。

### チェックリスト

- [ ] 実装着手時点の **Drizzle 最新 stable バージョン**を [npm](https://www.npmjs.com/package/drizzle-orm) と [公式リリースノート](https://orm.drizzle.team/docs/latest-releases) で確認
- [ ] **採用バージョンを決定**：以下のいずれか
  - **v1.0 stable がリリース済み** → v1.x 系で着手（推奨：直近マイナーを固定）
  - **v1.0 stable 未リリース** → v0.45.x 系（npm `latest`）で着手し、v1.0 stable 到達後に移行 ADR を起票して切替
  - **判断が割れる場合**は本 ADR の「将来の見直しトリガー」に該当 → 新規 ADR で記録
- [ ] 採用バージョンを `package.json` に **`^` ではなく具体バージョン**で固定（例：`"drizzle-orm": "0.45.2"` または `"1.0.0"`）
- [ ] 同様に `drizzle-kit` のバージョンも固定（drizzle-orm と互換性のあるマイナーに揃える）
- [ ] [05-runtime-stack.md: データベース](../../docs/requirements/2-foundation/05-runtime-stack.md#データベース) に採用バージョンを追記
- [ ] メジャー更新（v1 → v2 等）時は移行 ADR を起票してから着手

### 破壊的変更への対応方針

- v0.x → v1.0 を含むメジャー更新は**専用ブランチで対応**（`feature/api/drizzle-vX-migration` 等）
- 公式の Migration Guide を読んでから着手、自己判断で API を書き換えない
- 移行作業は ADR で記録（理由・代替案・所要時間）

## ファイル構成

- `apps/api/drizzle/*.sql` — マイグレーション SQL（適用済みのものは削除禁止）
- `apps/api/drizzle/meta/*.json` — スナップショット（手動編集禁止）
- `apps/api/drizzle/meta/_journal.json` — マイグレーション履歴
- `apps/api/src/drizzle/schema/` — スキーマ定義（TypeScript）
- `apps/api/src/drizzle/seeds/` — シードデータ
- `apps/api/drizzle.config.ts` — Drizzle Kit 設定

## スナップショットの操作ルール

**`meta/*.json` は手動編集禁止。必ず `db:generate` で生成・更新する。**

スナップショットに問題が生じた場合も、パッチではなく再生成で対処する。

## コンフリクト発生時の手順

マージ時に `drizzle/` 配下でコンフリクトが発生した場合：

1. **`*.sql`**：ファイル名が異なるためコンフリクトしない（そのまま両方残す）
2. **`_journal.json`**：両ブランチの `entries` を `idx` 昇順に手動マージする（数行の作業）
3. **`meta/*.json`**：行単位のマージ禁止。`git checkout --ours` または `--theirs` でどちらか一方を丸ごと採用する
4. `pnpm db:generate` を実行する
   - 差分が出た場合 → 採用しなかった側の変更が新規マイグレーションとして生成される（正しい挙動）
   - `No schema changes, nothing to migrate` → 完了
5. すでに適用済みの SQL ファイルは削除しない

## Postgres 固有の機能

### `jobs` テーブル

ジョブキュー実装の中核（→ [01-data-model.md](../../docs/requirements/3-cross-cutting/01-data-model.md)、[ADR 0004](../../docs/adr/0004-postgres-as-job-queue.md)）。

- `id BIGSERIAL` — その他のテーブルが UUID を使うのに対し、ジョブだけ数値 ID（処理順序を直感的に扱うため）
- `payload JSONB` — ジョブごとのデータ。スキーマは `packages/shared-types/schemas/job.schema.json`
- インデックス：`(queue, state, run_at)` — ワーカーの取得クエリ高速化に必須

### `LISTEN/NOTIFY`

NestJS が `INSERT INTO jobs` と同じトランザクションで `NOTIFY new_job, '<jobId>'` を発火する。Go ワーカー側が `LISTEN` で受信。

```typescript
// NestJS 側（Drizzle）
await tx.execute(sql`NOTIFY new_job, ${jobId.toString()}`);
```

### `pgvector` 拡張（R7）

将来的に RAG・重複検出を実装する際に有効化（→ [01-data-model.md: 将来拡張の想定](../../docs/requirements/3-cross-cutting/01-data-model.md)）。

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

## カラム命名規則

| サフィックス | 型 | 用途 | 例 |
|---|---|---|---|
| `_at` | TIMESTAMPTZ | 日時 | `created_at`, `updated_at`, `graded_at`, `locked_at` |
| `_id` | UUID / BIGINT FK | 外部キー | `user_id`, `problem_id`, `submission_id` |

- ID は `id UUID DEFAULT gen_random_uuid()`、ジョブのみ `id BIGSERIAL`
- 日時は **TIMESTAMPTZ で UTC**、表示時に JST 変換
- 状態カラム：`state`（マシン的、jobs.state）/ `status`（ユーザー視点、submissions.status）を使い分け
- JSON カラム：`JSONB` を使う、必ずスキーマを別途文書化

## スキーマ定義のパターン

```typescript
// apps/api/src/drizzle/schema/jobs.ts
import { bigserial, integer, jsonb, pgTable, text, timestamp } from 'drizzle-orm/pg-core';

export const jobs = pgTable('jobs', {
  id: bigserial('id', { mode: 'bigint' }).primaryKey(),
  queue: text('queue').notNull(),
  type: text('type').notNull(),
  payload: jsonb('payload').notNull(),
  state: text('state').notNull().default('queued'),
  attempts: integer('attempts').notNull().default(0),
  run_at: timestamp('run_at', { withTimezone: true }).notNull().defaultNow(),
  locked_at: timestamp('locked_at', { withTimezone: true }),
  locked_by: text('locked_by'),
  last_error: text('last_error'),
  result: jsonb('result'),
  created_at: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  updated_at: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
});
```

## マイグレーション操作コマンド

```bash
pnpm db:generate    # スキーマ変更から SQL 生成
pnpm db:migrate     # 未適用マイグレーションを適用
pnpm db:push        # ローカル開発用：スキーマを直接 DB に反映（マイグレーション SQL を作らない）
pnpm db:studio      # Drizzle Studio 起動
pnpm db:seed        # シードデータ投入
pnpm db:reset       # DB を初期化（破壊的、ローカル専用）
```

## スキーマ変更時の手順

1. `apps/api/src/drizzle/schema/` のスキーマファイルを修正
2. `pnpm db:generate` でマイグレーション SQL を生成
3. 生成された `apps/api/drizzle/*.sql` の内容を確認（必要なら手動で順序調整等）
4. 生成された SQL ファイル + `meta/` を git にコミット
5. `pnpm db:migrate` でマイグレーション適用

## 既存 SQL ファイルの編集

- 適用済みの SQL は原則編集しない
- ただし、本番環境への反映前なら追記が許容される（例：インデックス追加忘れ）
- 適用後は新しいマイグレーションファイルを追加する

## ローカル DB の初期化（全データリセット）

```bash
docker compose exec postgres dropdb -U postgres ai_coding_drill
docker compose exec postgres createdb -U postgres ai_coding_drill
pnpm db:migrate
pnpm db:seed
```

または短縮：

```bash
pnpm db:reset
```

## シードデータの管理

- シードは `apps/api/src/drizzle/seeds/` に配置
- 開発に必要な最小限のデータ：カテゴリマスタ、テスト問題数件、テストユーザー
- 投入順序は FK 依存順
- 本番環境への投入は別途運用手順で対応（シードと本番データを分離）

## トランザクション分離レベル

- 既定：`READ COMMITTED`（Postgres デフォルト）
- ジョブ取得（`SELECT FOR UPDATE SKIP LOCKED`）は既定で問題なし
- 厳密な整合性が必要な集計等：`SERIALIZABLE` を使用

```typescript
this.drizzle.db.transaction(async (tx) => {
  // ...
}, { isolationLevel: 'serializable' });
```
