# AI Coding Drill — 採用担当・面接官向けガイド

LLM が自動生成したプログラミング問題を、サンドボックス環境で検証・採点する学習サイト。「LLM の出力を信用せず、サンドボックスで動作保証する」設計思想を実装したポートフォリオプロジェクト。

> **Python 版**：TS 版（[`yzanbo/ai-coding-drill`](https://github.com/yzanbo/ai-coding-drill)）を [`v1.0.0-typescript`](https://github.com/yzanbo/ai-coding-drill/releases/tag/v1.0.0-typescript) タグで fork し、バックエンドを Python に pivot した派生版（→ [ADR 0033](docs/adr/0033-backend-language-pivot-to-python.md)）。Frontend (Next.js) と採点ワーカー (Go) は維持。

🚀 デモ：_R5 完了時に公開予定_
📊 ステータス：**R0 基盤構築完了・R1 MVP 完了**（R1-1〜R1-7 すべて完了、R2 着手前）
🛠️ ローカルで動かす場合：[README.md](README.md) を参照

---

## このプロジェクトの位置づけ

R0 基盤と R1 MVP（認証 / 問題生成 / 採点 / 解答 / 履歴・統計 / 生成履歴）が一気通貫で動く状態。**Python pivot 後の実装**として、設計判断 + 動くコードの両面で評価可能。

- アーキテクト枠：[ADR](docs/adr/) を中心に閲覧推奨。TS 版（`v1.0.0-typescript`）と本リポジトリの差分で**同じ設計を 2 言語で実装した経験**を確認可
- フルスタック（Python）枠：R1 まで進んだ実装コード（[apps/api/](apps/api/) / [apps/web/](apps/web/) / [apps/workers/grading/](apps/workers/grading/)）が読める状態

> 進捗の詳細（R0 / R1 完了状況 + R2 以降の予定）は [README.md: 現在の進捗](README.md#現在の進捗2026-05-時点) を参照。

---

## 推奨閲覧順

短時間で評価するための導線：

1. **本ファイルのハイライト**（[下記](#ハイライト)） — 差別化軸の概要
2. **[ADR](docs/adr/)** — 設計判断の中核
3. **[要件定義書 5 バケット構造](docs/requirements/)** — ドキュメント設計力
4. **[個別機能仕様](docs/requirements/4-features/)** — GitHub OAuth / 問題生成 / 採点 / 学習履歴
5. **動くデモ**（R5 公開後）

### 評価軸別の見どころ

| 観点 | 推奨閲覧 |
|---|---|
| 設計判断・トレードオフ | [docs/adr/](docs/adr/) |
| アーキテクチャ | [02-architecture.md](docs/requirements/2-foundation/02-architecture.md) + [ADR 0004](docs/adr/0004-postgres-as-job-queue.md) / [0009](docs/adr/0009-disposable-sandbox-container.md) / [0010](docs/adr/0010-w3c-trace-context-in-job-payload.md) |
| LLM アプリ設計 | [03-llm-pipeline.md](docs/requirements/2-foundation/03-llm-pipeline.md) + [ADR 0008](docs/adr/0008-custom-llm-judge.md) / [0007](docs/adr/0007-llm-provider-abstraction.md) |
| セキュリティ・サンドボックス | [ADR 0009](docs/adr/0009-disposable-sandbox-container.md) + [自動採点](docs/requirements/4-features/grading.md) |
| 観測性 | [04-observability.md](docs/requirements/2-foundation/04-observability.md) + [ADR 0010](docs/adr/0010-w3c-trace-context-in-job-payload.md) / [0041](docs/adr/0041-observability-stack-grafana-and-sentry.md) |
| ドキュメント設計 | [docs/requirements/README.md](docs/requirements/README.md) |
| アジャイル運用 | [5-roadmap/01-roadmap.md](docs/requirements/5-roadmap/01-roadmap.md) |

---

## ハイライト

1. **LLM 生成 × サンドボックス検証パイプライン** — 模範解答がサンドボックスで動作するまで DB に保存しない（[03-llm-pipeline.md](docs/requirements/2-foundation/03-llm-pipeline.md) / [ADR 0009](docs/adr/0009-disposable-sandbox-container.md)）
2. **品質評価の 4 レイヤ防御** — 決定論チェック / LLM-as-a-Judge / 行動シグナル / 集合評価（[ADR 0008](docs/adr/0008-custom-llm-judge.md)）
3. **Python + Go + TypeScript のポリグロット** — レイヤごとに適材適所（[ADR 0033](docs/adr/0033-backend-language-pivot-to-python.md) / [0003](docs/adr/0003-phased-language-introduction.md)）
4. **Postgres ジョブキュー** — `SKIP LOCKED` + `LISTEN/NOTIFY`、Outbox 不要（[ADR 0004](docs/adr/0004-postgres-as-job-queue.md) / [0005](docs/adr/0005-redis-not-for-job-queue.md)）
5. **使い捨てコンテナサンドボックス** — Docker → gVisor → Firecracker の段階強化（[ADR 0009](docs/adr/0009-disposable-sandbox-container.md)）
6. **LLM プロバイダ抽象化** — Anthropic / Google / OpenAI / OpenRouter 差し替え可（[ADR 0007](docs/adr/0007-llm-provider-abstraction.md)）
7. **W3C Trace Context** — FastAPI → Postgres → Go Worker を単一 trace_id で連結（[ADR 0010](docs/adr/0010-w3c-trace-context-in-job-payload.md)）
8. **Pydantic SSoT + 境界別 2 伝送路型生成** — OpenAPI → Hey API（TS）、JSON Schema → quicktype（Go）（[ADR 0006](docs/adr/0006-json-schema-as-single-source-of-truth.md)）
9. **AWS 単独 + IaC + 観測性スタック** — OTel + Grafana 系 + Sentry、月 $10〜30 想定（[ADR 0002](docs/adr/0002-aws-single-cloud.md) / [0041](docs/adr/0041-observability-stack-grafana-and-sentry.md)）

---

## 設計判断（ADR）索引

複数案を検討して 1 つを選んだ判断はすべて [docs/adr/](docs/adr/) に **1 ファイル 1 決定**で記録。判断が変わった場合は本文を直接書き換え、変更経緯は git log で辿る。

### 戦略

| ADR | タイトル |
|---|---|
| [0033](docs/adr/0033-backend-language-pivot-to-python.md) | バックエンドを Python に pivot |

### アーキテクチャ

| ADR | タイトル |
|---|---|
| [0004](docs/adr/0004-postgres-as-job-queue.md) | Postgres をジョブキューに採用 |
| [0005](docs/adr/0005-redis-not-for-job-queue.md) | Redis をジョブキューでは使わない |
| [0009](docs/adr/0009-disposable-sandbox-container.md) | 使い捨てサンドボックスコンテナ |
| [0008](docs/adr/0008-custom-llm-judge.md) | LLM-as-a-Judge を自前実装 |
| [0003](docs/adr/0003-phased-language-introduction.md) | レイヤ別ポリグロット構成 |
| [0007](docs/adr/0007-llm-provider-abstraction.md) | LLM プロバイダ抽象化戦略 |
| [0010](docs/adr/0010-w3c-trace-context-in-job-payload.md) | W3C Trace Context をジョブペイロードに埋め込む |

### 技術スタック

| ADR | タイトル |
|---|---|
| [0015](docs/adr/0015-codemirror-over-monaco.md) | CodeMirror 6 採用 |
| [0034](docs/adr/0034-fastapi-for-backend.md) | FastAPI 採用 |
| [0016](docs/adr/0016-go-for-grading-worker.md) | 採点ワーカーを Go で実装 |
| [0011](docs/adr/0011-github-oauth-with-extensible-design.md) | GitHub OAuth + 拡張可能設計 |
| [0037](docs/adr/0037-sqlalchemy-alembic-for-database.md) | SQLAlchemy 2.0 + Alembic |
| [0041](docs/adr/0041-observability-stack-grafana-and-sentry.md) | Grafana 系 + Sentry |

### インフラ

| ADR | タイトル |
|---|---|
| [0002](docs/adr/0002-aws-single-cloud.md) | AWS 単独 |
| [0012](docs/adr/0012-upstash-redis-over-elasticache.md) | Upstash Redis 採用 |
| [0013](docs/adr/0013-vercel-for-frontend-hosting.md) | Frontend は Vercel |

### 開発規律

| ADR | タイトル |
|---|---|
| [0039](docs/adr/0039-mise-for-task-runner-and-tool-versions.md) | mise でタスクランナー + 版数管理 |
| [0036](docs/adr/0036-frontend-monorepo-pnpm-only.md) | Frontend ツーリングを apps/web 内に閉じる |
| [0035](docs/adr/0035-uv-for-python-package-management.md) | Python パッケージ管理に uv |
| [0020](docs/adr/0020-python-code-quality.md) | Python コード品質（ruff + pyright + pip-audit + deptry） |
| [0006](docs/adr/0006-json-schema-as-single-source-of-truth.md) | Pydantic SSoT + 境界別 2 伝送路 |
| [0021](docs/adr/0021-r0-tooling-discipline.md) | 補完ツールを R0 から導入 |
| [0001](docs/adr/0001-requirements-as-5-buckets.md) | 要件定義書を 5 バケット時系列構造に |
| [0019](docs/adr/0019-go-code-quality.md) | Go コード品質（gofmt + golangci-lint） |
| [0040](docs/adr/0040-worker-grouping-and-llm-in-worker.md) | Worker を系統別に分割、LLM 呼び出しは Worker に集約 |
| [0038](docs/adr/0038-test-frameworks.md) | テストフレームワーク（pytest / Vitest + Playwright / Go testing + testify） |
| [0025](docs/adr/0025-github-actions-as-ci-cd.md) | CI/CD に GitHub Actions |
| [0028](docs/adr/0028-dependabot-auto-update-policy.md) | Dependabot 自動更新ポリシー |
| [0029](docs/adr/0029-commit-scope-convention.md) | コミット scope 規約 |
| [0027](docs/adr/0027-github-actions-sha-pinning.md) | サードパーティアクションを SHA でピン止め |
| [0022](docs/adr/0022-config-file-format-priority.md) | 設定ファイル形式の選定方針 |
| [0024](docs/adr/0024-syncpack-package-json-consistency.md) | syncpack による package.json 整合性ゲート |
| [0032](docs/adr/0032-github-repository-settings.md) | GitHub リポジトリ設定の方針 |

→ 全 ADR の索引：[docs/adr/README.md](docs/adr/README.md)

---

## 技術スタック概要

| レイヤ | 採用技術 |
|---|---|
| 言語ランタイム | Python 3.14 / Node.js 24 / Go 1.26（mise で固定） |
| フロントエンド | Next.js 16+（App Router）+ Tailwind v4 + shadcn/ui + React Hook Form + Zod + CodeMirror 6 + TanStack Query |
| バックエンド API | Python + FastAPI |
| ORM / マイグレーション | SQLAlchemy 2.0（async）+ Alembic |
| パッケージ管理 | uv（Python）/ pnpm（Frontend）/ go modules |
| Lint / Format | ruff（Python）/ Biome（TS）/ gofmt + golangci-lint（Go） |
| 型チェック | pyright / tsc |
| 採点ワーカー | Go + Docker クライアント + pgx |
| データストア | PostgreSQL 18（DB + ジョブキュー兼任）+ Upstash Redis |
| LLM | プロバイダ抽象化（Anthropic / Google / OpenAI / OpenRouter） |
| サンドボックス | Docker → R3 で gVisor → R9 で Firecracker |
| タスクランナー | mise（3 言語横断、Turborepo 不採用） |
| テスト | pytest / Vitest + Playwright / Go testing + testify |
| インフラ | AWS（ECS Fargate + EC2 + RDS + ECR + Route 53）+ Terraform |
| 観測性 | OpenTelemetry + Grafana + Loki + Tempo + Prometheus + Sentry |
| CI/CD | GitHub Actions |

> 具体版数の SSoT は [mise.toml](mise.toml)。詳細は [2-foundation/05-runtime-stack.md](docs/requirements/2-foundation/05-runtime-stack.md)。

---

## アーキテクチャ概要

```
[User Browser]
     ↓
[Next.js (Vercel)]
     ↓
[Python API (FastAPI, ECS Fargate)]
     ├── PostgreSQL (RDS)
     │     └── jobs テーブル（LISTEN/NOTIFY で Worker 群に通知、Backend は enqueue のみ）
     └── Upstash Redis（キャッシュ・セッション）

LLM 呼び出しは Worker 側に集約（ADR 0040）：
     ↓ jobs テーブル経由
[Go Worker 群 (apps/workers/<name>/)]
 ├─ apps/workers/grading/ (EC2)
 │   ├── Docker Engine + 使い捨て採点コンテナ
 │   └── judge LLM 呼び出し
 └─ apps/workers/generation/ (EC2、将来追加)
     └── 問題生成 LLM 呼び出し
```

詳細は [2-foundation/02-architecture.md](docs/requirements/2-foundation/02-architecture.md)。

---

## リリース計画

| リリース | アウトカム | 主な対象 | 状態 |
|---|---|---|---|
| R0：基盤立ち上げ | `docker compose up` で開発環境が立ち上がる、CI が動く | mise / uv / pnpm / go mod / DB・Redis・GitHub Actions・補完ツール一式 | ✅ 完了 |
| R1：MVP（最小貫通） | 問題生成 → 解答 → 採点 → 結果表示 → 履歴閲覧が一気通貫で動く | GitHub OAuth / 問題生成 / 採点 / 学習履歴 / 生成履歴 | ✅ 完了 |
| **R2：品質保証パイプライン** ★ | 「LLM 出力を信用しない」設計思想が動作で示せる | LLM-as-a-Judge / ミューテーションテスト / プロンプトキャッシュ / 構造化出力厳密化 / 非同期ジョブ化（リトライ・DLQ） | ⏳ 着手前（次フェーズ） |
| **R3：サンドボックス強化** ★ | Docker → gVisor 切替が設定で可能、ベンチマーク結果が README にある | gVisor 対応 / 隔離強化ベンチマーク / セキュリティドキュメント化 | ⏳ 未着手 |
| **R4：観測性** ★ | 面接官にダッシュボードを見せられる、ログ・トレース・メトリクスが連結 | OpenTelemetry（FastAPI / Go）/ W3C Trace Context / Grafana / Sentry / アラート / 管理ダッシュボード | ⏳ 未着手 |
| R5：仕上げ・公開 | 面接官が URL からサービスを触れる、README にデモ動画が揃う | IaC（Terraform）/ 本番デプロイ / E2E テスト / README 完成 | ⏳ 未着手 |
| R6 以降（任意） | 適応型出題 / generation Worker 機能実装 / 多言語化 / Firecracker microVM | R6 適応型出題 + LLM ヒント / R7 generation Worker + RAG / R8 多言語化 / R9 Firecracker | ⏸️ 後回し |

★ = ポートフォリオ評価の核。詳細は [5-roadmap/01-roadmap.md](docs/requirements/5-roadmap/01-roadmap.md)。

---

## ドキュメント索引

### 要件定義書（5 バケット時系列構造）

| # | バケット | 役割 |
|---|---|---|
| 1 | [1-vision/](docs/requirements/1-vision/) | ビジョン・ペルソナ・ユーザーストーリー |
| 2 | [2-foundation/](docs/requirements/2-foundation/) | 非機能・アーキテクチャ・LLM パイプライン・観測性・実装技術 |
| 3 | [3-cross-cutting/](docs/requirements/3-cross-cutting/) | ER 図・API 共通仕様 |
| 4 | [4-features/](docs/requirements/4-features/) | 個別機能の詳細仕様 |
| 5 | [5-roadmap/](docs/requirements/5-roadmap/) | ロードマップ・バックログ・スプリント |

→ 全体マップ：[docs/requirements/README.md](docs/requirements/README.md)

### 個別機能

- [GitHub OAuth ログイン](docs/requirements/4-features/authentication.md)
- [問題生成](docs/requirements/4-features/problem-generation.md)
- [問題表示・解答入力](docs/requirements/4-features/problem-display-and-answer.md)
- [自動採点](docs/requirements/4-features/grading.md)
- [学習履歴・統計](docs/requirements/4-features/learning.md)

### その他

- [SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) — 物理配置・コンポーネント責務・ジョブの流れ
- [docs/runbook/](docs/runbook/) — 運用 Runbook（R4 以降）

---

## 設計原則

- **可逆な判断は遅延させる**：LLM モデル選定・型チェッカー選定など、市場が変化する領域は実装着手時に決定
- **YAGNI**：使うか分からない抽象化を先取りしない
- **拡張容易性は構造的に確保**：認証 / LLM / サンドボックスは差し替え可能
- **遅延の不可逆性が高い判断は R0 から**：トレース連携・補完ツールは初期導入
- **規模に応じた選定**：Bazel・Kafka・Nx 等の "本格派" は不採用
- **設計判断は ADR で記録**：判断更新時は本文を直接書き換える

---

## ライセンス

[MIT License](LICENSE) © 2026 Yohei Jinbo

## 著者

神保 陽平 — Backend / AI Engineer 候補
