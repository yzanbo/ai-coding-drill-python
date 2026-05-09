# 01. ロードマップとプロダクトバックログ

> **このドキュメントの守備範囲**：プロダクト全体の方向性（ビジョン）、リリース単位のロードマップ、優先度付きプロダクトバックログ、スプリント運用、リスク。
> **個別機能の受け入れ条件・実装単位は [features/](../4-features/) が SSoT**、**設計判断の履歴は [docs/adr/](../../adr/) が SSoT**。
> アジャイル形式で運用するため、**「Phase X を着手前に固定」ではなく、ビジョンに沿って優先度を継続的に見直す**。

---

## ビジョン（変わらない北極星）

LLM が自動生成したプログラミング問題を、サンドボックスで動作保証してから提供する **TypeScript 練習サービス**を、ポートフォリオとして公開可能な水準で完成させる。

### 成功の定義（リリースレベル）

| 指標 | 目標 |
|---|---|
| 採用担当者がリンク 1 つでサービスを触れる状態 | 必達 |
| README から設計判断（ADR）を辿って論理的に説明できる | 必達 |
| LLM 出力の品質保証パイプラインが多層防御として動作する | 必達 |
| サンドボックスが段階的隔離強化（Docker → gVisor → Firecracker）の道筋を持つ | 達成度を見せる |
| 観測性ダッシュボードで生成成功率・コスト・レイテンシが見える | 必達 |

---

## ロードマップ（リリース単位）

時系列の大枠。**詳細タスクはバックログで管理**するためここには列挙しない。各リリースの粒度は「面接で見せられる状態」になることを基準にする。

