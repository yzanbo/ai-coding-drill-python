# components/providers/

## providers/ とは何か

**React の Provider 群**（アプリ全体のコンテキストを供給する部品）を置くフォルダ。
`app/layout.tsx` のいちばん外側で `<RootProviders>{children}</RootProviders>` のように
読み込んで、子コンポーネントから `useXxx()` で値を取り出せるようにします。

代表例（このプロジェクトで想定）：

- `tanstack-query-provider/`（TanStack Query の `QueryClientProvider`、共有 `queryClient` は
  [lib/shared-query/](../../lib/shared-query/) から取り出す）
- `api-error-provider/`（API エラーを全画面共通のトースト表示で出す Provider）
- `theme-provider/`（ダーク / ライトテーマ。導入時に検討）

## 役目

- **画面の外側で 1 回だけ**有効にしたい横断機能（キャッシュ / 認証 / テーマ / トースト等）を
  React のコンテキストとして配る
- 値の生成（`new QueryClient()` 等）は **`lib/` 側で作って渡す**形にし、Provider は配るだけに保つ

## ファイル配置

**全 Provider を同名フォルダで包む**ルール（[frontend-component.md](../../../../../.claude/rules/frontend-component.md)）：

- `tanstack-query-provider/tanstack-query-provider.tsx`（本体）
- `tanstack-query-provider/tanstack-query-provider.test.tsx`（テスト）
- `tanstack-query-provider/use-api-error.ts`（同フォルダ内に取り出し用フック）
- `root-providers/root-providers.tsx`（複数 Provider を 1 つにまとめる集約も同じく同名フォルダ）

## やってはいけないこと

- ❌ `providers/` 内で具体的なドメイン部品（`ProblemCard` 等）を import する
  （Provider は **配るだけ**に保つ）
- ❌ Provider の中で `useState` を使ってアプリ全体の状態を保持する用途で使う
  （複雑な状態管理は TanStack Query / 専用ストアを別途検討）
