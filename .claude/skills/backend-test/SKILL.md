---
name: backend-test
description: 要件 .md に基づいて NestJS のユニットテストを生成・実行する
argument-hint: "[feature-name] (例: problems, grading)"
---

# 要件ベースのバックエンドテスト生成・実行

引数 `$ARGUMENTS` を機能名として解釈する。

## 手順

### 1. 要件と実装の読み込み

1. `docs/requirements/4-features/$ARGUMENTS.md` を読み込む
2. [.claude/rules/backend.md](../../rules/backend.md) のテスト規約を確認する
3. 対象モジュールの実装コードを読み込む：
   - `apps/api/src/$ARGUMENTS/*.service.ts` — テスト対象のメインロジック
   - `apps/api/src/$ARGUMENTS/*.controller.ts` — エンドポイントの確認
   - `apps/api/src/$ARGUMENTS/dto/*.ts` — DTO の確認
   - `apps/api/src/drizzle/schema/*.ts` — 関連スキーマ

### 2. テスト方針の提示

以下をユーザーに提示し、承認を得てから生成に着手する：

- テスト対象のサービス・メソッド一覧
- テストケースの概要（正常系・異常系・境界値）
- 生成するファイルの一覧

### 3. ユニットテスト生成

`apps/api/src/$ARGUMENTS/` 配下に `*.spec.ts` ファイルを作成する。

#### テスト規約

- テストフレームワーク：Jest（NestJS 標準）
- テスト説明文は日本語（`正常系: ...`, `異常系: ...`）
- DrizzleService 等はモックで注入する
- ファイル名：`<class-name>.spec.ts`（例：`problems.service.spec.ts`）

#### テスト構造

```typescript
import { Test, TestingModule } from '@nestjs/testing';
import { ProblemsService } from './problems.service';
import { DrizzleService } from '../drizzle/drizzle.service';

describe('ProblemsService', () => {
  let service: ProblemsService;
  let drizzle: { db: { query: Record<string, unknown>; insert: jest.Mock; update: jest.Mock } };

  beforeEach(async () => {
    drizzle = { db: { query: {}, insert: jest.fn(), update: jest.fn() } };
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        ProblemsService,
        { provide: DrizzleService, useValue: drizzle },
      ],
    }).compile();
    service = module.get<ProblemsService>(ProblemsService);
  });

  describe('findAll', () => {
    it('正常系: 一覧を取得できる', async () => { /* ... */ });
  });

  describe('findOne', () => {
    it('正常系: 詳細を取得できる', async () => { /* ... */ });
    it('異常系: 存在しない ID で NotFoundException', async () => { /* ... */ });
  });

  describe('create', () => {
    it('正常系: 作成できる', async () => { /* ... */ });
  });
});
```

#### Drizzle モックパターン（Postgres）

```typescript
// query.* のモック
drizzle.db.query.problems = {
  findMany: jest.fn().mockResolvedValue([]),
  findFirst: jest.fn().mockResolvedValue(null),
};

// insert().values().returning() チェーン
const returningMock = jest.fn().mockResolvedValue([{ id: 'uuid-1' }]);
const valuesMock = jest.fn().mockReturnValue({ returning: returningMock });
drizzle.db.insert = jest.fn().mockReturnValue({ values: valuesMock });

// update().set().where()
const whereMock = jest.fn().mockResolvedValue(undefined);
const setMock = jest.fn().mockReturnValue({ where: whereMock });
drizzle.db.update = jest.fn().mockReturnValue({ set: setMock });

// transaction
drizzle.db.transaction = jest.fn().mockImplementation(async (cb) => cb(drizzle.db));
```

#### LLM プロバイダのモックパターン

```typescript
const llmProvider = {
  generate: jest.fn().mockResolvedValue({
    data: { /* generated problem */ },
    usage: { inputTokens: 100, outputTokens: 200, costUsd: 0.001 },
    model: 'mock-model',
    cached: false,
  }),
  judge: jest.fn().mockResolvedValue({ data: { total: 22 }, ... }),
};
```

#### テストケースのカバレッジ目安

各サービスメソッドに対して：

- **正常系**：期待通りの結果が返ること
- **異常系（存在チェック）**：存在しないリソースで `NotFoundException`
- **異常系（権限チェック）**：他人のリソースで `ForbiddenException`
- **異常系（バリデーション）**：DTO バリデーション、ビジネスルール違反
- **境界値**：空配列、null、最大文字数、最小日付等

### 4. テスト実行

```bash
pnpm --filter @ai-coding-drill/api test --testPathPattern='src/$ARGUMENTS/' --verbose
```

または：

```bash
cd apps/api
pnpm jest --testPathPattern='src/$ARGUMENTS/' --verbose
```

テストが失敗した場合は修正して再実行。全テストがパスするまで繰り返す。

### 5. E2E テスト（必要な場合）

重要なフロー（解答送信 → 採点 → 結果取得）は E2E でも検証する。詳細は [.claude/rules/backend.md](../../rules/backend.md) の「E2E テストの実行方法」を参照。

```bash
pnpm e2e:up
pnpm --filter @ai-coding-drill/api test:e2e
pnpm e2e:down
```

### 6. 結果報告

テスト結果をユーザーに報告する：

- パスしたテスト数 / 全テスト数
- カバレッジ概要（`pnpm --filter @ai-coding-drill/api test:cov` で取得）
- 要件に対するテストカバレッジの説明
- 該当する場合、要件の「テスト完了」ステータスをチェック
