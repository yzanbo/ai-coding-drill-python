---
name: frontend-test
description: 要件 .md に基づいてフロントエンドのテストを生成・実行する
argument-hint: "[<name>] (例: problem-display-and-answer, learning)"
---

# 要件ベースのフロントエンドテスト

引数 `$ARGUMENTS` を機能名として解釈する。

## 手順

### 1. 要件と実装コードの読み込み

- `docs/requirements/4-features/$ARGUMENTS.md` を読み込む（画面 / ユーザーフロー / バリデーション節、セクション名は `_template.md` 準拠）
- 対応する FE 実装コード（ページ、コンポーネント、フック）を読み込む

### 2. テスト対象の特定

以下の優先度でテスト対象を特定する：

1. **バリデーションスキーマ**（`lib/validation/` の Zod スキーマ）
2. **カスタムフック**（`_hooks/` 配下、特にデータ変換・ビジネスロジック）
3. **ユーティリティ関数**（`lib/utils/` 配下）
4. **コンポーネント**（主要なインタラクションを持つもの、特に解答画面・フォーム）

### 3. 要件 .md の事前更新（テスト対象の検討で確定した決定を反映）

手順 2 のテスト対象特定で**ユーザーと対話的に確定した観測対象**を、テスト生成に入る前に要件 .md に反映する。テストの観測対象を要件側に揃えることで、要件・コード・テストの 3 者を SSoT として一貫させる。

- 反映先：機能要件 .md の**受け入れ条件**節（観測可能な境界値・異常系・状態遷移の追加）、必要なら**バリデーション**節（業務上の理由があるルール）にも追記
- 機械的検証（型・必須・最大長）は Pydantic / Zod 側が SSoT のため要件 .md には書かない（→ `_template.md` 冒頭の長期運用原則）

差分を要件側に反映してから手順 4 のテスト生成に進む。

### 4. テストの生成

Vitest + Testing Library + MSW でテストを生成する：

- テストファイルは対象ファイルと同階層に `*.test.ts(x)` で配置（コロケーション）
- バリデーションテスト：正常系・異常系・境界値
- フックテスト：`renderHook` で状態変化・API 呼び出しを検証
- コンポーネントテスト：`render` + `userEvent` でインタラクション検証
- API モック：MSW でハンドラー設定（`server.use(http.get(...))`）

#### バリデーションテストの例

```typescript
import { describe, it, expect } from 'vitest';
import { problemAnswerSchema } from './problem-answer.schema';

describe('problemAnswerSchema', () => {
  it('正常系: 有効なコードを受け入れる', () => {
    const result = problemAnswerSchema.safeParse({ code: 'export function solve() {}' });
    expect(result.success).toBe(true);
  });

  it('異常系: 空コードを拒否する', () => {
    const result = problemAnswerSchema.safeParse({ code: '' });
    expect(result.success).toBe(false);
  });
});
```

#### コンポーネントテストの例

```typescript
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProblemDetail } from './problem-detail';

describe('ProblemDetail', () => {
  it('正常系: 解答送信ボタンをクリックすると submit が呼ばれる', async () => {
    const onSubmit = vi.fn();
    render(<ProblemDetail problem={mockProblem} onSubmit={onSubmit} />);
    await userEvent.click(screen.getByRole('button', { name: /送信/ }));
    expect(onSubmit).toHaveBeenCalled();
  });
});
```

### 5. テスト実行

```bash
mise run web:test
```

失敗したテストがあれば原因を分析し、テストまたは実装を修正する。

### 6. カバレッジ確認

テスト対象に対して主要なケースがカバーされているか確認する：

- 正常系フロー
- エラー系（バリデーションエラー、API エラー）
- 境界値（空文字、最大長、日付境界等）
- ローディング・エラー状態の表示

### 7. E2E テスト（Playwright）

主要なユーザーフロー（ログイン → 問題生成 → 解答 → 採点結果表示など、機能受け入れ条件に紐づく経路）は **Playwright** でカバーする（→ [ADR 0038](../../../docs/adr/0038-test-frameworks.md)、[.claude/rules/frontend.md](../../rules/frontend.md) の Playwright 章）：

- テストファイルは `apps/web/e2e/` 配下に `*.spec.ts` で配置（ユニットテストとは別ディレクトリ）
- 各テストは独立した認証セッションを使う（`storageState` / `test.use({ storageState })`）
- バックエンドは Docker Compose で起動した実 API + 実 DB を相手にする（モックしない）
- 実行：`mise run web:e2e`
- CI では headless、ローカルデバッグ時は `--headed` / `--ui` モード

```typescript
import { test, expect } from '@playwright/test';

test('解答送信フロー: 問題詳細から正答提出まで', async ({ page }) => {
  await page.goto('/problems/1');
  await page.getByRole('textbox', { name: /コード/ }).fill('export function solve() {}');
  await page.getByRole('button', { name: /送信/ }).click();
  await expect(page.getByText(/採点結果/)).toBeVisible();
});
```

E2E は「主要フローのみ」に絞る（受け入れ条件に直結する 1〜3 経路 / 機能）。エッジケースはユニット・結合テストでカバーする。

### 8. 結合テストのルール

詳細は [.claude/rules/frontend.md](../../rules/frontend.md) の「結合テストのルール」を参照：

- `fireEvent` ではなく `userEvent` を使用
- API モックは MSW
- 非同期は `findBy*` / `waitFor` で待機
- 各テストは独立させる

### 9. 要件 .md の事後追従（テスト中に確定した差分を反映）

テスト生成・実行中に明らかになった以下があれば**結果報告の前に**要件 .md へ反映する（実装が SSoT、要件側は契約の鏡として揃える、→ `_template.md` の長期運用原則）：

- **新たに見つかった観測可能な振る舞い**：画面遷移・状態表示・エラー時の挙動を受け入れ条件に追加
- **業務上の制約として発見されたバリデーション**：「バリデーション」節に追加（機械的検証は対象外）

軽微な追従はこのスキル内で直接更新してよい。差分の規模が大きい場合は `/update-requirements` で対話的に進める。

### 10. 結果報告

テスト結果をユーザーに報告する：

- パスしたテスト数 / 全テスト数
- カバレッジ概要
- 該当する場合、要件の「ユニットテスト完了」「E2E テスト完了」ステータスをチェック（`_template.md` 準拠の項目のみ、追加・削除はしない）
