# 0036. Frontend ツーリングを apps/web 内に閉じ、root を orchestration 専用層に縮小（Turborepo + pnpm workspaces 不採用）

- **Status**: Accepted
- **Date**: 2026-05-09 <!-- 当初の「pnpm workspaces のみ採用」から「pnpm 自体を apps/web 内に閉じ、Biome / Knip / syncpack も apps/web 内に再配置」に拡張 -->
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

<!-- ※本 ADR の Context は Python pivot（ADR 0033）以前の状況（NestJS + apps/grading-worker + packages/*）を記述しているが、Decision（pnpm を apps/web/ 内に閉じる + Turborepo 不採用）は pivot 後も有効。Python pivot 後の現行構成は ADR 0033 / 0035 / 0040 を参照。 -->

[ADR 0023](./0023-turborepo-pnpm-monorepo.md) で TS 版時代に **Turborepo + pnpm workspaces** を採用していた。当時の前提：

- `apps/web`（Next.js）+ `apps/api`（NestJS）+ `apps/grading-worker`（Go）+ `packages/*` の **複数アプリ構成**
- Turborepo の並列ビルド・依存グラフ・リモートキャッシュ（Vercel 統合）が複数アプリ運用で価値を発揮

[ADR 0033](./0033-backend-language-pivot-to-python.md) で **Backend が Python (FastAPI) に pivot** された結果、TS 側の構成は以下に変化した：

- **TS apps**：`apps/web`（Next.js）の **1 アプリのみ**
- **TS packages**：`packages/shared-types` / `packages/prompts` / `packages/config`（小規模、Python から参照される共有スキーマ・LLM プロンプト等）
- **Backend (Python)**：別ツール `uv` で workspace 管理（→ [ADR 0035](./0035-uv-for-python-package-management.md)）
- **Worker (Go)**：`go mod` で独立管理

選定にあたっての要請：

- 1 アプリ + 数 package の小規模 TS 構成に対し、Turborepo の **設定保守コスト**と**価値**が見合うか再評価する
- ADR 0023 の Superseded by 0033 状態を踏まえ、Frontend 用途として継続採用するか縮小するかを確定する

判断のために参照した情報源：

- [Self-hosting Next.js without full monorepo dependencies (vercel/next.js Discussion #85099)](https://github.com/vercel/next.js/discussions/85099)
- [T3 Turbo vs T3 Stack 2026 - StarterPick](https://starterpick.com/guides/t3-turbo-vs-t3-stack-2026)

## Decision（決定内容）

Frontend のモノレポ管理は **「pnpm を `apps/web/` 内に閉じる、root には Frontend ツーリングを置かない」** 設計を採用する。Turborepo と pnpm workspaces は不採用。Biome / Knip / syncpack は採用維持で配置を `apps/web/` に移動、syncpack はルールセットを縮小する。

### Frontend ツーリングの所在

- **pnpm**：`apps/web/` 配下のみで動作。`apps/web/package.json` / `apps/web/pnpm-lock.yaml` / `apps/web/node_modules/`
- **Biome / Knip / TypeScript / tsconfig.json**：`apps/web/` 配下に配置（`apps/web/biome.jsonc` 等）
- **syncpack**：`apps/web/.syncpackrc.ts` に配置。ルールセットは単一 package.json でも有効な 3 件（depType 重複検知 / キー順整形 / `^` 統一）に縮小（→ [ADR 0024](./0024-syncpack-package-json-consistency.md) Note）
- **Turborepo**：不採用（旧 ADR 0023 の Superseded、§Why 1 参照）
- **pnpm workspaces**：不採用（Frontend が単一 app のため workspace 機能の価値ドライバが効かない、§Why 4 参照）

### root の役割（orchestration 専用層）

root には言語横断の orchestration / Git フック / コミット規約のみを置く：

- `mise.toml`（タスク + tool 版数 SSoT、→ [ADR 0039](./0039-mise-for-task-runner-and-tool-versions.md)）
- `lefthook.yml`（Git フック、commit-msg のみ。pre-commit フックの言語別追加は app 着手時）
- `commitlint.config.mjs`（`.ts` ではなく `.mjs`、root の TS 依存をゼロ化）
- `package.json`（`@commitlint/cli` / `@commitlint/config-conventional` / `lefthook` のみの最小構成）
- `.gitignore` / `README.md` / `LICENSE` / `CONTRIBUTING.md` / `SYSTEM_OVERVIEW.md`
- `docs/` / `infra/` / `apps/` / `packages/prompts/`

### タスク実行の経路

すべて `mise run <task>` 経由（→ [ADR 0039](./0039-mise-for-task-runner-and-tool-versions.md)）。`apps/web` 配下のタスクは mise.toml に `dir = "apps/web"` を指定し、`pnpm run dev` 等を delegate する形にする。

[ADR 0023](./0023-turborepo-pnpm-monorepo.md) と [ADR 0024](./0024-syncpack-package-json-consistency.md) は本 ADR と [ADR 0033](./0033-backend-language-pivot-to-python.md) の組み合わせで Superseded。

## Why（採用理由）

### 1. Turborepo の価値ドライバが現構成に存在しない

Turborepo の主要価値は以下 3 点：

- **並列タスク実行**：複数 app / package を同時ビルド・テスト → **app は Next.js 単独のため並列対象なし**
- **依存グラフ駆動の incremental build**：A が変わったら B も rebuild → **app が 1 つのため依存グラフが浅い**
- **リモートキャッシュ（Vercel 統合）**：チーム間でビルド成果物を共有 → **個人 portfolio で共有相手なし**

3 ドライバすべてが効かない構成では、Turborepo の設定維持コスト（`turbo.jsonc` / pipeline 定義 / `dependsOn` 管理）が純粋な負債になる。

### 2. Web 調査結果の業界コンセンサス

- 「**single Next.js app では Turborepo はオーバーヘッド**」（vercel/next.js Discussion #85099）
- 「web-only product なら T3 Stack（単一 Next.js app）、複数 app / mobile が必要なら T3 Turbo」（StarterPick 2026）
- 「Turborepo の複雑度は monorepo に複数 apps / shared components がある場合のみ正当化される」（pronextjs.dev）

### 3. pnpm workspaces 単体で本プロジェクトの要件は満たせる

- `packages/shared-types` / `packages/prompts` / `packages/config` への symlink 解決：pnpm workspaces で自動
- `workspace:*` プロトコルでの内部参照：pnpm workspaces ネイティブ
- Next.js の build：`next build` 単体で完結、Turborepo 経由の必要なし
- 型生成パイプライン（[ADR 0006](./0006-json-schema-as-single-source-of-truth.md)）：npm scripts チェーンで十分

### 4. ツール散逸の抑制

[ADR 0033](./0033-backend-language-pivot-to-python.md) の Python pivot 以降、3 言語ポリグロット構成で各言語のツール選定 ADR が必要になっている：

- Python: uv（[ADR 0035](./0035-uv-for-python-package-management.md)）
- Go: go mod（標準）
- TS: pnpm workspaces（本 ADR）

各言語で **「言語標準のツール 1 本」**に揃えることで、ツール学習・保守コストを最小化する。Turborepo は「言語標準」ではなく追加レイヤなので、価値が見合わなければ削る方が CLAUDE.md の「**規模に応じた選定**」原則と整合する。

### 5. 復帰コストが低い

将来 Turborepo が必要になった場合（Frontend 拡張時）の復帰コストは小さい：

- `pnpm-workspace.yaml` を残したまま `turbo.jsonc` と pipeline 定義を追加するだけ
- パッケージ構造は無変更で済む
- 削除する設定は `turbo.jsonc` 1 ファイル + `package.json` の `turbo` script、再導入も同 1 ファイル + script 復活で済む

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| **pnpm workspaces のみ（採用）** | 言語標準のモノレポ機能で完結 | — |
| pnpm workspaces + Turborepo 維持 | ADR 0023 を Superseded から復活させて Frontend 用途として継続 | 単一 Next.js app では並列ビルド・依存グラフ・リモートキャッシュの価値ドライバが効かず、設定維持コストが純粋な負債になる |
| Nx | 複雑な monorepo 向けの強力なタスクランナー | Turborepo より重量級。本プロジェクト規模に対し過剰、学習コストも高い |
| Lerna | 旧来の JS monorepo ツール | Nx に吸収され実質的にメンテ縮小、新規採用する理由なし |
| npm workspaces | Node.js 標準の workspace 機能 | pnpm 比で依存解決が遅く、disk 効率も悪い。本プロジェクトは pnpm 採用済みなので変更理由なし |
| Yarn workspaces | Yarn berry の workspace 機能 | pnpm の代替案だが、pnpm の方が disk 効率と速度で優位。乗り換える理由なし |

## Consequences（結果・トレードオフ）

### 得られるもの

- **設定保守コストの削減**：`turbo.jsonc` / pipeline 定義 / `dependsOn` 管理が不要
- **言語標準ツール 1 本に揃った構成**：Python (uv) / Go (go mod) / TS (pnpm workspaces) の 1 言語 1 ツール
- **学習コスト低減**：Turborepo 固有の概念（pipeline / outputs / cache key 等）を新規参画者が学ぶ必要なし
- **Vercel リモートキャッシュへのロックイン回避**：Vercel 以外のホスティング（[ADR 0013](./0013-vercel-for-frontend-hosting.md)）への移行余地を残せる

### 失うもの・受容するリスク

- **将来 Frontend を拡張した場合（mobile app 追加 / 複数 web app 化等）に Turborepo 復帰コストが発生**：ただし復帰は小規模（`turbo.jsonc` 追加のみ）
- **並列ビルド・キャッシュの恩恵を諦める**：app が 1 つのため影響は最小、CI ビルド時間は Next.js 単体の build 時間に支配される
- **Turborepo の経験を portfolio で語る機会を失う**：ただし「**Turborepo を入れない判断ができた**」こと自体が「規模に応じた選定能力」の証明として portfolio に書ける

### 派生 1：`packages/config/` の廃止

本 ADR の「Frontend は単一 Next.js app」という現実から、`packages/config/`（multi-consumer 前提の TS 設定共有パッケージ、[ADR 0018](./0018-biome-for-tooling.md) で導入）も**廃止**：

- `packages/config/` の存在意義は「**複数 TS workspace が tsconfig / Vitest base を共有する**」こと
- 本 ADR で TS app が `apps/web/` 1 個と確定した結果、**消費者が単一**になり multi-consumer 前提が成立しない
- tsconfig / vitest.config.ts 等は `apps/web/` 直下に直接配置すれば足り、`packages/config/` の Layer 2 抽象は YAGNI 違反

### 派生 2：`syncpack` を apps/web 内に移動 + ルールセット縮小

[ADR 0024](./0024-syncpack-package-json-consistency.md) の syncpack はツール採用そのものは維持し、Biome と同じく **配置を root → `apps/web/` に移動**、**ルールセットを縮小**する：

- **継続採用ルール（単一 package.json でも有効）**：
  1. `dependencies` / `devDependencies` の重複検知（同じパッケージの両方定義を検出）
  2. `package.json` キー順整形
  3. semver 範囲指定子 `^` の統一
- **不採用ルール（multi-workspace 必須、対象消滅）**：
  1. ~~外部依存の全 workspace 同一バージョン~~（apps/web 1 個のため）
  2. ~~内部 workspace パッケージ `workspace:*` 固定~~（内部 pkg 不在のため）
- **配置**：`apps/web/.syncpackrc.ts`（apps/web の devDep として syncpack を投入）
- **起動経路**：`mise run web-syncpack`（apps/web 着手時に `mise.toml` + `lefthook.yml` + `ci.yml` に追加）

詳細は [ADR 0024](./0024-syncpack-package-json-consistency.md) の Note を参照。

**再拡張の余地**：将来 `apps/web/` 内部が multi-package 構成（例：`apps/web/packages/ui` 等の UI ライブラリ分離 / Storybook 独立等）に拡張された場合、不採用にした 2 ルール（同一バージョン / `workspace:*`）も apps/web 内で復活させる判断は妥当（→ §将来の見直しトリガー）。

### 派生 3：`pnpm workspaces` の不採用

旧版の本 ADR では「pnpm workspaces のみ採用、Turborepo 不採用」だったが、上記 2 派生（`packages/config/` 廃止 + `packages/shared-types` 不採用 → ADR 0006）の結果、**workspace 構造そのものが消滅**した：

- workspace member は `apps/web` のみで、root と apps/web は互いに `workspace:*` 参照しない（依存が完全に分離）
- pnpm workspace 機能（hoisted node_modules / 単一 lockfile / `workspace:*` プロトコル）の価値ドライバが全て不発
- `pnpm-workspace.yaml` を削除し、`apps/web/` を独立した pnpm プロジェクトとする
- root には pnpm の orchestration-only パッケージ（commitlint + lefthook のみ）を残す

### 将来の見直しトリガー

- **Frontend が複数 app 構成に拡張される場合**（mobile app 追加 / web admin 分離 / Storybook 独立等）→ Turborepo 復帰を検討、新規 ADR を起票
- **`apps/web/` が内部 multi-package 構成に拡張される場合**（apps/web/packages/ui 等の UI ライブラリ分離）→ apps/web 内で `syncpack` 再導入を検討、ADR 0024 復活 or 新規 ADR 起票
- **CI のビルド時間が運用 pain になる場合**（5 分超等）→ Turborepo + リモートキャッシュ採用を再検討
- **チーム開発に移行した場合**（個人 portfolio から複数人開発に変化）→ リモートキャッシュ価値が出るので Turborepo 復帰を検討

## References

- [ADR 0023: Turborepo + pnpm workspaces](./0023-turborepo-pnpm-monorepo.md)（Superseded by 0033、本 ADR で pnpm workspaces 部分のみ選択的継承）
- [ADR 0033: バックエンドを Python に pivot](./0033-backend-language-pivot-to-python.md)（Backend Python 化により TS 側構成が縮小した契機）
- [ADR 0035: Python のパッケージ管理に uv を採用](./0035-uv-for-python-package-management.md)（Python 側のモノレポ管理）
- [ADR 0013: Frontend ホスティングに Vercel を採用](./0013-vercel-for-frontend-hosting.md)（リモートキャッシュ非採用の文脈）
- [ADR 0006: Pydantic を SSoT、用途別 2 伝送路で各言語に展開](./0006-json-schema-as-single-source-of-truth.md)（共有型 SSoT を `apps/api/` 内に閉じ、`packages/shared-types` 等の TS package を不採用とした根拠）
- [pnpm workspaces 公式](https://pnpm.io/workspaces)
- [Self-hosting Next.js without full monorepo dependencies](https://github.com/vercel/next.js/discussions/85099)
