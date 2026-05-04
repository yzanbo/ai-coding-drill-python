---
name: frontend-implement
description: 要件 .md を読んで Next.js のフロントエンドを実装する
argument-hint: "[feature-name] (例: problem-detail, history)"
---

# 要件ベースのフロントエンド実装

引数 `$ARGUMENTS` を機能名として解釈する。

## 手順

### 1. 要件の読み込み

- 機能要件：`docs/requirements/4-features/$ARGUMENTS.md`
- ベース要件：[01-overview.md](../../../docs/requirements/1-vision/01-overview.md)
- フロントエンドルール：[.claude/rules/frontend.md](../../rules/frontend.md)

ファイルが存在しない場合は、ユーザーに `/new-requirements` で先に作成することを提案する。

### 2. 画面一覧の確認

要件 .md の「画面一覧」セクションを確認する。画面一覧が空または不足している場合は、先に記入するようユーザーに促す。

以下を抽出する：

- **画面**：パス、概要、主要コンポーネント、使用 API
- **ユーザーフロー**：ステップの流れ
- **バリデーションルール**：FE/BE 共通のルール

### 3. 既存 FE コードの確認

- 関連するページ（`apps/web/src/app/(routing)/` 配下の `page.tsx`）を確認
- 関連する `_components/`、`_hooks/` を確認
- 既存の共通コンポーネント（`components/ui/`、`components/parts/`）の再利用可能性を確認
- API クライアント（`lib/api/`）と型（`@ai-coding-drill/shared-types` から import）を確認

### 4. 実装方針の提示

[.claude/rules/frontend.md](../../rules/frontend.md) の規約に従い、実装方針をユーザーに提示する：

- 新規作成するファイルの一覧（ページ、コンポーネント、フック）
- 変更するファイルの一覧
- 再利用する既存コンポーネントの一覧
- RSC（Server Component）と Client Component の使い分け
- 実装の順序（ページ骨組み → API フック → コンポーネント詳細 → スタイル）

ユーザーの承認を待ってから実装に着手する。

### 5. 実装

[.claude/rules/frontend.md](../../rules/frontend.md) のコーディング規約に従って実装する：

- ページ固有コンポーネントは `_components/` に配置
- ページ固有フックは `_hooks/` に配置（API 呼び出しは `_hooks/_fetch/`）
- 共有スキーマから型を import：`import type { ProblemType } from '@ai-coding-drill/shared-types'`
- フォームは React Hook Form + Zod、`mode: "onTouched"`
- API 呼び出しはカスタムフックで（`useGet*` / `usePost*` / `usePatch*` / `useDelete*`）
- API エラーは `ApiErrorProvider` で一元処理（個別フックは `error` state を保持）
- `cn()` でクラス名結合、デザインルール（`primary` / `destructive` 等のセマンティックカラー）を遵守
- 認証必須ページは `(authed)` ルートグループ配下に配置
- ファイル名・ディレクトリ名はケバブケース、`index.ts` 禁止

### 6. CodeMirror の使い方（解答画面）

`/problems/:id` の解答画面では：

- `_components/code-editor/` に CodeMirror ラッパーを配置
- `@codemirror/lang-javascript` で TS ハイライト
- `@typescript/vfs` + `@valtown/codemirror-ts` でブラウザ内型診断
- 型診断はサーバ採点の事前フィードバック、最終正誤はサーバが正

### 7. 採点結果ポーリング（TanStack Query）

```tsx
const { data: submission } = useGetSubmission(submissionId, {
  refetchInterval: (query) =>
    query.state.data?.status === 'graded' ? false : 1500,
});
```

### 8. ステータス更新

実装完了後、`docs/requirements/4-features/$ARGUMENTS.md` のステータスチェックボックスを更新：

```markdown
## ステータス
- [x] 要件定義完了
- [x] バックエンド実装完了
- [x] フロントエンド実装完了    ← ここをチェック
- [ ] 採点ワーカー実装完了
- [ ] テスト完了
```

### 9. 動作確認

- `pnpm --filter @ai-coding-drill/web typecheck` で型エラーなし
- `pnpm lint` で Biome 警告なし
- ローカルで http://localhost:3000 から手動疎通確認
- レスポンシブ確認（コードエディタ画面はデスクトップ優先）

問題があれば修正してから完了とする。
