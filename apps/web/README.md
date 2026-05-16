# apps/web

Next.js / TypeScript フロントエンド。R0 で雛形 + 品質ゲート（Biome / tsc / Knip / syncpack）を整備済み、機能実装は R1 以降。

## 役割（[ADR 0036](../../docs/adr/0036-frontend-monorepo-pnpm-only.md)）

- ユーザ向け Web UI（CodeMirror エディタ含む、[ADR 0015](../../docs/adr/0015-codemirror-over-monaco.md)）
- ジョブ進捗ポーリング / 完了通知
- API クライアント（型 + Zod + HTTP クライアントは Hey API で自動生成、[ADR 0006](../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）

## 構成

- `package.json` / `pnpm-lock.yaml` — pnpm 管理、Frontend ツーリングは本 app 配下に閉じる（[ADR 0036](../../docs/adr/0036-frontend-monorepo-pnpm-only.md)）
- `pnpm-workspace.yaml` — pnpm 11+ の `onlyBuiltDependencies` 宣言用（workspace 機能は未使用）
- `tsconfig.json` / `biome.jsonc` / `knip.config.ts` / `.syncpackrc.ts` / `vitest.config.ts` / `playwright.config.ts`
- `src/app/` — Next.js App Router（コロケーション規約は [.claude/rules/frontend.md](../../.claude/rules/frontend.md) を参照）
- `src/app/__generated__/api/` — Hey API 生成物（R1 以降、コミット対象）

## ホスティング

Vercel（[ADR 0013](../../docs/adr/0013-vercel-for-frontend-hosting.md)）。

## 起動

すべて root から `mise run web:*` で起動する（タスク SSoT は [mise.toml](../../mise.toml)）。

```bash
mise run web:dev          # next dev
mise run web:lint         # biome check
mise run web:typecheck    # tsc --noEmit
mise run web:knip         # 未使用検出
mise run web:syncpack     # package.json 整合性
mise run web:test         # vitest（R1 以降で本格利用）
mise run web:e2e          # playwright（R5 以降で本格利用）
```
