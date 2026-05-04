# 0016. ORM に Drizzle を採用（Prisma 不採用）

- **Status**: Accepted
- **Date**: 2026-05-03
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

TypeScript で PostgreSQL を扱う ORM / クエリビルダを 1 つに決める必要がある。

- DB は PostgreSQL 16 で確定（→ [05-runtime-stack.md: データベース](../requirements/2-foundation/05-runtime-stack.md#データベース)）
- 同じ DB をジョブキューとしても使う（→ [ADR 0001](./0001-postgres-as-job-queue.md)）
- ジョブ取得には `SELECT ... FOR UPDATE SKIP LOCKED` と `LISTEN/NOTIFY` を使う（NestJS 側でも一部参考実装が必要）
- 解答送信時は「`submissions` INSERT + `jobs` INSERT + `NOTIFY new_job`」を**同一トランザクション**で行う必要がある（Outbox パターン不要を成立させる根拠）
- バックエンドは NestJS（→ [ADR 0004](./0004-nestjs-for-backend.md)）。Service が DB アクセスを直接行う方針で、Repository レイヤは設けない
- TypeScript の型推論を最大限活かし、`any` を排除したい（[backend.md](../../.claude/rules/backend.md) のコーディング規約）
- 当初は要件定義書で「Prisma または Drizzle」と未確定だったが、実装規約（[CLAUDE.md](../../.claude/CLAUDE.md)・[backend.md](../../.claude/rules/backend.md)）では Drizzle を前提に書かれており、ドキュメント間の不整合が発生していた

## Decision（決定内容）

**Drizzle ORM** を採用。Prisma は不採用。

- Drizzle のスキーマ定義（`apps/api/src/drizzle/schema/`）を Single Source of Truth として、マイグレーション SQL は `drizzle-kit` で自動生成
- `DrizzleService` を `@Global()` モジュールで提供し、各 Service が `this.drizzle.db` を直接呼び出す
- リレーショナルクエリ（`db.query.<table>.findFirst/findMany`）と CRUD API（`db.insert/update/delete`）を併用
- トランザクションは `db.transaction(async (tx) => { ... })` で記述、ジョブ投入は同一 `tx` 内で `INSERT` + `NOTIFY` を行う

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **Drizzle ORM** | TS-first の軽量 ORM、SQL ライクな API + リレーショナルクエリ | （採用） |
| Prisma | スキーマ DSL ベースの ORM、Generated Client で型安全 | スキーマが独自 DSL（`.prisma`）で JSON Schema SSoT 戦略（[ADR 0014](./0014-json-schema-as-single-source-of-truth.md)）と相性が悪い。ランタイムが重い（Rust エンジン同梱）、`SKIP LOCKED` や `LISTEN/NOTIFY` を素直に書けず `$queryRaw` への退避が頻発する |
| TypeORM | デコレータベースの老舗 ORM | デコレータ経由で型推論が弱く `any` が混入しやすい、メンテナンスペースが鈍化（2026 時点）、Active Record / Data Mapper の二系統が共存して規約がブレやすい |
| Kysely | TS-first のクエリビルダ、型推論が強力 | クエリビルダ専業でリレーショナルクエリ機能が薄い。`with: { submissions: true }` のような JOIN が冗長になり、開発速度で Drizzle に劣る |
| 生 SQL（`pg` / `postgres-js` 直叩き） | 最も軽量、最大の自由度 | 型安全性ゼロで DTO を全て手書きする必要、`any` 禁止規約と矛盾、本プロジェクト規模では過剰な手間 |

## Consequences（結果・トレードオフ）

### 得られるもの
- **強い型推論**：スキーマ定義から `typeof problems.$inferSelect` 等で型を導出でき、`any` を構造的に排除できる
- **生 SQL に近い API**：`SKIP LOCKED`・`LISTEN/NOTIFY`・`jsonb_path_ops` 等の Postgres 固有機能を `sql` テンプレートで素直に書ける
- **軽量ランタイム**：Prisma のような外部エンジンプロセス不要、コールドスタートが速い（ECS Fargate 最小タスク 1 構成と相性が良い、→ [ADR 0004](./0004-nestjs-for-backend.md)）
- **トランザクション内で混合操作可能**：`tx.insert().values()` と `tx.execute(sql\`NOTIFY ...\`)` を同一トランザクションで自然に書ける
- **Repository レイヤ不要**：Drizzle 自体が Repository 風の API を提供するため、Service が直接呼び出す方針（→ [ADR 0004](./0004-nestjs-for-backend.md)、[02-architecture.md: Backend API](../requirements/2-foundation/02-architecture.md#backend-apinestjs)）と整合
- **JSON Schema SSoT 戦略と整合**：Drizzle スキーマと JSON Schema は別レイヤの SSoT として共存できる（DB スキーマ ↔ ペイロードスキーマの責務が綺麗に分離）

### 失うもの・受容するリスク
- **Prisma Studio 級の GUI が無い**：Drizzle Studio はあるが、Prisma Studio に比べて機能が限定的。代替として `psql` と Drizzle Studio で運用
- **エコシステムの厚みは Prisma に劣る**：Auth.js 等の他 OSS で Prisma がデフォルトサポートのことが多く、Drizzle アダプタが必要な場面がある
- **マイグレーション管理が手動寄り**：`drizzle-kit generate` で SQL は出るが、Prisma Migrate の宣言的差分検知ほど洗練されていない。ただし本プロジェクト規模では問題にならない
- **学習コスト**：Drizzle 経験者は Prisma 経験者より少ない。ポートフォリオで「なぜ Drizzle？」を説明する必要がある（→ 本 ADR が回答）

### 将来の見直しトリガー
- 複雑なネストリレーション・分散 DB・複数 RDBMS への対応が必要になった場合は Prisma を再検討
- Drizzle のメンテナンス停滞・破壊的変更頻発が観測された場合は移行を検討
- マルチデータソース（DynamoDB 等）併用が必要になった場合は、ストレージ抽象化のために Repository レイヤと併せて再設計

## References

- [05-runtime-stack.md: データベース](../requirements/2-foundation/05-runtime-stack.md#データベース)
- [02-architecture.md: Backend API](../requirements/2-foundation/02-architecture.md#backend-apinestjs)
- [.claude/rules/backend.md](../../.claude/rules/backend.md)
- [.claude/rules/drizzle.md](../../.claude/rules/drizzle.md)
- [ADR 0001: Postgres をジョブキューに採用](./0001-postgres-as-job-queue.md)
- [ADR 0004: バックエンド API に NestJS を採用](./0004-nestjs-for-backend.md)
- [ADR 0014: JSON Schema を Single Source of Truth に採用](./0014-json-schema-as-single-source-of-truth.md)
- Drizzle ORM 公式：https://orm.drizzle.team/
