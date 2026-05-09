# apps/web

Next.js / TypeScript フロントエンド。**実装着手前の skeleton**。

## 役割（[ADR 0036](../../docs/adr/0036-frontend-monorepo-pnpm-only.md)）

- ユーザ向け Web UI（CodeMirror エディタ含む、[ADR 0015](../../docs/adr/0015-codemirror-over-monaco.md)）
- ジョブ進捗ポーリング / 完了通知
- API クライアント（型 + Zod + HTTP クライアントは Hey API で自動生成、[ADR 0006](../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）

## 実装着手時に揃えるもの

- `package.json`（pnpm 管理、Frontend ツーリングは本 app 配下に閉じる、[ADR 0036](../../docs/adr/0036-frontend-monorepo-pnpm-only.md)）
- `tsconfig.json` / `biome.jsonc` / `knip.config.ts` / `.syncpackrc.ts`（root から本 app に移動）
- `pnpm-lock.yaml`（独立した lockfile）
- `src/__generated__/api/`（Hey API 生成物、コミット対象）
- `src/`（Next.js App Router）
- テスト：Vitest + React Testing Library + Playwright（[ADR 0038](../../docs/adr/0038-test-frameworks.md)）

## ホスティング

Vercel（[ADR 0013](../../docs/adr/0013-vercel-for-frontend-hosting.md)）。

## 起動

`mise run web-dev` 等は実装着手後に有効化される（タスク定義は [mise.toml](../../mise.toml) に既記載）。
