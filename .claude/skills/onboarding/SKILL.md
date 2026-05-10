---
name: onboarding
description: 新規参画者向けのプロジェクトオンボーディングを対話的に進める
argument-hint: "(省略可) backend / frontend / worker / fullstack"
---

# プロジェクトオンボーディング

引数 `$ARGUMENTS` が指定された場合、その担当領域（backend / frontend / worker / fullstack）に特化した案内を行う。
省略された場合は、最初にヒアリングして担当領域を決定する。

## 手順

### 1. ヒアリング（対話フェーズ）

引数が省略された場合、AskUserQuestion で確認する：

- **担当領域**：バックエンド（FastAPI）／ フロントエンド（Next.js）／ Worker（採点 / 問題生成、Go、ADR 0040）／ フルスタック
- **経験レベル**：使用技術（FastAPI, SQLAlchemy 2.0, Next.js, Go, Postgres 等）の経験有無

ヒアリング結果に応じて、以降のステップで強調する内容を調整する。

### 2. プロジェクト概要の説明

以下の情報源を読み込み、要点を分かりやすく説明する：

- [README.md](../../../README.md) — ハイライト・技術スタック・クイックスタート
- [SYSTEM_OVERVIEW.md](../../../SYSTEM_OVERVIEW.md) — 物理配置・コンポーネント責務・ジョブの流れ
- [.claude/CLAUDE.md](../../CLAUDE.md) — 開発フロー・コマンド・規約
- [01-overview.md](../../../docs/requirements/1-vision/01-overview.md) — プロジェクトの目的・ターゲット

説明すべき内容：

