# 03. Next.js 環境構築（🔴 未着手）

> **守備範囲**：Next.js ランタイム（Node.js + pnpm）取得から apps/web を品質ゲート付きで動かすまでの 6 ステップ。本フェーズが終わると、Next.js の lint / typecheck / knip がローカル + CI 両方で緑になり、依存自動更新が走り始める。
> **前提フェーズ**：[02-python.md](./02-python.md) 完了済（Python 縦スライスと同じ「品質ゲートのステップ」パターンを再利用する）
> **次フェーズ**：R0 完了 → R1（[../01-roadmap.md](../01-roadmap.md) の「Now：R1 MVP」セクション）

---

## 1. mise install node && mise install pnpm

**目的**：[01-foundation.md: 3. mise 導入](./01-foundation.md#3-mise-導入-) の `mise.toml` で pin 済の Node.js 22 / pnpm を実体化する。

**コマンド**：
```bash
mise install node
mise install pnpm
```

**完了確認**：
```bash
node --version   # v22.x
pnpm --version   # 11.x（または mise.toml 固定の版数）
```

**前提**：[01-foundation.md: 3. mise 導入](./01-foundation.md#3-mise-導入-)（mise.toml に `node = "22"` / `pnpm = "latest"` が pin されている）

**関連 ADR**：[ADR 0039](../../../adr/0039-mise-for-task-runner-and-tool-versions.md)

---

## 2. apps/web 環境構築

**目的**：apps/web に pnpm workspace を初期化し、Next.js 雛形と Next.js ツール一式を `apps/web/` 配下に閉じる形で配置する。

**作業内容**：
1. `apps/web/` に Next.js 雛形を作成（`pnpm create next-app apps/web --ts --app --tailwind`）
2. `apps/web/package.json` を pnpm workspace に登録（root の `pnpm-workspace.yaml`）
3. Frontend ツール群を `apps/web/` 直下に直接配置（root に置かない）：
   - `apps/web/biome.jsonc` — Biome 設定
   - `apps/web/knip.config.ts` — Knip（未使用検出）設定
   - `apps/web/.syncpackrc.ts` — syncpack（package.json 整合性）設定
   - `apps/web/tsconfig.json` — TypeScript 設定
4. `pnpm install` で lockfile（`apps/web/pnpm-lock.yaml`）生成

**完了確認**：
```bash
cd apps/web
pnpm install
pnpm exec biome check .         # Biome が動く
pnpm exec tsc --noEmit          # tsc が動く
pnpm exec knip                  # knip が動く
```

**前提**：本ファイルの「1. mise install node && mise install pnpm」

**関連 ADR**：[ADR 0036](../../../adr/0036-frontend-monorepo-pnpm-only.md) / [ADR 0018](../../../adr/0018-biome-for-tooling.md) / [ADR 0024](../../../adr/0024-syncpack-package-json-consistency.md)

---

## 3. mise.toml に Next.js タスク追記

**目的**：apps/web 配下のツール起動経路を `mise run web:*` に統一する。

**追記するタスク（最低限）**：
- `web:dev` — `next dev`
- `web:test` — `vitest`（R1 でテスト対象コードが入ってから本格使用）
- `web:e2e` — `playwright test`（R5 で本格使用）
- `web:lint` — `biome check .`
- `web:format` — `biome check --write .`
- `web:typecheck` — `tsc --noEmit`
- `web:knip` — `knip`
- `web:syncpack` — `syncpack lint`
- `web:types-gen` — Hey API で OpenAPI から TS 型 + Zod + クライアント生成（型同期パイプライン構築フェーズで本格使用、R0 では雛形のみ）

**完了確認**：
```bash
mise tasks | grep web:
mise run web:lint   # Biome が起動
```

**関連 ADR**：[ADR 0039](../../../adr/0039-mise-for-task-runner-and-tool-versions.md)

---

## 4. lefthook.yml に Next.js 用 pre-commit 追加

**目的**：ローカル commit 時に Next.js の lint / typecheck / knip を自動発火させ、規約逸脱を hook で弾く。

**追記内容**：
- `pre-commit` セクションに以下を追加：
  - `biome-check`：ステージ済 `apps/web/**/*.{ts,tsx,js,jsx,json,jsonc}` に `mise exec -- biome check --write` を実行（`stage_fixed: true`）
  - `web-typecheck`：`apps/web/**/*.{ts,tsx}` 変更時に `mise exec -- tsc --noEmit` を実行
  - `knip`：apps/web 直下の変更で `mise exec -- knip --no-progress` を実行（重い場合は CI 専用に切り替え）
- `mise exec --` 経由で起動する理由は [lefthook.yml の commit-msg 設定コメント](../../../../lefthook.yml) と同じ（Git フックの非対話シェルに対する shims 解決）

**完了確認**：
```bash
echo "const x: number = 'string';" > apps/web/_test.ts   # 型エラーを仕込む
git add apps/web/_test.ts && git commit -m "test"        # pre-commit が exit 1 で止まる
git restore --staged apps/web/_test.ts && rm apps/web/_test.ts
```

**前提**：本ファイルの「3. mise.toml に Next.js タスク追記」

---

## 5. lefthook.yml に Next.js 用 pre-push 追加

**目的**：push 直前に **動的検証（unit テスト + 本番ビルド）** を発火させ、pre-commit の静的検査と CI の間にあるギャップを埋める。`tsc --noEmit` だけでは見えない RSC / SSG / image 最適化などの本番ビルド段階固有のエラーを `next build` で先回り検出する。

**追記内容**（`pre-push` セクション）：

```yaml
pre-push:
  commands:
    vitest:
      run: mise exec -- vitest run --dir apps/web
    next-build:
      run: mise exec -- next build apps/web
```

**設計判断**：
- **vitest run（unit のみ）**：高速（数秒）。E2E（Playwright）は遅すぎ + バックエンド + DB 必須なので CI 専用に隔離（→ [ADR 0038](../../../adr/0038-test-frameworks.md)）
- **next build を含める判断**：30〜60 秒の遅延コストと「CI で初めて気付く」リスクのトレードオフ。本プロジェクトは pre-commit に静的検査を集約済なので、push 段階で本番ビルドを通すことに価値がある
- **`mise exec --` 経由**：pre-commit と同じ理由（Git フックの非対話シェルに対する shims 解決）

**完了確認**：
```bash
# RSC エラーを仕込む（例：Server Component で window 参照）
echo "export default function P() { window.foo; return null; }" > apps/web/app/_test/page.tsx
git add apps/web/app/_test/page.tsx && git push   # next build が exit 1 で止まる
git restore --staged apps/web/app/_test/ && rm -rf apps/web/app/_test/
```

**前提**：本ファイルの「4. lefthook.yml に Next.js 用 pre-commit 追加」

**関連 ADR**：[ADR 0038](../../../adr/0038-test-frameworks.md)

---

## 6. GitHub Actions に Next.js ジョブ追加

**目的**：[01-foundation.md: 4. GitHub Actions ワークフロー雛形](./01-foundation.md#4-github-actions-ワークフロー雛形-) で整備したワークフローに Frontend 用ジョブを追加し、hook bypass された逸脱もリモートで弾く。

**追記内容**（[.github/workflows/ci.yml](../../../../.github/workflows/ci.yml)）：
- 新規ジョブ：`web-lint`、`web-typecheck`、`web-knip`、`web-syncpack`
  - 各ジョブで `mise install` → `mise run web:<task>` を実行
  - `actions/checkout` + `jdx/mise-action` を SHA ピン止めで使用
  - `pnpm/action-setup` を SHA ピン止めで追加（`pnpm install` の cache 用）
- `ci-success` の `needs:` に上記 4 ジョブを追加

**完了確認**：
- PR を作ると `web-lint` 〜 `web-syncpack` が走る
- いずれかが失敗すると `ci-success` も赤になり、Branch protection で merge がブロックされる

**前提**：本ファイルの「4. lefthook.yml に Next.js 用 pre-commit 追加」+「5. lefthook.yml に Next.js 用 pre-push 追加」（ローカル品質ゲートが緑）

**関連 ADR**：[ADR 0026](../../../adr/0026-github-actions-incremental-scope.md) / [ADR 0031](../../../adr/0031-ci-success-umbrella-job.md)

---

## 7. dependabot.yml の `npm` コメントアウト解除

**目的**：apps/web の npm 依存（`apps/web/package.json` + `apps/web/pnpm-lock.yaml`）を Dependabot の週次自動更新対象に含める。

**作業内容**（[.github/dependabot.yml](../../../../.github/dependabot.yml)）：
- `npm` ブロックのコメントアウトを解除
- `directory: /apps/web` を指定（pnpm workspaces を Dependabot が解析できるように、必要なら `package-ecosystem: npm` で各 workspace ディレクトリを個別に列挙）
- `version-update:semver-major` を `ignore` に追加（メジャー更新は手動運用、→ [ADR 0028](../../../adr/0028-dependabot-auto-update-policy.md)）
- グループ化設定：`@types/*` / `@biomejs/*` + `biome` / `@commitlint/*` + `commitlint`

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
