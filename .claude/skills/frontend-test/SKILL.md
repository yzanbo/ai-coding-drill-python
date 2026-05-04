---
name: frontend-test
description: 要件 .md に基づいてフロントエンドのテストを生成・実行する
argument-hint: "[feature-name] (例: problem-detail, history)"
---

# 要件ベースのフロントエンドテスト

引数 `$ARGUMENTS` を機能名として解釈する。

## 手順

### 1. 要件と実装コードの読み込み

- `docs/requirements/4-features/$ARGUMENTS.md` を読み込む（画面一覧、ユーザーフロー、バリデーションルール）
- 対応する FE 実装コード（ページ、コンポーネント、フック）を読み込む

### 2. テスト対象の特定

以下の優先度でテスト対象を特定する：

1. **バリデーションスキーマ**（`lib/validation/` の Zod スキーマ）
2. **カスタムフック**（`_hooks/` 配下、特にデータ変換・ビジネスロジック）
3. **ユーティリティ関数**（`lib/utils/` 配下）
4. **コンポーネント**（主要なインタラクションを持つもの、特に解答画面・フォーム）

### 3. テストの生成

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

### 4. テスト実行

```bash
pnpm --filter @ai-coding-drill/web test
```

失敗したテストがあれば原因を分析し、テストまたは実装を修正する。

### 5. カバレッジ確認

テスト対象に対して主要なケースがカバーされているか確認する：

- 正常系フロー
- エラー系（バリデーションエラー、API エラー）
- 境界値（空文字、最大長、日付境界等）
- ローディング・エラー状態の表示

### 6. 結合テストのルール

詳細は [.claude/rules/frontend.md](../../rules/frontend.md) の「結合テストのルール」を参照：

- `fireEvent` ではなく `userEvent` を使用
- API モックは MSW
- 非同期は `findBy*` / `waitFor` で待機
- 各テストは独立させる

### 7. 結果報告

テスト結果をユーザーに報告する：

- パスしたテスト数 / 全テスト数
- カバレッジ概要
- 該当する場合、要件の「テスト完了」ステータスをチェック
