# 03. Next.js 環境構築（🟡 進行中）

> **守備範囲**：Next.js ランタイム（Node.js + pnpm）取得から apps/web を品質ゲート付きで動かすまでの 9 ステップ。本フェーズが終わると、Next.js の lint / typecheck / knip / syncpack がローカル + CI 両方で緑になり、依存自動更新が走り始める。
> **前提フェーズ**：[02-python.md](./02-python.md) 完了済（Python 縦スライスと同じ「品質ゲートのステップ」パターンを再利用する）
> **次フェーズ**：R0 完了 → R1（[../01-roadmap.md](../01-roadmap.md) の「Now：R1 MVP」セクション）
>
> **本ファイル共通の最新版調査ポリシー**：
> 本プロジェクトのバージョン方針（[.claude/CLAUDE.md: バージョン方針](../../../../.claude/CLAUDE.md#バージョン方針)）に従い、**SSoT に書かれた既存版数を信用せず、各ステップで対象ツールの最新安定版を毎回 Web で調査してから書き換える**。`create-next-app` / `pnpm add` 等は実行タイミングで latest を取りに行くので雛形作成時点の最新は自動的に入るが、**Node.js / pnpm / Next.js / React / TypeScript / Biome / Knip / syncpack / Vitest / Playwright / Testing Library / Tailwind 等**は毎回リリースノートで EOL / breaking change を確認してから採用する。RC / beta / nightly は採用しない。

---

## 1. Node.js 最新 Active LTS / pnpm 最新版を調査して pin → mise install

**目的**：Node.js の最新 Active LTS（偶数メジャー、Current は不採用）と pnpm の最新版を調査し、`mise.toml` と `README.md` の 2 箇所のみを書き換えて pin 化、そのうえで実体化する。

**作業内容**：
1. **Node.js 最新 Active LTS を調査**：[nodejs.org/en/about/previous-releases](https://nodejs.org/en/about/previous-releases) で Active LTS の最大メジャー版数（偶数）を確認。Current（最新メジャー）と Maintenance LTS は不採用
2. **pnpm の最新安定版を確認**：[pnpm.io](https://pnpm.io/) または npm registry。mise.toml は `pnpm = "latest"` 指定だが、メジャー upgrade 時は CHANGELOG（breaking change）を読む
3. **`mise.toml` を書き換え**：`[tools]` の `node = "<X>"` を最新 Active LTS のメジャー数値に更新
4. **`README.md` を書き換え**：「技術スタック概要」表の Node.js 版数を同じメジャーに更新
5. **`mise install` を実行**：mise.toml の全 tool をまとめて再解決
6. **動作確認**：`mise exec -- node --version` / `mise exec -- pnpm --version` が想定版数を返すこと

**コマンド例**：
```bash
# 1〜4. 最新 Active LTS / pnpm 版数を調査して mise.toml と README.md を編集
# 5. インストール
mise install
# 6. 動作確認
mise exec -- node --version    # 調査済の Active LTS メジャー（patch は mise が解決）
mise exec -- pnpm --version    # 調査済の最新安定版
```

**前提**：[01-foundation.md: 3. mise 導入](./01-foundation.md#3-mise-導入-)（mise CLI が動作）

**関連 ADR**：[ADR 0039](../../../adr/0039-mise-for-task-runner-and-tool-versions.md)

---

## 2. apps/web に Next.js 雛形を作成

**目的**：`pnpm create next-app` で apps/web に Next.js + React + TypeScript + Tailwind の雛形を生成する。ESLint は同コマンドで入るが本プロジェクトは Biome 採用（[ADR 0018](../../../adr/0018-biome-for-tooling.md)）のため次 step で除去する。

**作業内容**：
1. **Next.js / React の最新安定版を調査**：
   - Next.js：[nextjs.org/blog](https://nextjs.org/blog) で latest stable のメジャー版を確認（RC / canary は不採用）。**メジャー upgrade の場合は upgrade guide を読み、本プロジェクト規約（App Router / Server Component / Image 最適化）への影響を確認**
   - React：[react.dev/blog](https://react.dev/blog) で latest stable を確認。**Next.js の peer dep（`pnpm view next@latest peerDependencies`）と矛盾しないこと**
   - これらは `create-next-app@latest` 実行時点でレジストリの latest が解決されるので**コマンド実行のタイミングで自動的に入る**が、雛形にピン留めされた版数が直近で patch リリースを取りこぼしている可能性があるので step 3 で `pnpm outdated` 後追い確認する
2. **既存 `apps/web/README.md` を退避**：`pnpm create next-app` が README を上書きするため、事前に退避（後で復元 or 書き換え）
3. **`pnpm create next-app` を実行**（オプション選択を CLI 引数で確定させる）：
   ```bash
   mise exec -- pnpm create next-app@latest apps/web \
     --ts --app --tailwind \
     --src-dir \
     --no-eslint \
     --turbopack \
     --use-pnpm \
     --import-alias "@/*" --yes
   ```
   - `--src-dir`：[.claude/rules/frontend.md](../../../../.claude/rules/frontend.md) の `apps/web/src/app/...` 構造と整合させる（**R0 から src/ ありで始めることで、後の構造大移動を防ぐ**）
   - `--no-eslint`：Biome 採用のため ESLint は入れない（入れたら次 step で削除する手間が増えるだけ）
   - `--turbopack`：Next.js 16+ 標準のビルド/開発 server。create-next-app の対話プロンプトを省略するため明示
   - `--app` / `--ts` / `--tailwind` / `--use-pnpm` / `--import-alias` は本プロジェクトの規約に従う
4. **`pnpm-workspace.yaml`（apps/web 直下、pnpm 11+ の設定ファイル）の `allowBuilds:` で build script を許可**：
   - pnpm 11+ はセキュリティ既定で postinstall 等の任意 script を明示許可しないと走らせない
   - Next.js は `sharp`（画像最適化ネイティブ実装）と `unrs-resolver`（ESLint/TS module 解決ネイティブ実装）の 2 つを必要とするため、`allowBuilds: { sharp: true, unrs-resolver: true }` を書く
   - 許可しないと dev 起動時に sharp 警告 + 画像最適化の一部経路 fallback、unrs-resolver で lint/typecheck が JS フォールバックに落ちて遅くなる
5. **`pnpm install` を実行**：lockfile 生成 + build script 実行
6. **元 README.md を「実装後」の内容に書き換え**（create-next-app の汎用 README を残さず、本 app の役割・タスク起動方法を書く）

**完了確認**：
```bash
cd apps/web
mise exec -- pnpm install              # 警告無しで完了
mise exec -- pnpm exec next build      # `Generating static pages (4/4)` 等が出て成功
```

**前提**：本ファイルの「1. Node.js / pnpm 調査 → mise install」

**関連 ADR**：[ADR 0036](../../../adr/0036-frontend-monorepo-pnpm-only.md) / [ADR 0018](../../../adr/0018-biome-for-tooling.md)

---

## 3. Frontend ツール群を最新版で追加 + 雛形の React / TypeScript を最新化

**目的**：`pnpm create next-app` が入れた版数は `latest` 解決とはいえ、React patch や TypeScript メジャーが追いついていないことがある。**本ステップで `pnpm outdated` を回し、React / TypeScript を最新に揃える**。同時に本プロジェクトで採用する Biome / Knip / syncpack / Vitest / RTL / Playwright を `pnpm add -D` で導入する（**いずれも `pnpm add -D <name>` がレジストリの最新を取りにいく仕様**を活用、`@latest` 明示でもよい）。

**作業内容**：
1. **ESLint 除去**：`mise exec -- pnpm remove eslint eslint-config-next` + `rm apps/web/eslint.config.mjs`（Biome 採用、[ADR 0018](../../../adr/0018-biome-for-tooling.md)）
2. **Frontend ツール一括追加**：
   ```bash
   mise exec -- pnpm add -D \
     @biomejs/biome \
     knip \
     syncpack \
     vitest \
     @vitest/coverage-v8 \
     @vitejs/plugin-react \
     @testing-library/react \
     @testing-library/jest-dom \
     @testing-library/user-event \
     jsdom \
     @playwright/test
   ```
3. **既存 dep の最新化**：`mise exec -- pnpm outdated` で patch / minor / major の差分を確認。React / TypeScript / @types/node 等を `pnpm update <pkg>@latest` で揃える
   - **メジャー upgrade には CHANGELOG 確認**：TypeScript / Next.js のメジャー bump は peer dep / breaking 変更で雛形が落ちないか確認してから採用
   - `tsc --noEmit` がパスすれば採用可
4. **`package.json` の `scripts` を整える**（次 step の設定ファイルから参照される）：
   ```jsonc
   "scripts": {
     "dev": "next dev",
     "build": "next build",
     "start": "next start",
     "lint": "biome lint",
     "lint:fix": "biome lint --write",
     "format": "biome check --linter-enabled=false",
     "format:fix": "biome check --linter-enabled=false --write",
     "check": "biome check",
     "check:fix": "biome check --write",
     "tsc": "tsc --noEmit",
     "knip": "knip",
     "syncpack": "syncpack lint",
     "test": "vitest",
     "test:run": "vitest run",
     "test:coverage": "vitest run --coverage",
     "e2e": "playwright test"
   }
   ```
   - `generate:api`（Hey API）は **`@hey-api/openapi-ts` 未導入なので R1（型同期パイプライン構築フェーズ）で追加**。R0 時点で書くと knip の "Unlisted binaries" で fail する

**完了確認**：
```bash
cd apps/web
mise exec -- pnpm outdated      # 残差が無い / 残ったメジャーは意図的に保留したものだけ
```

**前提**：本ファイルの「2. apps/web に Next.js 雛形を作成」

**関連 ADR**：[ADR 0018](../../../adr/0018-biome-for-tooling.md) / [ADR 0024](../../../adr/0024-syncpack-package-json-consistency.md) / [ADR 0038](../../../adr/0038-test-frameworks.md)

---

## 4. Frontend ツール設定ファイルを apps/web 直下に配置

**目的**：Biome / Knip / syncpack / Vitest / Playwright の設定を `apps/web/` 直下に置く（root には置かない、[ADR 0036](../../../adr/0036-frontend-monorepo-pnpm-only.md)）。**別プロジェクト axon（`/Users/jinboyouhei/Documents/site/axon/frontend/`）に既に実戦投入済みの設定があるので、これを叩き台にしてプロジェクト固有差分を上書きする**。

### 4-1. `apps/web/biome.jsonc`（axon の biome.json を踏襲）

axon との共通項として残すもの：
- `vcs.useIgnoreFile: true`（.gitignore を尊重して重複定義を防ぐ）
- `files.ignoreUnknown: true`（画像等の混入耐性）
- `linter.domains: { next: "recommended", react: "recommended" }`（Biome 2.x の Next/React 専用ルールセット）
- `linter.rules.suspicious.noUnknownAtRules: "off"`（Tailwind の `@theme` / `@apply` 等の at-rule を unknown 扱いさせない）
- `overrides`：Hey API 生成物 / shadcn/ui の lint / format を切る
- `assist.actions.source.organizeImports: "on"`（保存時に import 順自動整列）

本プロジェクト固有で追加するもの：
- **`css.parser.tailwindDirectives: true`**：本プロジェクトの Biome 2.4+ では `noUnknownAtRules: off` だけでは Tailwind v4 ディレクティブ（`@import "tailwindcss"` / `@theme inline`）が parse error になる。両方の指定が必須（axon は古い Biome 2.2 で前者だけで通せていたが現行版では不可）
- `javascript.formatter`：`quoteStyle: "double"` / `semicolons: "always"` / `formatter.indentWidth: 2` / `lineWidth: 100`
- `files.includes` から除外する path はプロジェクト構造に合わせて `!.next` `!next-env.d.ts` `!src/app/__generated__` `!src/components/ui`

### 4-2. `apps/web/knip.config.ts`（axon の knip.config.ts を踏襲）

axon との共通項：
- `entry` は Next.js App Router の規約ファイル（`page` / `layout` / `loading` / `error` / `global-error` / `not-found` / `route` / `template` / `default`）に限定 — `_components/` / `_hooks/` 配下の孤立コードを検出するため
- `ignoreDependencies` に `tailwindcss`（postcss 経由）/ Testing Library 系（テスト追加時に使用）

本プロジェクト固有：
- **R0 時点では src/app しか存在しない**ため、`project` は `src/app/**/*.{ts,tsx}` 1 件のみ。`src/components` / `src/hooks` / `src/lib` 関連の `ignore` / `project` patterns は R1 で当該ディレクトリ追加時に axon の構成に拡張する
- patterns が `(no matches)` 状態だと knip が "Configuration hints" を出して noisy になるため、**実存ディレクトリだけに絞る**

### 4-3. `apps/web/.syncpackrc.ts`（apps/web 単一 package.json 構成、[ADR 0024](../../../adr/0024-syncpack-package-json-consistency.md) Note）

本プロジェクトはモノレポでも apps/web は単一 package.json なので、syncpack の主用途「複数 package.json 間のバージョン整合」は不要。書式整合 3 ルールに縮小：
- `sortPackages: true`
- `sortFirst: ["name", "version", "private", "type", "scripts"]`
- `sortAz: ["dependencies", "devDependencies", "peerDependencies", "optionalDependencies"]`
- `versionGroups: []` / `semverGroups: []`（明示的に空）

### 4-4. `apps/web/vitest.config.ts` + `apps/web/vitest.setup.ts`

- `vitest.config.ts`：`environment: "jsdom"` / `globals: true` / `setupFiles: ["./vitest.setup.ts"]` / `plugins: [react()]` / `exclude: ["**/.next/**", "**/e2e/**"]`
- `vitest.setup.ts`：`import "@testing-library/jest-dom/vitest"` の 1 行（matcher を expect に組込み）

### 4-5. `apps/web/playwright.config.ts`

- R0 では雛形のみ、R5 で本格利用
- `testDir: "./e2e"`（Vitest と分離）/ `baseURL: "http://localhost:3000"` / `forbidOnly: !!process.env.CI` / `retries: process.env.CI ? 2 : 0`

**完了確認**：
```bash
cd /path/to/repo  # root に戻ってもよい
mise run web:lint           # Biome 緑
mise run web:typecheck      # tsc 緑
mise run web:knip           # Knip 緑（exit 0、hints 0）
mise run web:syncpack       # syncpack 緑
```

**前提**：本ファイルの「3. Frontend ツール群を最新版で追加」

**関連 ADR**：[ADR 0018](../../../adr/0018-biome-for-tooling.md) / [ADR 0021](../../../adr/0021-r0-tooling-discipline.md) / [ADR 0024](../../../adr/0024-syncpack-package-json-consistency.md) / [ADR 0038](../../../adr/0038-test-frameworks.md)

---

## 5. mise.toml の Next.js タスク稼働確認

**目的**：[01-foundation.md](./01-foundation.md) で mise.toml に**先回りで定義済み**の `web:*` タスク群が、apps/web の実体（package.json + pnpm-lock.yaml + src/app/ + 設定ファイル）が揃ったこの時点で正しく動作することを確認する（02-python.md step 9 と同じパターン）。

**前提済の登録タスク**（[mise.toml](../../../../mise.toml) の `[tasks."web:*"]`、本 step では追記しない）：
- `web:dev` — `pnpm dev`（next dev）
- `web:test` — `pnpm test`（vitest）
- `web:e2e` — `pnpm exec playwright test`（R5 で本格使用）
- `web:lint` / `web:format` — `pnpm exec biome check [.|--write .]`
- `web:typecheck` — `pnpm exec tsc --noEmit`
- `web:knip` / `web:knip-fix` — `pnpm exec knip [--fix]`
- `web:syncpack` / `web:syncpack-format` — `pnpm exec syncpack [lint|format]`
- `web:types-gen` — `pnpm exec openapi-ts`（R1 で `@hey-api/openapi-ts` 導入後に有効化、R0 時点では exit 1 で構わない）

**作業内容**：
1. `mise tasks | grep ^web:` で全 `web:*` タスクが list されることを確認
2. **動作するもの**を順に起動：
   - `mise run web:lint` → `No fixes applied.`
   - `mise run web:typecheck` → 出力なし（緑）
   - `mise run web:knip` → 出力なし（緑）
   - `mise run web:syncpack` → `No issues found`
3. **動作しないもの**（パッケージ未導入）：
   - `web:types-gen` は R0 時点では `@hey-api/openapi-ts` 未導入のため exit 1。step 8（GitHub Actions）でも CI に組み込まない。R1 で `pnpm add -D @hey-api/openapi-ts` してから雛形 `openapi-ts.config.ts` を置く

**完了確認**：上記 4 タスクが緑で抜ける。

**前提**：本ファイルの「4. Frontend ツール設定ファイルを apps/web 直下に配置」

**関連 ADR**：[ADR 0039](../../../adr/0039-mise-for-task-runner-and-tool-versions.md)

---

## 6. lefthook.yml に Next.js 用 pre-commit 追加

**目的**：ローカル commit 時に Next.js の lint / typecheck / knip を自動発火させ、規約逸脱を hook で弾く。

**追記内容**：
- `pre-commit` セクションに以下を追加：
  - `web-biome`：ステージ済 `apps/web/**/*.{ts,tsx,js,jsx,json,jsonc,css}` に `mise exec -- biome check --write` を実行（`stage_fixed: true`）
  - `web-typecheck`：`apps/web/**/*.{ts,tsx}` 変更時に `mise exec -- pnpm -C apps/web exec tsc --noEmit` を実行
  - `web-knip`：apps/web 直下の変更で `mise exec -- pnpm -C apps/web exec knip --no-progress` を実行（重い場合は CI 専用に切り替え）
- `mise exec --` 経由で起動する理由は [lefthook.yml の commit-msg 設定コメント](../../../../lefthook.yml) と同じ（Git フックの非対話シェルに対する shims 解決）

**完了確認**：
```bash
echo "const x: number = 'string';" > apps/web/src/app/_test.ts   # 型エラーを仕込む
git add apps/web/src/app/_test.ts && git commit -m "test"        # pre-commit が exit 1 で止まる
git restore --staged apps/web/src/app/_test.ts && rm apps/web/src/app/_test.ts
```

**前提**：本ファイルの「5. mise.toml の Next.js タスク稼働確認」

---

## 7. lefthook.yml に Next.js 用 pre-push 追加

**目的**：push 直前に **動的検証（unit テスト + 本番ビルド）** を発火させ、pre-commit の静的検査と CI の間にあるギャップを埋める。`tsc --noEmit` だけでは見えない RSC / SSG / image 最適化などの本番ビルド段階固有のエラーを `next build` で先回り検出する。

**追記内容**（`pre-push` セクション）：

```yaml
pre-push:
  commands:
    web-vitest:
      glob: "apps/web/**/*.{ts,tsx}"
      root: apps/web
      run: mise exec -- pnpm exec vitest run
    web-next-build:
      glob: "apps/web/**/*.{ts,tsx,css,json}"
      root: apps/web
      run: mise exec -- pnpm exec next build
```

**設計判断**：
- **vitest run（unit のみ）**：高速（数秒）。E2E（Playwright）は遅すぎ + バックエンド + DB 必須なので CI 専用に隔離（→ [ADR 0038](../../../adr/0038-test-frameworks.md)）
- **next build を含める判断**：30〜60 秒の遅延コストと「CI で初めて気付く」リスクのトレードオフ。本プロジェクトは pre-commit に静的検査を集約済なので、push 段階で本番ビルドを通すことに価値がある
- **`glob` で apps/web 変更時のみ発火**：Backend / Worker / docs のみの push では起動しない
- **`mise exec --` 経由**：pre-commit と同じ理由

**完了確認**：
```bash
# RSC エラーを仕込む（例：Server Component で window 参照）
mkdir -p apps/web/src/app/_test
echo "export default function P() { window.foo; return null; }" > apps/web/src/app/_test/page.tsx
git add apps/web/src/app/_test/page.tsx && git push   # web-next-build が exit 1 で止まる
git restore --staged apps/web/src/app/_test/ && rm -rf apps/web/src/app/_test/
```

**前提**：本ファイルの「6. lefthook.yml に Next.js 用 pre-commit 追加」

**関連 ADR**：[ADR 0038](../../../adr/0038-test-frameworks.md)

---

## 8. GitHub Actions に Next.js ジョブ追加

**目的**：[01-foundation.md: 4. GitHub Actions ワークフロー雛形](./01-foundation.md#4-github-actions-ワークフロー雛形-) で整備したワークフローに Frontend 用ジョブを追加し、hook bypass された逸脱もリモートで弾く。

**追記内容**（[.github/workflows/ci.yml](../../../../.github/workflows/ci.yml)）：
- 新規ジョブ 5 種：`web-lint` / `web-typecheck` / `web-knip` / `web-syncpack` / `web-test`
  - 各ジョブで `actions/checkout` → `jdx/mise-action`（SHA pin、内部で `mise install` 実行）→ `mise run web:<task>`
  - `mise install` が pnpm を入れるため `pnpm/action-setup` は **不要**（pnpm の cache が欲しい場合は別途検討）
- `ci-success` の `needs:` に上記 5 ジョブを追加

**完了確認**：
- PR を作ると `web-lint` / `web-typecheck` / `web-knip` / `web-syncpack` / `web-test` の 5 ジョブが並列で走る
- いずれかが失敗すると `ci-success` も赤になり、Branch protection で merge がブロックされる

**前提**：本ファイルの「6. lefthook.yml に Next.js 用 pre-commit 追加」+「7. lefthook.yml に Next.js 用 pre-push 追加」（ローカル品質ゲートが緑）

**関連 ADR**：[ADR 0026](../../../adr/0026-github-actions-incremental-scope.md) / [ADR 0031](../../../adr/0031-ci-success-umbrella-job.md)

---

## 9. dependabot.yml の `npm` コメントアウト解除

**目的**：apps/web の npm 依存（`apps/web/package.json` + `apps/web/pnpm-lock.yaml`）を Dependabot の週次自動更新対象に含める。

**作業内容**（[.github/dependabot.yml](../../../../.github/dependabot.yml)）：
- 既存テンプレ（コメントアウト済みブロック）のコメントアウト解除
- `directory: /apps/web` を指定（apps/web 配下が真の SSoT、[ADR 0036](../../../adr/0036-frontend-monorepo-pnpm-only.md)）
- `version-update:semver-major` を `ignore` に追加（メジャー更新は手動運用、→ [ADR 0028](../../../adr/0028-dependabot-auto-update-policy.md)）
- グループ化：`@types/*` / `@biomejs/*` + `biome` / `@hey-api/*` / `react` + `react-*` + `next` / `@playwright/*` + `playwright`

**完了確認**：
- 翌週月曜 06:00 JST に `build(deps)` / `build(deps-dev)` の自動 PR が生成される
- もしくは GitHub UI から `Insights → Dependency graph → Dependabot` で手動 trigger で確認

**関連 ADR**：[ADR 0028](../../../adr/0028-dependabot-auto-update-policy.md)

---

## このフェーズ完了時点で揃うもの

- 🟢 apps/web が `mise run web:dev` で起動し、`http://localhost:3000` で Next.js 雛形が見える
- 🟢 Biome / tsc / Knip / syncpack がローカル + CI 両方で動く
- 🟢 規約違反コミットが pre-commit hook で弾かれる
- 🟢 Next.js 依存の自動更新 PR が週次で来る

---

## R0 完了

R0 全項目（[setup/01-foundation.md](./01-foundation.md) / [02-python.md](./02-python.md) / 本ファイル / [04-go.md](./04-go.md)）が全て緑になった時点で R0 完了。`docker compose up && mise run api:dev && mise run web:dev && mise run worker:grading:dev` で開発環境が全言語で立ち上がり、CI が緑になる状態が達成される。

次は R1 MVP：[../01-roadmap.md](../01-roadmap.md) の「Now：R1 MVP」セクション（[F-01 GitHub OAuth](../../4-features/F-01-github-oauth-auth.md) から開始）。
