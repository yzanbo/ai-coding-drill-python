# 0036. Frontend モノレポ管理を pnpm workspaces のみに縮小（Turborepo 不採用）

- **Status**: Accepted
- **Date**: 2026-05-09
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

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

Frontend のモノレポ管理は **`pnpm workspaces` のみを採用**し、**Turborepo は不採用**とする。

- **依存解決・パッケージリンク**：`pnpm workspaces`（`pnpm-workspace.yaml`）
- **タスク実行**：`pnpm --filter <pkg> <script>` を直接使用、または npm scripts のチェーン
- **キャッシュ**：Next.js 標準の `.next/cache` / Vercel デプロイ時の自動キャッシュに依存
- **リモートキャッシュ**：採用しない（必要が生じた段階で再評価）

[ADR 0023](./0023-turborepo-pnpm-monorepo.md) は **Superseded by 0033** だが、`pnpm workspaces` 部分のみを継承する形となるため、本 ADR で**選択的継承の範囲を明確化**する。

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

### 派生：`packages/config/` の廃止

本 ADR の「Frontend は単一 Next.js app」という現実から、`packages/config/`（multi-consumer 前提の TS 設定共有パッケージ、[ADR 0018](./0018-biome-for-tooling.md) で導入）も**廃止**する：

- `packages/config/` の存在意義は「**複数 TS workspace が tsconfig / Vitest base を共有する**」こと
- 本 ADR で TS app が `apps/web/` 1 個と確定した結果、**消費者が単一**になり multi-consumer 前提が成立しない
- tsconfig / vitest.config.ts 等は `apps/web/` 直下に直接配置すれば足り、`packages/config/` の Layer 2 抽象は YAGNI 違反
- 既存の `packages/config/`（現状中身は `package.json` + `README.md` のみ、実設定ファイル未投入）は本 ADR 反映時に削除する
- 将来複数 TS app 構成に拡張された場合、Turborepo 復帰検討（上記 §将来の見直しトリガー）と一緒に `packages/config/` 復活も再評価する

### 将来の見直しトリガー

- **Frontend が複数 app 構成に拡張される場合**（mobile app 追加 / web admin 分離 / Storybook 独立等）→ Turborepo 復帰を検討、新規 ADR を起票
- **CI のビルド時間が運用 pain になる場合**（5 分超等）→ Turborepo + リモートキャッシュ採用を再検討
- **チーム開発に移行した場合**（個人 portfolio から複数人開発に変化）→ リモートキャッシュ価値が出るので Turborepo 復帰を検討

## References

- [ADR 0023: Turborepo + pnpm workspaces](./0023-turborepo-pnpm-monorepo.md)（Superseded by 0033、本 ADR で pnpm workspaces 部分のみ選択的継承）
- [ADR 0033: バックエンドを Python に pivot](./0033-backend-language-pivot-to-python.md)（Backend Python 化により TS 側構成が縮小した契機）
- [ADR 0035: Python のパッケージ管理に uv を採用](./0035-uv-for-python-package-management.md)（Python 側のモノレポ管理）
- [ADR 0013: Frontend ホスティングに Vercel を採用](./0013-vercel-for-frontend-hosting.md)（リモートキャッシュ非採用の文脈）
- [ADR 0006: JSON Schema を SSoT に](./0006-json-schema-as-single-source-of-truth.md)（packages/shared-types の役割）
- [pnpm workspaces 公式](https://pnpm.io/workspaces)
- [Self-hosting Next.js without full monorepo dependencies](https://github.com/vercel/next.js/discussions/85099)