- **プロダクト**：AI Coding Drill — LLM 自動生成 × サンドボックス採点の TS 学習サイト
- **アーキテクチャ**：3 言語ポリグロット（Python for API、TS for Web、Go for Worker 群、→ [ADR 0033](../../../docs/adr/0033-backend-language-pivot-to-python.md) / [ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）
- **タスクランナー / tool 版数**：mise（uv / pnpm / Go を一括管理、→ [ADR 0039](../../../docs/adr/0039-mise-for-task-runner-and-tool-versions.md)）。Turborepo は不採用（→ [ADR 0036](../../../docs/adr/0036-frontend-monorepo-pnpm-only.md)）
- **DB / キュー**：Postgres + SQLAlchemy 2.0 async + Alembic（→ [ADR 0037](../../../docs/adr/0037-sqlalchemy-alembic-for-database.md)）、ジョブキューも Postgres `SELECT FOR UPDATE SKIP LOCKED`
- **キャッシュ**：Upstash Redis（ジョブキュー用途では使わない）
- **インフラ**：AWS 単独（ECS Fargate + EC2 + RDS + ECR + Route 53）

### 3. アーキテクチャ・設計判断の説明

[02-architecture.md](../../../docs/requirements/2-foundation/02-architecture.md) と [docs/adr/](../../../docs/adr/) の代表的な ADR を紹介：

- [ADR 0004: Postgres ジョブキュー](../../../docs/adr/0004-postgres-as-job-queue.md) — なぜ Redis Streams ではないか
- [ADR 0015: CodeMirror 6 採用](../../../docs/adr/0015-codemirror-over-monaco.md) — なぜ Monaco ではないか
- [ADR 0016: Go 採点 Worker](../../../docs/adr/0016-go-for-grading-worker.md) — なぜ Node ではないか（リネーム後のパスは [ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md) 参照）
- [ADR 0009: 使い捨てコンテナ](../../../docs/adr/0009-disposable-sandbox-container.md) — なぜウォームプールではないか
- [ADR 0007: LLM プロバイダ抽象化](../../../docs/adr/0007-llm-provider-abstraction.md) — なぜ特定モデルに固定しないか
- [ADR 0006: JSON Schema を SSoT](../../../docs/adr/0006-json-schema-as-single-source-of-truth.md) — 多言語間の型整合性

担当領域に応じて、特に関わりの深い ADR を重点的に紹介する。

### 4. ドメインモデルの説明

[01-data-model.md](../../../docs/requirements/3-cross-cutting/01-data-model.md) の ER 図をもとに：

- `users` + `auth_providers`（プロバイダ非依存設計、→ [ADR 0011](../../../docs/adr/0011-github-oauth-with-extensible-design.md)）
- `problems`（カテゴリ・難易度・テストケース・模範解答・LLM Judge スコア）
- `submissions`（ユーザー解答、採点結果）
- `generation_requests`（問題生成の非同期リクエスト）
- `jobs`（ジョブキュー、SKIP LOCKED で取得）

### 5. 開発ワークフローの説明

[.claude/CLAUDE.md: 開発ワークフロー](../../CLAUDE.md) をもとに、要件駆動の開発フローを説明する：

```
/new-requirements → /backend-implement → /backend-test
                  → /frontend-implement → /frontend-test
                  → /worker-implement → /worker-test
```

各コマンドの役割：

| コマンド | 用途 |
|---|---|
| `/new-requirements` | 機能要件 .md を対話的に新規作成 |
| `/update-requirements` | 要件を先に更新してから実装を修正 |
| `/verify-requirements` | 要件と実装の整合性を検証 |
| `/backend-implement` | 要件 .md を読んで FastAPI 実装 |
| `/backend-test` | バックエンドのユニットテスト生成・実行 |
| `/backend-new-module` | FastAPI モジュール（router / schema / service / repository）をスキャフォールド |
| `/frontend-implement` | 要件 .md を読んで Next.js 実装 |
| `/frontend-test` | フロントエンドのテスト生成・実行 |
| `/worker-implement` | Go Worker の実装 |
| `/worker-test` | Go Worker のテスト生成・実行 |

**重要**：機能追加は必ず `docs/requirements/4-features/` の要件 .md から始める。

### 6. 担当領域別の規約説明

担当領域に応じて、対応するルールファイルを読み込んで要点を説明する。

#### バックエンド担当の場合
- [.claude/rules/backend.md](../../rules/backend.md) — FastAPI ディレクトリ構成、SQLAlchemy 2.0 async クエリ、認証・認可、Pydantic SSoT、コーディング規約
- [.claude/rules/alembic-sqlalchemy.md](../../rules/alembic-sqlalchemy.md) — Postgres スキーマ、Alembic マイグレーション、`jobs` テーブルの扱い

#### フロントエンド担当の場合
- [.claude/rules/frontend.md](../../rules/frontend.md) — App Router 構成、RSC vs Client、CodeMirror、TanStack Query

#### 採点 Worker 担当の場合
- [.claude/rules/worker.md](../../rules/worker.md) — Go 構成、Docker クライアント、ジョブ取得・処理パターン、Worker 内 LLM 呼び出し（ADR 0040）

#### LLM プロンプト関連の場合
- [.claude/rules/prompts.md](../../rules/prompts.md) — YAML 構造、バージョン管理、A/B テスト
- [03-llm-pipeline.md](../../../docs/requirements/2-foundation/03-llm-pipeline.md) — 4 レイヤ品質評価の全体像

#### フルスタック担当の場合
- 上記すべてを読み込んで説明する

### 7. ローカル環境の起動

[README.md](../../../README.md) のクイックスタートに沿って実際に起動を試してもらう：

```bash
git clone git@github-yzanbo:yzanbo/ai-coding-drill.git
cd ai-coding-drill
cp .env.example .env
# 各 .env を編集
mise run bootstrap        # mise install + lefthook install
docker compose up -d
mise run api:db-migrate
# 別ターミナルで以下を起動
mise run api:dev
mise run web:dev
mise run worker:grading:dev
```

動作確認 URL：

- Web：http://localhost:3000
- Swagger UI（FastAPI 自動生成）：http://localhost:8000/docs
- Redoc：http://localhost:8000/redoc
- OpenAPI 3.1 JSON：http://localhost:8000/openapi.json

### 8. 開発フェーズの現在地

[01-roadmap.md](../../../docs/requirements/5-roadmap/01-roadmap.md) で現在の Phase を伝え、次に取り組むべき作業を案内する。
