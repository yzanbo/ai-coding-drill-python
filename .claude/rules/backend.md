---
paths:
  - "apps/api/**/*"
---

# バックエンド開発ルール（NestJS API）

NestJS（TypeScript）の API サーバー。詳細な選定理由は [ADR 0004](../../docs/adr/0004-nestjs-for-backend.md)。ORM は Drizzle（→ [ADR 0016](../../docs/adr/0016-drizzle-orm-over-prisma.md)）。

## モジュール構成（`apps/api/src/`）

機能別フラット構成（→ [02-architecture.md](../../docs/requirements/2-foundation/02-architecture.md#backend-apinestjs)）：

- `auth/` — 認証（GitHub OAuth、Passport Strategy、セッション管理）
- `users/` — ユーザー管理（プロバイダ非依存、`auth_providers` 経由で連携）
- `problems/` — 問題 CRUD
- `generation/` — LLM 呼び出し（生成・Judge）、プロンプト読み込み、`LlmProvider` 抽象化
- `grading/` — 採点ジョブ投入（`jobs` テーブルへの INSERT + `NOTIFY new_job`）、結果取得 API
- `submissions/` — 解答記録
- `observability/` — OpenTelemetry セットアップ、構造化ログ、メトリクス
- `drizzle/` — Drizzle Module（`@Global()` で全モジュールから利用可能）+ スキーマ + シード
- `lib/` — どの機能モジュールにも属さない純粋なユーティリティ（共通 DTO、定数等）。サービス・ビジネスロジック禁止

### 設計方針

- **「admin/customer」のような分割は採用しない**。同じリソースを扱うエンドポイントが分散しロジックが重複するため
- 認証の有無は `@Public()` デコレータで制御する。エンドポイントのパス分割ではなく、ガードで認証要否を切り替える
- **横断的な部品は所属する機能モジュールに置き、exports で公開する**。例：`@Public()` / `JwtAuthGuard` / `@CurrentUser()` → `auth/`
- どの機能モジュールにも属さない純粋なユーティリティ（例：PaginationMetaDto）のみ `lib/` に配置する。サービスやビジネスロジックを `lib/` に置いてはならない

### 循環依存の防止

- **モジュール間の依存は一方向に保つ**。A → B かつ B → A の関係を作らない
- 依存の方向：`grading/` → `submissions/`, `problems/` のように、上位の業務モジュールが下位のマスタ系モジュールを参照する
- 副作用（通知送信等）は EventEmitter でトリガーし、直接の import を避ける
- `forwardRef()` は使わない。循環が発生した場合は依存方向の設計を見直す

## API ルートと認証

- REST リソース単位のパス設計（例：`/problems`, `/submissions`, `/auth/github`）
- Swagger UI：`/api/docs`、OpenAPI JSON：`/api/docs/openapi.json`
- 認証：Passport + GitHub OAuth、セッションは Cookie + Redis（→ [ADR 0015](../../docs/adr/0015-github-oauth-with-extensible-design.md)）
- 全ルートデフォルト認証必須（`APP_GUARD` で `JwtAuthGuard` 相当をグローバル適用）
- `@Public()` で認証スキップ、`@CurrentUser(key?)` で認証済みユーザー情報取得
- レート制限：`@nestjs/throttler` + Redis ストレージ、Sliding Log 方式（→ [01-non-functional.md](../../docs/requirements/2-foundation/01-non-functional.md)）

## データベース（Postgres + Drizzle ORM）

- Drizzle ORM + Postgres（`postgres-js` または `node-postgres` ドライバ）。`DrizzleService` を注入して `this.drizzle.db` でアクセス
- タイムゾーン：`TIMESTAMPTZ` で UTC 保持、表示時に JST 変換（dayjs）
- IDs：UUID（`gen_random_uuid()`）または BIGSERIAL（`jobs.id` のみ BIGSERIAL）
- 全テーブルに `created_at`、必要に応じて `updated_at`。**ハードデリート方針**（ソフトデリートは原則使わない、必要なら個別に検討）
- スキーマ定義：`apps/api/src/drizzle/schema/` 配下に機能別ファイル
- 詳細は [01-data-model.md](../../docs/requirements/3-cross-cutting/01-data-model.md)

### Drizzle クエリパターン

```typescript
// リレーショナルクエリ
this.drizzle.db.query.problems.findFirst({ where: eq(problems.id, id), with: { submissions: true } })
this.drizzle.db.query.problems.findMany({ where: and(...conditions), columns: { id: true, title: true } })

// INSERT（RETURNING で生成 ID 取得）
this.drizzle.db.insert(submissions).values(data).returning({ id: submissions.id })

// UPDATE
this.drizzle.db.update(jobs).set({ state: 'running', locked_at: new Date() }).where(eq(jobs.id, id))

// DELETE
this.drizzle.db.delete(submissions).where(eq(submissions.id, id))

// SELECT + count
this.drizzle.db.select({ count: count() }).from(problems).where(...)

// トランザクション（解答 INSERT + ジョブ INSERT を同時に → トランザクショナルなエンキュー）
await this.drizzle.db.transaction(async (tx) => {
  const [submission] = await tx.insert(submissions).values(...).returning({ id: submissions.id });
  await tx.insert(jobs).values({ type: 'grade', payload: { submissionId: submission.id }, state: 'queued' });
  await tx.execute(sql`NOTIFY new_job, ${submission.id.toString()}`);
});

// SKIP LOCKED でジョブ取得（参考、実際は Go ワーカー側で実行）
this.drizzle.db
  .select()
  .from(jobs)
  .where(and(eq(jobs.state, 'queued'), lte(jobs.run_at, new Date())))
  .orderBy(jobs.run_at)
  .limit(1)
  .for('update', { skipLocked: true });
```

### where 条件の必須ルール

- 認証済みエンドポイントでは「自分のリソースか」をチェックする（例：`eq(submissions.user_id, currentUser.id)`）
- `inArray(table.col, ids)` を使う前に `ids.length === 0` を必ずガードする

### ページネーションパターン

`PaginationMetaDto`（`lib/dto/pagination-meta.dto.ts`）を使用：

```typescript
return {
  data: items,
  meta: { total, page, limit, last_page: Math.ceil(total / limit) },
};
```

## ジョブキュー（Postgres `jobs` テーブル）

- ジョブ投入は `INSERT INTO jobs` + `NOTIFY new_job, <jobId>` を**同一トランザクション**で実行（→ [ADR 0001](../../docs/adr/0001-postgres-as-job-queue.md)）
- ペイロードは JSONB、スキーマは `packages/shared-types/schemas/job.schema.json` で管理（→ [ADR 0014](../../docs/adr/0014-json-schema-as-single-source-of-truth.md)）
- ワーカー側の取得・処理は Go で実装（→ [.claude/rules/worker.md](./worker.md)）

## LLM 呼び出し

- `generation/` モジュール内の `LlmProvider` インターフェース経由で呼び出す（→ [ADR 0011](../../docs/adr/0011-llm-provider-abstraction.md)）
- 直接 `@anthropic-ai/sdk` 等を呼ぶ実装はしない。必ず抽象化レイヤを通す
- プロンプトは `packages/prompts/` 配下の YAML から読み込む（→ [.claude/rules/prompts.md](./prompts.md)）
- 構造化出力は Zod でランタイムバリデーション、スキーマは `packages/shared-types/schemas/` から自動生成
- LLM-as-a-Judge は自前実装、生成と Judge は別プロバイダ・別モデル（→ [ADR 0009](../../docs/adr/0009-custom-llm-judge.md)）

## コーディング規約

### コードスタイル

- Biome（lint + format）。設定は `packages/config/biome-config/`（→ [ADR 0013](../../docs/adr/0013-biome-for-tooling.md)）
- 型チェックは `tsc --noEmit`
- **`any` 利用不可**。Drizzle の推論型（`typeof problems.$inferSelect`）や独自 DTO で型付けする
- モジュール名（ディレクトリ・クラス名）は単数形を使う（例：`problem/`, `ProblemModule`）。テーブル名は複数形のまま

### コントローラ

- ビジネスロジックはサービスに委譲する。コントローラはリクエスト/レスポンスの橋渡しのみ
- `@ApiTags('Problems')` で Swagger のグループ分けを付ける
- `@ApiOperation({ summary: '...' })` + `@ApiOkResponse({ type: DtoClass })` を全エンドポイントに付ける
- パスパラメータ：UUID は `@Param('id', ParseUUIDPipe) id: string`、整数は `ParseIntPipe`
- `@Query()` の DTO が `main.ts` の `extraModels` に登録されていない場合、Swagger に型が出ないので追加する

### DTO

- 命名：`Create*Dto`, `Update*Dto`, `*ResponseDto`, `*ParamDto`, `*QueryDto`
- `@ApiProperty()` で Swagger 定義、`class-validator` でバリデーション
- クエリパラメータには `@Type(() => Number)` で型変換を付ける
- `PartialType()`, `PickType()` で DTO 派生を活用する
- `ValidationPipe({ transform: true })` は `APP_PIPE` でグローバル適用する

### サービス

- Drizzle は `this.drizzle.db.query.model.method()` でリレーショナルクエリ、`this.drizzle.db.insert/update/delete(table)` で CRUD 操作
- トランザクション：`this.drizzle.db.transaction(async (tx) => { ... })`
- 認証済みエンドポイントでは「自分のリソースか」を必ずチェックする
- エラーは NestJS 組み込み例外（`NotFoundException`, `BadRequestException` 等）。メッセージは日本語
- ロガー：`private readonly logger = new Logger(ClassName.name)`

## 新規機能の追加パターン

### 基本（CRUD 機能）

1. `apps/api/src/<feature>/` にディレクトリ作成
2. `module.ts`, `controller.ts`, `service.ts`, `dto/` を作成
3. `app.module.ts` の imports に追加
4. スキーマ変更があれば `apps/api/src/drizzle/schema/` に追加 → `pnpm db:generate` でマイグレーション生成

```
apps/api/src/problems/
├── problems.module.ts
├── problems.controller.ts        // @Controller('problems')
├── problems.service.ts
└── dto/
    ├── create-problem.dto.ts
    ├── update-problem.dto.ts
    └── problem-response.dto.ts
```

### モジュール間の依存

- 他モジュールのサービスを利用する場合は、提供元モジュールを imports に追加する
- 提供元モジュールは service を exports に登録する

## テスト

- ユニットテスト（`*.spec.ts`）：Jest + ts-jest（NestJS 標準）。DrizzleService 等はモックで注入
- E2E テスト（`*.e2e-spec.ts`）：`test/jest-e2e.json` で設定。AppModule を import、supertest で HTTP リクエスト
- テスト説明文は日本語（`正常系: ...`, `異常系: ...`）

### E2E テストの実行方法

E2E は専用の Postgres / Redis を docker-compose で起動して実行する。テスト終了後に `-v` でボリューム破棄。

```bash
pnpm e2e:up               # E2E 環境起動
pnpm --filter @ai-coding-drill/api test:e2e
pnpm e2e:down             # 環境破棄
```

## データベース操作

```bash
pnpm db:migrate           # 未適用マイグレーションを適用
pnpm db:generate          # スキーマ変更後にマイグレーション SQL 生成
pnpm db:push              # スキーマを直接 DB に反映（ローカル開発の手軽な同期）
pnpm db:seed              # シードデータ投入
pnpm db:studio            # Drizzle Studio 起動
pnpm db:reset             # DB を初期化（破壊的、ローカル専用）
```

詳細は [.claude/rules/drizzle.md](./drizzle.md)。

## 技術選定

新規コードで使うライブラリ：

- 日付操作：`dayjs`
- パスワードハッシュ：使わない（GitHub OAuth のみのため）
- バリデーション（DTO）：`class-validator` + `class-transformer`
- バリデーション（LLM 出力等のランタイム検証）：`zod`
- HTTP クライアント：標準 `fetch` または `undici`
- LLM SDK：`@anthropic-ai/sdk` / `@google/generative-ai` 等（プロバイダ抽象化レイヤ内でのみ）
- メール送信：MVP では不要（R6 以降で必要なら検討）
