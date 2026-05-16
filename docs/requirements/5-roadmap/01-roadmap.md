# 01. ロードマップとプロダクトバックログ

> **このドキュメントの守備範囲**：プロダクト全体の方向性（ビジョン）、リリース単位のロードマップ、優先度付きプロダクトバックログ、スプリント運用、リスク。
> **個別機能の受け入れ条件・実装単位は [features/](../4-features/) が SSoT**、**設計判断の履歴は [docs/adr/](../../adr/) が SSoT**。
> アジャイル形式で運用するため、**「Phase X を着手前に固定」ではなく、ビジョンに沿って優先度を継続的に見直す**。

---

## ビジョン（変わらない北極星）

LLM が自動生成したプログラミング問題を、サンドボックスで動作保証してから提供する **TypeScript 練習サービス**を、ポートフォリオとして公開可能な水準で完成させる。バックエンドは **Python (FastAPI)**、Frontend は **Next.js (TypeScript)**、採点 / LLM 呼び出しは **Go Worker** で構成する（→ [ADR 0033](../../adr/0033-backend-language-pivot-to-python.md) / [ADR 0040](../../adr/0040-worker-grouping-and-llm-in-worker.md)）。

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
| **R0：基盤立ち上げ** | `docker compose up` で開発環境が立ち上がる、CI が動く | mise（タスク + tool 版数 SSoT）/ uv（Python）/ pnpm（apps/web 内）/ go mod / DB・Redis・GitHub Actions・補完ツール一式（→ [ADR 0021](../../adr/0021-r0-tooling-discipline.md) / [ADR 0035](../../adr/0035-uv-for-python-package-management.md) / [ADR 0036](../../adr/0036-frontend-monorepo-pnpm-only.md) / [ADR 0039](../../adr/0039-mise-for-task-runner-and-tool-versions.md)） |
| **R1：MVP（最小貫通）** | ユーザーが問題を生成 → 解答 → 採点 → 結果表示まで一気通貫で動く | [F-01](../4-features/F-01-github-oauth-auth.md) 〜 [F-05](../4-features/F-05-learning-history.md)（API は enqueue のみ、LLM 呼び出しは Worker に集約 → [ADR 0040](../../adr/0040-worker-grouping-and-llm-in-worker.md)） |
| **R2：品質保証パイプライン** ★ ポートフォリオ評価の核 | 「LLM 出力を信用しない」設計思想が動作で示せる | LLM-as-a-Judge（grading worker 内）/ ミューテーションテスト / プロンプトキャッシュ / 構造化出力厳密化 / 非同期ジョブ化（リトライ・DLQ・スタックジョブ回収） |
| **R3：サンドボックス強化** ★ ポートフォリオ評価の核 | Docker → gVisor 切替が設定で可能、ベンチマーク結果が README にある | gVisor 対応 / 隔離強化ベンチマーク / セキュリティドキュメント化（→ [ADR 0009](../../adr/0009-disposable-sandbox-container.md)） |
| **R4：観測性** ★ ポートフォリオ評価の核 | 面接官にダッシュボードを見せられる、ログ・トレース・メトリクスが連結 | OpenTelemetry 組み込み（FastAPI / Go 両側）/ プロセス境界トレース連携（→ [ADR 0010](../../adr/0010-w3c-trace-context-in-job-payload.md)）/ Grafana ダッシュボード / Sentry 接続 / アラート整備 / [F-08](#f-08-管理ダッシュボード) 着手 |
| **R5：仕上げ・公開** | 面接官が URL からサービスを触れる、README に設計判断・ベンチマーク・デモ動画が揃う | IaC（Terraform）/ 本番デプロイ / E2E テスト（Playwright）/ README 完成 / ポートフォリオサイトからリンク |

任意（優先度低、Later 扱い）：R6 適応型出題 / R7 問題生成 Worker（apps/workers/generation）/ R8 多言語化 / R9 Firecracker microVM。

期間目安：R0〜R5 で **専業 6〜8 週 / 兼業 2〜3 ヶ月**（ベロシティ × 残バックログで都度予測。コミットメントではない）。

---

## プロダクトバックログ（優先度順）

優先度の高い順に並べる。**いつ着手するかは固定せず、各スプリント開始時に上から取る**。

凡例：🔴 Now（直近 1〜2 スプリント）/ 🟡 Next（次候補）/ 🟢 Later（着手未定）/ ⏸️ Parked（先送り）

### Now：R0 基盤（直列、初期慣行 + 言語別環境構築）

R0 は補完ツールの導入順序にロジックがあるため**直列**で進める。**根拠は [ADR 0021](../../adr/0021-r0-tooling-discipline.md) 参照**。技術選定の SSoT は [06-dev-workflow.md](../2-foundation/06-dev-workflow.md)。Python pivot 後の構成（→ [ADR 0033](../../adr/0033-backend-language-pivot-to-python.md)）に合わせて R0 のツーリング項目を再編する。

**各項目の詳細手順は [setup/](./r0-setup/) 配下のファイルが SSoT**（roadmap は項目の存在のみ追跡し、内部の手順番号や数は setup ファイル内で完結する）。

| ID | 項目 | 状態 | 詳細手順 |
|---|---|---|---|
| R0-1 | 初期慣行の構築（commitlint / lefthook / mise / GitHub Actions / Dependabot 雛形） | ✅ 完了 | [r0-setup/01-foundation.md](./r0-setup/01-foundation.md) |
| R0-2 | Python 環境構築（apps/api + DB + 品質ゲート + CI + dependabot 統合） | ✅ 完了 | [r0-setup/02-python.md](./r0-setup/02-python.md) |
| R0-3 | Next.js 環境構築（apps/web + 品質ゲート + CI + dependabot 統合） | ✅ 完了 | [r0-setup/03-nextjs.md](./r0-setup/03-nextjs.md) |
| R0-4 | Go 環境構築（apps/workers/grading + 品質ゲート + CI + dependabot 統合 + サンドボックス雛形）<br>**着手タイミングは柔軟**：R0-1〜R0-3 完了後にすぐ着手する必要はなく、**R1 開始までに完了**させればよい（R1-3 LLM プロバイダ抽象化が Worker コードを必要とするため、その前までに揃っていればよい） | 🔴 未着手 | [r0-setup/04-go.md](./r0-setup/04-go.md) |

**マイルストーン**：「Python が完成 = R0-2 完了」「Next.js が完成 = R0-3 完了」「Go が完成 = R0-4 完了」「R0 全完了 = `docker compose up && mise run api:dev && mise run web:dev && mise run worker:grading:dev` で開発環境が全言語で立ち上がる」。

**R0 で着手しないツール**（テスト系は対象コード待ち、ミューテーションテストは R2 以降、IaC は R5 等）は [r0-setup/README.md: 後続フェーズ待ち項目](./r0-setup/README.md#r0-で着手しないツール後続フェーズ待ち) を参照。

### Now：R1 MVP（9 項目、上から順に依存関係に従う）

> **前提**：R0 全完了（Go 環境構築 R0-4 を含む）。R1-5 LLM プロバイダ抽象化が Worker コードを必要とするため、R0-4 が遅延した場合は R1-5 着手前に必ず完了させる。
>
> **R1-1 / R1-2 と r0-setup の分担**：r0-setup（[02-python.md](./r0-setup/02-python.md) / [03-nextjs.md](./r0-setup/03-nextjs.md)）では「悩む余地のない基本構造」（`app/main.py` / `app/db/session.py` / `app/models/` / Next.js scaffold 等）までを扱う。R1-1 / R1-2 はその上に **プロジェクト固有のレイヤ分割**（FastAPI の `routers` / `services` / `schemas` / `core` 分離 + import 方向、Frontend の feature folder vs `src/{components,hooks,lib}` 配置規約）を確定し、`.claude/rules/{backend,frontend}.md` に「実装契約」として固定する。R1-3 以降の機能実装はこの規約に従う。

| ID | 項目 | 状態 | 関連 |
|---|---|---|---|
| R1-1 | Backend ディレクトリ構成決定（`apps/api/app/{routers,services,schemas,models,core,db}/` を `__init__.py` 付きで配置、各 layer の責務 + import 方向 + 命名規則を `.claude/rules/backend.md` に確定）| 🔴 | [.claude/rules/backend.md](../../../.claude/rules/backend.md) |
| R1-2 | Frontend ディレクトリ構成決定（`apps/web/src/{components,hooks,lib,__generated__/api}/` 配置、feature folder 配置規約 + import 方向 + 命名規則を `.claude/rules/frontend.md` に確定）| 🔴 | [.claude/rules/frontend.md](../../../.claude/rules/frontend.md) |
| R1-3 | ジョブペイロード Pydantic モデル確定 + Pydantic から JSON Schema 出力（Go 型生成パス）+ FastAPI OpenAPI 3.1（Frontend 向け TS 型生成）の構築（[補足](#r1-3-補足-型同期パイプライン)）| 🔴 | [ADR 0006](../../adr/0006-json-schema-as-single-source-of-truth.md) |
| R1-4 | [F-01: GitHub OAuth ログイン](../4-features/F-01-github-oauth-auth.md) | 🔴 | [ADR 0011](../../adr/0011-github-oauth-with-extensible-design.md) |
| R1-5 | LLM プロバイダ抽象化レイヤ + 初期モデル選定（**Worker 側に集約**、実装着手時に確定 + ADR 起票）| 🔴 | [ADR 0007](../../adr/0007-llm-provider-abstraction.md) / [ADR 0040](../../adr/0040-worker-grouping-and-llm-in-worker.md) |
| R1-6 | [F-02: 問題生成リクエスト](../4-features/F-02-problem-generation.md)（API は enqueue のみ、生成は grading worker でも問題生成 worker でも実行可能な形に）| 🔴 | [03-llm-pipeline.md](../2-foundation/03-llm-pipeline.md) / [ADR 0040](../../adr/0040-worker-grouping-and-llm-in-worker.md) |
| R1-7 | [F-03: 問題表示・解答入力](../4-features/F-03-problem-display-and-answer.md) | 🔴 | [ADR 0015](../../adr/0015-codemirror-over-monaco.md) |
| R1-8 | [F-04: 自動採点](../4-features/F-04-auto-grading.md)（trace_id 連結を R1 から実装）| 🔴 | [ADR 0010](../../adr/0010-w3c-trace-context-in-job-payload.md) |
| R1-9 | [F-05: 学習履歴・統計](../4-features/F-05-learning-history.md) | 🔴 | — |

<a id="r1-3-補足-型同期パイプライン"></a>
#### R1-3 補足：型同期パイプライン（Pydantic SSoT）

[ADR 0006](../../adr/0006-json-schema-as-single-source-of-truth.md) の Pydantic-first SSoT 設計に従い、R1-3 では以下のパスを **R1-3 の DoD に含める**。

- **Pydantic モデルを apps/api 内で SSoT として定義**（リクエスト / レスポンス / ジョブペイロード）
- **HTTP API 境界（Frontend 向け、TS 型）**：FastAPI が自動生成する `apps/api/openapi.json`（OpenAPI 3.1）を起点に、Hey API（`@hey-api/openapi-ts` + Zod プラグイン）で TS 型 + Zod + 型付き HTTP クライアントを生成。`mise run web:types-gen` として mise.toml に登録（→ [ADR 0039](../../adr/0039-mise-for-task-runner-and-tool-versions.md)）
- **Job キュー境界（Worker 向け、Go struct）**：Pydantic モデルから `model.model_json_schema()` で個別 JSON Schema を `apps/api/job-schemas/<job-name>.schema.json` に出力（`mise run api:job-schemas-export`）し、quicktype `--src-lang schema` で各 Worker（`apps/workers/<name>/internal/jobtypes/`）に Go struct を生成。`mise run worker:types-gen` として登録（横断、対象 Worker 全てに配布）
- **dev モードでの即時反映**：FastAPI は `uvicorn --reload` で Pydantic モデル変更を即時反映、Frontend は OpenAPI 再取得 + 型再生成（手動 / watch）、Go Worker は再生成された型ファイルを取り込んで再ビルド
- 中継パッケージ（旧 `packages/shared-types` 構想）は廃止（→ [ADR 0006](../../adr/0006-json-schema-as-single-source-of-truth.md) / [ADR 0036](../../adr/0036-frontend-monorepo-pnpm-only.md)）。各 app は artifact（`apps/api/openapi.json` / `apps/api/job-schemas/`）を直接読み、生成物を自身のディレクトリ内に配置する

R1 完了時点でこの型同期パイプラインを `.claude/rules/backend.md` `.claude/rules/frontend.md` `.claude/rules/worker.md` に「実装契約」として転記する。

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
| 🟢 | OpenTelemetry SDK 組み込み（FastAPI / Go 両側）| R4 | [04-observability.md](../2-foundation/04-observability.md) |
| 🟢 | プロセス境界トレース連携の実装（W3C Trace Context payload）| R4 | [ADR 0010](../../adr/0010-w3c-trace-context-in-job-payload.md) |
| 🟢 | Grafana ダッシュボード（生成成功率・コスト・レイテンシ・ジョブキュー）| R4 | [04-observability.md: メトリクス](../2-foundation/04-observability.md#メトリクス) |
| 🟢 | Sentry 接続 + PII マスキング実装 | R4 | [04-observability.md: エラー追跡](../2-foundation/04-observability.md#エラー追跡) |
| 🟢 | アラート整備（コスト・成功率・キュー深さ・DLQ・ヘルスチェック）| R4 | [04-observability.md: アラート](../2-foundation/04-observability.md#アラート) |
| 🟢 | <a id="f-08-管理ダッシュボード"></a>F-08: 管理ダッシュボード | R4 | 着手時に [_template.md](../4-features/_template.md) で詳細化 |
| 🟢 | apps/web 内の pnpm 依存整合性の正規化（`strict-peer-dependencies=true` 復帰 + `pnpm.overrides` 整理） | R5 | `apps/web/.npmrc`（実装着手時に配置）/ [ADR 0036](../../adr/0036-frontend-monorepo-pnpm-only.md) |
| 🟢 | IaC（Terraform）整備 + 本番デプロイパイプライン | R5 | — |
| 🟢 | E2E テスト主要フロー整備（Playwright）| R5 | [ADR 0038](../../adr/0038-test-frameworks.md) |
| 🟢 | README 完成（設計判断・ベンチマーク・デモ動画）| R5 | — |
| 🟢 | <a id="f-06-適応型出題"></a>F-06: 適応型出題 | R6 | 着手時に [_template.md](../4-features/_template.md) で詳細化 |
| 🟢 | <a id="f-07-llm-ヒント機能"></a>F-07: LLM ヒント機能 | R6 | プロンプトインジェクション対策の検討必須 |
| 🟢 | apps/workers/generation（問題生成 Worker）切り出し + プロンプト群移管（apps/workers/generation/prompts/） | R7 | [ADR 0040](../../adr/0040-worker-grouping-and-llm-in-worker.md) |
| 🟢 | RAG による教材準拠問題生成（apps/workers/rag、Ragas / LlamaIndex 等）+ 評価バッチ用 Python オフライン基盤（apps/workers/eval-pipeline）| R7 | [05-runtime-stack.md](../2-foundation/05-runtime-stack.md) |
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
| SQLAlchemy 2.0 async + Alembic の運用未経験箇所での詰まり | DB 層の進捗が止まると R1 全体が遅延 | R0-2（Python 環境構築）の DB 基盤ステップで薄い CRUD + マイグレーション 1 周を通し、つまずき箇所を早期に洗い出す（→ [r0-setup/02-python.md](./r0-setup/02-python.md) / [ADR 0037](../../adr/0037-sqlalchemy-alembic-for-database.md)）|
| サンドボックス起動時間が想定（200ms）超 | スループット・コスト影響 | R1 終了時にベンチマーク、必要なら R3 を前倒し |
| プロセス境界トレース連携を後回し | R4 で詰む | R1 の最初のジョブ INSERT で一緒に実装 → [ADR 0010](../../adr/0010-w3c-trace-context-in-job-payload.md) |
| ポートフォリオの差別化軸がぼやける | R5 公開後の評価低下 | R2〜R4 を最優先、R5 で README に設計判断を凝縮 |
| 立ち上げ期の apps/web 内 pnpm peer 緩和設定を本番化前に戻し忘れる | 依存バージョン不整合が実行時エラーや謎の挙動として顕在化、デバッグ困難化 | R5 のバックログ「apps/web 内 pnpm 依存整合性の正規化」で `strict-peer-dependencies=true` 復帰を必須化 → `apps/web/.npmrc`（実装着手時に配置）/ [ADR 0036](../../adr/0036-frontend-monorepo-pnpm-only.md) |
| Pydantic SSoT → OpenAPI / JSON Schema → TS / Go 型生成の同期が崩れる | Frontend / Worker が古い型で動き、型安全性が形骸化 | R1-3 で `mise run api:openapi-export` / `api:job-schemas-export` / `web:types-gen` / `worker:types-gen` を CI 必須ステップに組み込み、生成物の差分が出たら CI を fail させる → [ADR 0006](../../adr/0006-json-schema-as-single-source-of-truth.md) / [ADR 0039](../../adr/0039-mise-for-task-runner-and-tool-versions.md) |

---

## このドキュメントの更新タイミング

- **スプリント終了ごと**：完了項目を Now → 完了印（✅）に、Next を見直し
- **リリース完了時**：ロードマップ表の該当行を更新
- **新しい設計判断時**：関連バックログ項目に ADR リンク追加

本プロジェクトのリリース表記は **RX**（R0〜R9）に統一する。git 履歴・古い PR 等で旧「Phase X」表記を見かけた場合は **Phase N = RN** で読み替える（→ [ADR 0001](../../adr/0001-requirements-as-5-buckets.md)）。