| リリース | 主要アウトカム | 主な対象機能・トピック |
|---|---|---|
| **R0：基盤立ち上げ** | `docker compose up` で開発環境が立ち上がる、CI が動く | モノレポ・DB・Redis・GitHub Actions・補完ツール一式（→ [ADR 0021](../../adr/0021-r0-tooling-discipline.md)） |
| **R1：MVP（最小貫通）** | ユーザーが問題を生成 → 解答 → 採点 → 結果表示まで一気通貫で動く | [F-01](../4-features/F-01-github-oauth-auth.md) 〜 [F-05](../4-features/F-05-learning-history.md)（同期/単純構成で OK） |
| **R2：品質保証パイプライン** ★ ポートフォリオ評価の核 | 「LLM 出力を信用しない」設計思想が動作で示せる | LLM-as-a-Judge / ミューテーションテスト / プロンプトキャッシュ / 構造化出力厳密化 / 非同期ジョブ化（リトライ・DLQ・スタックジョブ回収） |
| **R3：サンドボックス強化** ★ ポートフォリオ評価の核 | Docker → gVisor 切替が設定で可能、ベンチマーク結果が README にある | gVisor 対応 / 隔離強化ベンチマーク / セキュリティドキュメント化（→ [ADR 0009](../../adr/0009-disposable-sandbox-container.md)） |
| **R4：観測性** ★ ポートフォリオ評価の核 | 面接官にダッシュボードを見せられる、ログ・トレース・メトリクスが連結 | OpenTelemetry 組み込み / プロセス境界トレース連携（→ [ADR 0010](../../adr/0010-w3c-trace-context-in-job-payload.md)）/ Grafana ダッシュボード / Sentry 接続 / アラート整備 / [F-08](#f-08-管理ダッシュボード) 着手 |
| **R5：仕上げ・公開** | 面接官が URL からサービスを触れる、README に設計判断・ベンチマーク・デモ動画が揃う | IaC（Terraform）/ 本番デプロイ / E2E テスト / README 完成 / ポートフォリオサイトからリンク |

任意（優先度低、Later 扱い）：R6 適応型学習 / R7 Python 分析パイプライン / R8 多言語化 / R9 Firecracker microVM。

期間目安：R0〜R5 で **専業 6〜8 週 / 兼業 2〜3 ヶ月**（ベロシティ × 残バックログで都度予測。コミットメントではない）。

---

## プロダクトバックログ（優先度順）

優先度の高い順に並べる。**いつ着手するかは固定せず、各スプリント開始時に上から取る**。

凡例：🔴 Now（直近 1〜2 スプリント）/ 🟡 Next（次候補）/ 🟢 Later（着手未定）/ ⏸️ Parked（先送り）

### Now：R0 基盤（9 項目、上から順に直列）

R0 は補完ツールの導入順序にロジックがあるため**直列**で進める。**根拠は [ADR 0021](../../adr/0021-r0-tooling-discipline.md) 参照**。技術選定の SSoT は [06-dev-workflow.md](../2-foundation/06-dev-workflow.md)。

| ID | 項目 | 状態 | 理由 / 関連 |
|---|---|---|---|
| R0-1 | commitlint 導入 + scope/type 規約整備 | ✅ | 履歴ゲート。コミット履歴は遡及修正不可。設定の試行錯誤を hook 起動から切り離す |
| R0-2 | lefthook + commit-msg フック | ✅ | commitlint を機械強制 |
| R0-3 | モノレポ枠（pnpm workspaces + Turborepo + `packages/config`）| ✅ | 多消費者前提の shared config 置き場 → [packages/config/README.md](../../../packages/config/README.md) / [ADR 0023](../../adr/0023-turborepo-pnpm-monorepo.md) |
| R0-4 | Biome + lefthook の pre-commit 接続 | ✅ | コード蓄積前にフォーマット規律 → [ADR 0018](../../adr/0018-biome-for-tooling.md) |
| R0-5 | GitHub Actions（min：commitlint + Biome + typecheck）| ✅ | リモートで規約逸脱を弾く → [ADR 0026](../../adr/0026-github-actions-incremental-scope.md) / [ADR 0025](../../adr/0025-github-actions-as-ci-cd.md) |
| R0-6 | Dependabot + GitHub Actions の SHA ピン止め | ✅ | 設定 1 ファイルで自動 PR、SHA ピン止めとセット運用 |
| R0-7 | syncpack | ✅ | パッケージ複数化前に整合性ゲート → [ADR 0024](../../adr/0024-syncpack-package-json-consistency.md) |
| R0-8 | Knip | 🔴 次タスク | 設定先行投入、export 蓄積で本領発揮 |
| R0-9 | Docker Compose（Postgres + Redis）+ Drizzle 初版 + マイグレーション基盤 | 🔴 | R0 完了の最終条件 → [ADR 0004](../../adr/0004-postgres-as-job-queue.md) / [ADR 0017](../../adr/0017-drizzle-orm-over-prisma.md) |

R0 で着手しないツール（後続フェーズ待ち）：

- `gofmt` + `golangci-lint` — R1（grading-worker 着手時）
- `ruff` — R7
- JSON Schema → 型生成パイプライン — R1（最初のスキーマ投入時。ディレクトリ枠とビルドスクリプトの「形」だけ R0 で用意可）
- Jest / Playwright — テスト対象コード待ち
- `stryker-js`（ミューテーションテスト）— R2 以降
- Docker build → ECR push / Terraform — R5

### Now：R1 MVP（8 項目、上から順に依存関係に従う）

| ID | 項目 | 状態 | 関連 |
|---|---|---|---|
| R1-1 | ジョブペイロード JSON Schema 確定 + TS/Go 型自動生成（shared-types パターン確立）+ dev モード watch 連鎖の構築（[補足](#r1-1-補足-dev-モード-watch-連鎖)）| 🔴 | [ADR 0006](../../adr/0006-json-schema-as-single-source-of-truth.md) |
| R1-2 | [F-01: GitHub OAuth ログイン](../4-features/F-01-github-oauth-auth.md) | 🔴 | [ADR 0011](../../adr/0011-github-oauth-with-extensible-design.md) |
| R1-3 | LLM プロバイダ抽象化レイヤ + 初期モデル選定（実装着手時に確定 + ADR 起票）| 🔴 | [ADR 0007](../../adr/0007-llm-provider-abstraction.md) |
| R1-4 | [F-02: 問題生成リクエスト](../4-features/F-02-problem-generation.md)（同期版で先に成立）| 🔴 | [03-llm-pipeline.md](../2-foundation/03-llm-pipeline.md) |
| R1-5 | [F-03: 問題表示・解答入力](../4-features/F-03-problem-display-and-answer.md) | 🔴 | [ADR 0015](../../adr/0015-codemirror-over-monaco.md) |
| R1-6 | 採点ワーカー（Go）初版 + サンドボックス（Docker + 制限フラグ）+ Go リンター導入（[補足](#r1-6-補足-go-リンター導入)）| 🔴 | [ADR 0016](../../adr/0016-go-for-grading-worker.md) / [ADR 0009](../../adr/0009-disposable-sandbox-container.md) / [ADR 0019](../../adr/0019-go-code-quality.md) |
| R1-7 | [F-04: 自動採点](../4-features/F-04-auto-grading.md)（trace_id 連結を R1 から実装）| 🔴 | [ADR 0010](../../adr/0010-w3c-trace-context-in-job-payload.md) |
| R1-8 | [F-05: 学習履歴・統計](../4-features/F-05-learning-history.md) | 🔴 | — |

<a id="r1-1-補足-dev-モード-watch-連鎖"></a>
#### R1-1 補足：dev モード watch 連鎖

R1-1 の成果（shared-types 自動生成）を R1-4 / R1-5 / R1-6 で快適に利用するため、`pnpm dev`（ルート）起動時に `packages/shared-types` の編集が各アプリにリアルタイム反映される構成を **R1-1 の DoD に含める**。

- `packages/shared-types` の `dev` script を watch モード（`tsc --watch --preserveWatchOutput`）にして `dist/` を継続更新
- 各アプリの `dependencies` で shared-types を **`workspace:*`** プロトコルで参照（pnpm の symlink で `node_modules/` 経由でも即時反映）
- `apps/api` の `scripts.dev` は `nest start --watch`（dist 変更を検知して NestJS プロセスを再起動）
- `apps/web` の `next.config.js` に **`transpilePackages: ["@ai-coding-drill/shared-types"]`** を設定（未設定だと `node_modules` 配下が HMR 対象から外れる）
- `apps/grading-worker` は Go のため対象外（型は生成物 `generated/go/` を import するのみ）
- Turbo の `tasks.dev` に `dependsOn: ["^build"]` を入れ、初回起動時に依存先を 1 回ビルドしてから dev を立ち上げる（型解決エラー回避）

反映フロー：`shared-types/src/*.ts` 編集 → `tsc --watch` が `dist/` 更新 → symlink 経由でアプリ側 `node_modules` も更新 → アプリ側 watch が再起動 / HMR で反映（通常 2〜5 秒）。

R1 完了時点でこの構成を `.claude/rules/backend.md` `.claude/rules/frontend.md` に「実装契約」として転記する。

<a id="r1-6-補足-go-リンター導入"></a>
#### R1-6 補足：Go リンター導入

採点ワーカーで Go コードがリポジトリに初めて入る時点で、TS と同等の品質ゲートを揃える。**R1-6 の DoD に含める**（→ [ADR 0019](../../adr/0019-go-code-quality.md)）。

- `apps/grading-worker/` 配下に **`go.mod` + `.golangci.yml`** を新設
- 有効化リンタ：`govet` / `staticcheck` / `errcheck` / `ineffassign` / `unused` / `gofumpt` / `gosec`
- ルート `lefthook.yml` の `pre-commit` に Go 用コマンドを追加：
    - ステージ済み `*.go` ファイルに対し `gofmt -w` + `golangci-lint run` を実行
    - `stage_fixed: true` で gofmt 整形差分を自動再ステージ
- CI（R0-5 で整備した GitHub Actions）にも `golangci-lint run` ステップを追加
- 任意：`govulncheck` の定期実行を別ワークフローで検討

R1 完了時点でこの Go 品質ゲートを `.claude/rules/worker.md` に「実装契約」として転記する。

### Next（次スプリント候補、すべて R2）

| 優先度 | 項目 | 関連 |
|---|---|---|
| 🟡 | 非同期ジョブ化の完全実装（リトライ・DLQ・スタックジョブ回収） | [02-architecture.md](../2-foundation/02-architecture.md#ジョブキューpostgres-select-for-update-skip-locked) |
| 🟡 | LLM-as-a-Judge 実装（自前、多軸スコアリング、複数回実行平均）| [ADR 0008](../../adr/0008-custom-llm-judge.md) |
| 🟡 | ミューテーションテスト導入 | [05-runtime-stack: 品質評価まわりのツール](../2-foundation/05-runtime-stack.md#品質評価まわりのツール) |
| 🟡 | モデル段階利用 + プロンプトキャッシュ + Redis レスポンスキャッシュ | [03-llm-pipeline: コスト最適化](../2-foundation/03-llm-pipeline.md#コスト最適化) |
| 🟡 | 構造化出力の厳密化（Zod スキーマでの最終バリデーション）| [03-llm-pipeline.md](../2-foundation/03-llm-pipeline.md) |

### Later（着手未定）

| 優先度 | 項目 | リリース | 関連 |
|---|---|---|---|
| 🟢 | gVisor 対応 + Docker vs gVisor ベンチマーク | R3 | [ADR 0009](../../adr/0009-disposable-sandbox-container.md) |
| 🟢 | OpenTelemetry SDK 組み込み（NestJS / Go 両側）| R4 | [04-observability.md](../2-foundation/04-observability.md) |
| 🟢 | プロセス境界トレース連携の実装（W3C Trace Context payload）| R4 | [ADR 0010](../../adr/0010-w3c-trace-context-in-job-payload.md) |
| 🟢 | Grafana ダッシュボード（生成成功率・コスト・レイテンシ・ジョブキュー）| R4 | [04-observability.md: メトリクス](../2-foundation/04-observability.md#メトリクス) |
| 🟢 | Sentry 接続 + PII マスキング実装 | R4 | [04-observability.md: エラー追跡](../2-foundation/04-observability.md#エラー追跡) |
| 🟢 | アラート整備（コスト・成功率・キュー深さ・DLQ・ヘルスチェック）| R4 | [04-observability.md: アラート](../2-foundation/04-observability.md#アラート) |
| 🟢 | <a id="f-08-管理ダッシュボード"></a>F-08: 管理ダッシュボード | R4 | 着手時に [_template.md](../4-features/_template.md) で詳細化 |
| 🟢 | pnpm 依存整合性の正規化（`strict-peer-dependencies=true` 復帰 + `pnpm.overrides` 整理） | R5 | [.npmrc](../../../.npmrc) |
| 🟢 | IaC（Terraform）整備 + 本番デプロイパイプライン | R5 | — |
| 🟢 | E2E テスト主要フロー整備（Playwright）| R5 | — |
| 🟢 | README 完成（設計判断・ベンチマーク・デモ動画）| R5 | — |
| 🟢 | <a id="f-06-適応型出題"></a>F-06: 適応型出題 | R6 | 着手時に [_template.md](../4-features/_template.md) で詳細化 |
| 🟢 | <a id="f-07-llm-ヒント機能"></a>F-07: LLM ヒント機能 | R6 | プロンプトインジェクション対策の検討必須 |
| 🟢 | Python 分析パイプライン（再評価バッチ / 重複検出 / Judge 信頼性 / 学習履歴分析）| R7 | [ADR 0003](../../adr/0003-phased-language-introduction.md) |
| 🟢 | RAG による教材準拠問題生成（Ragas / LlamaIndex 等）| R7 | — |
| 🟢 | 採点対象言語の多言語化（Python / React コンポーネント等）| R8 | [ADR 0003](../../adr/0003-phased-language-introduction.md) |
| 🟢 | Firecracker microVM 対応 | R9 | [ADR 0009](../../adr/0009-disposable-sandbox-container.md) |

### Parked（明示的に先送り）

| 項目 | 先送り理由 / 再評価条件 |
|---|---|
| ⏸️ メール+パスワード認証 | OAuth で十分 / F-01 に明確な不満が出た時 |
| ⏸️ コード共有・SNS 機能 | 個人学習サービスの範囲外 / 方向性再定義時 |
| ⏸️ 多人数同時利用前提のリアルタイム機能 | 規模に対してオーバー / スループット要件明確化時 |
| ⏸️ 独自プロンプトでの問題生成 | プロンプトインジェクションのリスク / 入力検証強化の見通しが立った時 |

---

## スプリント運用

- **1 週間スプリント**を基本単位（兼業時は 2 週間まで延長可）
- スプリント開始時に Now バックログ上位を取り、終了時に DoD を確認
- セレモニーは個人開発のため軽量：プランニング（開始時、DoR 確認）/ デイリー振り返り（任意）/ レビュー（終了時、デモ動画化）/ レトロ（終了時、必要なら ADR 化）

### Definition of Ready（DoR）：スプリント引き入れ前

- features/ に該当 .md がある（または独立した技術タスクとして明確）
- ユーザーストーリー / 技術タスクの目的が書かれている
- 受け入れ条件（テスト可能粒度）と スコープ外 が明記されている
- 影響範囲（変更ファイル・横断テーマ）が把握されている
- 必要な ADR があれば起票済み

### Definition of Done（DoD）：スプリント終了時

- 受け入れ条件すべてを満たす
- 必要範囲（BE / FE / Worker）の実装完了
- ユニットテスト / 必要に応じて E2E テスト追加
- 型チェック・lint・既存テストが green
- レビュー済みで PR がマージ済み
- features/ の「ステータス」セクション更新
- 重要な設計判断は ADR 起票・更新

### 見積もり

ストーリーポイントを採用（厳密化より「相対サイズの感覚」が目的）：

- **1**：数時間 / **2**：半日〜1 日 / **3**：1〜2 日（典型）/ **5**：数日（横断影響あり）/ **8**：1 週間以上（要分割検討、スプリント内で 1 つが上限）/ **13+**：必ず分割

期間予測：`残ポイント ÷ 平均ベロシティ ≒ 残スプリント数`。**コミットメントとは扱わない**。

---

## リスクレジスタ

| リスク | 影響 | 監視 / 対応 |
|---|---|---|
| LLM API コストが想定超 | R1 以降の機能継続可否に直結 | 日次コストアラート + キャッシュ強化 → [04-observability.md](../2-foundation/04-observability.md#アラート) |
| Drizzle v1.0 stable 時期未定 | ORM バージョン選定が不安定 → [ADR 0017](../../adr/0017-drizzle-orm-over-prisma.md) | [drizzle.md](../../../.claude/rules/drizzle.md) のチェックリストで実装着手時に確定 |
| サンドボックス起動時間が想定（200ms）超 | スループット・コスト影響 | R1 終了時にベンチマーク、必要なら R3 を前倒し |
| プロセス境界トレース連携を後回し | R4 で詰む | R1 の最初のジョブ INSERT で一緒に実装 → [ADR 0010](../../adr/0010-w3c-trace-context-in-job-payload.md) |
| ポートフォリオの差別化軸がぼやける | R5 公開後の評価低下 | R2〜R4 を最優先、R5 で README に設計判断を凝縮 |
| 立ち上げ期の peer 緩和設定を本番化前に戻し忘れる | 依存バージョン不整合が実行時エラーや謎の挙動として顕在化、デバッグ困難化 | R5 のバックログ「pnpm 依存整合性の正規化」で `strict-peer-dependencies=true` 復帰を必須化 → [.npmrc](../../../.npmrc) |
| syncpack `sameRange` × Dependabot `groups` の整合性が R1 以降の実弾で破綻 | Dependabot 自動 PR が片方 workspace のみ更新で `sameRange` 違反になると、毎回 CI が落ち手動修正が必要になり自動更新の自動化メリットが消える | R1 で `apps/*` が追加された後、**初の Dependabot PR で CI 通過を目視確認**。落ちたら [ADR 0028](../../adr/0028-dependabot-auto-update-policy.md) の `groups` 設定を見直す → [ADR 0024](../../adr/0024-syncpack-package-json-consistency.md) Consequences |

---

## このドキュメントの更新タイミング

- **スプリント終了ごと**：完了項目を Now → 完了印（✅）に、Next を見直し
- **リリース完了時**：ロードマップ表の該当行を更新
- **新しい設計判断時**：関連バックログ項目に ADR リンク追加

本プロジェクトのリリース表記は **RX**（R0〜R9）に統一する。git 履歴・古い PR 等で旧「Phase X」表記を見かけた場合は **Phase N = RN** で読み替える（→ [ADR 0001](../../adr/0001-requirements-as-5-buckets.md)）。
