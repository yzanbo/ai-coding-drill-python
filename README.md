# AI Coding Drill

> LLM が自動生成したプログラミング問題を、サンドボックス環境で検証・採点する学習サイト。
> 「LLM の出力を信用せず、サンドボックスで動作保証する」設計思想を実装したポートフォリオプロジェクト。

🚀 **デモ**: _（デプロイ後に追記予定）_

---

## ハイライト

このプロジェクトの差別化軸：

1. **LLM 生成 × サンドボックス検証 × 多層品質保証パイプライン**
   生成された問題は、模範解答がサンドボックスで動作することを確認するまで DB に保存されない。「動かないコードが混入する」既存サービスの根本問題を構造的に解決。

2. **品質評価の 4 レイヤ防御**（決定論チェック / LLM-as-a-Judge / ユーザー行動シグナル / 集合的評価）
   ミューテーションテスト・複数モデルによる多軸評価・人間評価との相関分析を組み合わせ、LLM 生成物の品質を継続的に担保。

3. **TypeScript + Go のポリグロット構成**（Phase 7 で Python 追加）
   実装速度（NestJS）・採点ワーカーの軽量並列性（Go）・LLM/評価エコシステム（Python）を、フェーズに応じて適材適所で導入。

4. **Postgres ジョブキュー**（`SELECT FOR UPDATE SKIP LOCKED` + `LISTEN/NOTIFY`）
   外部キューミドルウェア不要、解答登録とジョブ登録を同一トランザクションで処理。Outbox パターン回避。

5. **使い捨てコンテナによるサンドボックス**（Docker → gVisor → Firecracker の段階強化）
   ジョブごとにコンテナを生成・破棄。前回実行の影響が原理的に残らない強い隔離。

6. **LLM プロバイダ抽象化レイヤ**（Anthropic / Google / OpenAI / OpenRouter を差し替え可能）
   モデル選定はベンチマークに基づき適時更新。「アーキテクチャ判断とモデル選定を分離する」設計原則を実装。

7. **AWS 単独 + IaC（Terraform）+ 観測性（OTel + Grafana + Sentry）**
   コスト最適化（月 $10〜30）・無料枠活用・運用設計まで含めたエンドツーエンドの構成。

---

## 技術スタック概要

| レイヤ | 採用技術 |
|---|---|
| **フロントエンド** | Next.js（App Router）+ Tailwind CSS + CodeMirror 6 + TanStack Query |
| **バックエンド API** | NestJS（TypeScript）+ Passport（GitHub OAuth）+ Drizzle ORM |
| **採点ワーカー** | Go + Docker クライアント（公式）+ pgx |
| **データストア** | PostgreSQL 16（DB + ジョブキュー兼任）+ Upstash Redis（キャッシュ・セッション） |
| **LLM** | プロバイダ抽象化（Anthropic / Gemini / OpenAI / OpenRouter 差し替え可） |
| **サンドボックス** | Docker（使い捨てコンテナ）→ Phase 2 で gVisor → Phase 3 で Firecracker |
| **モノレポ** | Turborepo + pnpm workspaces |
| **コード品質** | Biome（lint+format）+ TypeScript（tsc）+ gofmt + golangci-lint |
| **インフラ** | AWS（ECS Fargate + EC2 + RDS + ECR + Route 53）+ Terraform |
| **観測性** | OpenTelemetry + Grafana + Loki + Tempo + Sentry |
| **CI/CD** | GitHub Actions |

詳細は [docs/requirements/base/07_tech_stack.md](docs/requirements/base/07_tech_stack.md) を参照。

---

## クイックスタート

### 必要ツール

| ツール | バージョン | 用途 |
|---|---|---|
| Node.js | 20+ | TS アプリ実行 |
| pnpm | 9+ | パッケージ管理 |
| Go | 1.22+ | 採点ワーカー |
| Docker | Desktop / Engine | サンドボックス + ローカル DB |
| psql | 任意 | DB クライアント（デバッグ用） |

### セットアップ

```bash
# 1. リポジトリ取得
git clone https://github.com/yohei/ai-coding-drill.git
cd ai-coding-drill

# 2. 環境変数を設定
cp .env.example .env
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env
# 各 .env を編集：DATABASE_URL / REDIS_URL / GitHub OAuth Secret 等

# 3. 依存パッケージをインストール
pnpm install

# 4. ローカル DB / Redis を起動
docker compose up -d

# 5. DB マイグレーション
pnpm db:migrate

# 6. シードデータ投入（任意）
pnpm db:seed

# 7. 全アプリを並列起動
pnpm dev
```

### 動作確認

| サービス | URL |
|---|---|
| Web | http://localhost:3000 |
| API（Swagger UI） | http://localhost:3001/api/docs |
| API ヘルスチェック | http://localhost:3001/healthz |
| Drizzle Studio（DB GUI） | `pnpm db:studio` で起動 |

### 主要な環境変数

ルート `.env`：
| 変数 | 例 | 説明 |
|---|---|---|
| `DATABASE_URL` | `postgresql://user:pass@localhost:5432/aicoding` | Postgres 接続文字列 |
| `REDIS_URL` | `redis://localhost:6379` | Redis 接続文字列 |
| `NODE_ENV` | `development` | 実行環境 |

`apps/api/.env`：
| 変数 | 説明 |
|---|---|
| `PORT` | API サーバポート（既定 3001） |
| `GITHUB_CLIENT_ID` | GitHub OAuth App の Client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth App の Client Secret |
| `SESSION_SECRET` | セッション署名用秘密鍵（32 文字以上） |
| `ANTHROPIC_API_KEY` | Claude API キー（採用時） |
| `GEMINI_API_KEY` | Gemini API キー（採用時） |

`apps/web/.env`：
| 変数 | 説明 |
|---|---|
| `NEXT_PUBLIC_API_URL` | API サーバの URL（例 `http://localhost:3001`） |

### トラブルシューティング

| 症状 | 対処 |
|---|---|
| `docker compose up` で Postgres ポート衝突 | ホストの 5432 を使う既存 Postgres を停止、または `docker-compose.yml` のポートを変更 |
| `pnpm install` が遅い・失敗する | `pnpm store prune` でキャッシュクリア |
| Drizzle マイグレーション失敗 | DB が起動しているか `docker compose ps` で確認、`pnpm db:reset` で初期化 |
| API が GitHub OAuth で 500 を返す | `.env` の `GITHUB_CLIENT_*` と `SESSION_SECRET` が設定されているか確認 |
| 採点ワーカーが Docker に接続できない | `docker.sock` の権限確認、Docker Desktop が起動しているか確認 |
| Vitest 実行時 `tsx` not found | サンドボックスイメージを再ビルド：`pnpm sandbox:build` |

---

## ディレクトリ構成

```
apps/                    実行可能アプリ（web / api / grading-worker）
packages/                共有パッケージ（shared-types / prompts / config）
infra/                   Terraform（network / db / ecs / worker / monitoring）
docs/                    要件定義書（10 章）+ ADR（15 本以上）
.github/workflows/       GitHub Actions（CI / デプロイ）
docker-compose.yml       ローカル開発環境
turbo.json               Turborepo 設定
pnpm-workspace.yaml      pnpm workspaces 設定
biome.json               Biome 設定
```

詳細な構成は [docs/adr/0012-turborepo-pnpm-monorepo.md](docs/adr/0012-turborepo-pnpm-monorepo.md) を参照。

---

## 開発コマンド

### Turborepo タスク

```bash
pnpm dev                 # 全アプリ並列起動
pnpm build               # 全パッケージビルド（依存順）
pnpm test                # 全テスト実行
pnpm lint                # Biome チェック
pnpm format              # Biome フォーマット
pnpm typecheck           # tsc --noEmit（型チェック）
```

### 個別アプリのみ実行

```bash
pnpm --filter @ai-coding-drill/web dev
pnpm --filter @ai-coding-drill/api dev
pnpm --filter @ai-coding-drill/grading-worker dev
```

### DB 関連

```bash
pnpm db:migrate          # マイグレーション適用
pnpm db:reset            # DB を初期化（破壊的）
pnpm db:seed             # シードデータ投入
pnpm db:studio           # Drizzle Studio 起動
pnpm db:generate         # マイグレーション生成（スキーマ変更後）
```

### Go ワーカー

```bash
cd apps/grading-worker
go run ./cmd/worker      # ローカル実行
go test ./...            # テスト
golangci-lint run        # リント
```

### サンドボックスイメージ

```bash
pnpm sandbox:build       # 採点用コンテナイメージビルド
```

---

## ドキュメント

### 要件定義書（base）

プロジェクトの設計全体を 10 章で記述：

| # | ファイル | 内容 |
|---|---|---|
| 01 | [overview](docs/requirements/base/01_overview.md) | プロジェクト概要・ゴール |
| 02 | [functional](docs/requirements/base/02_functional.md) | 機能要件 |
| 03 | [non_functional](docs/requirements/base/03_non_functional.md) | 非機能要件 |
| 04 | [architecture](docs/requirements/base/04_architecture.md) | アーキテクチャ・データフロー |
| 05 | [llm_pipeline](docs/requirements/base/05_llm_pipeline.md) | LLM パイプライン・品質評価 |
| 06 | [observability](docs/requirements/base/06_observability.md) | 観測性 |
| 07 | [tech_stack](docs/requirements/base/07_tech_stack.md) | 技術スタック・選定理由 |
| 08 | [milestones](docs/requirements/base/08_milestones.md) | マイルストーン |
| 09 | [data_model](docs/requirements/base/09_data_model.md) | ER 図・テーブル定義 |
| 10 | [api_spec](docs/requirements/base/10_api_spec.md) | API 仕様 |

### ADR（Architecture Decision Records）

重要な設計判断の履歴：[docs/adr/](docs/adr/)

代表的な ADR：
- [0001: Postgres をジョブキューに採用](docs/adr/0001-postgres-as-job-queue.md)
- [0003: CodeMirror 6 採用（Monaco 不採用）](docs/adr/0003-codemirror-over-monaco.md)
- [0008: 採点コンテナの使い捨て方式](docs/adr/0008-disposable-sandbox-container.md)
- [0011: LLM プロバイダ抽象化戦略](docs/adr/0011-llm-provider-abstraction.md)
- [0014: JSON Schema を Single Source of Truth に](docs/adr/0014-json-schema-as-single-source-of-truth.md)

### システム概要

[SYSTEM_OVERVIEW.md](SYSTEM_OVERVIEW.md) — 物理配置・コンポーネントの責務・ジョブの流れ。

---

## アーキテクチャ概要

```
[User Browser]
     ↓
[Next.js (Vercel)]
     ↓
[NestJS API (ECS Fargate)]
     ├── PostgreSQL (RDS) ← jobs テーブルが LISTEN/NOTIFY でワーカーに通知
     ├── Upstash Redis（キャッシュ・セッション）
     └── LLM API（プロバイダ抽象化レイヤ経由）
            ↓
[Go 採点ワーカー (EC2)]
     ├── Docker Engine
     └── 使い捨て採点コンテナ（Vitest 実行）
```

詳細は [04_architecture.md](docs/requirements/base/04_architecture.md) を参照。

---

## 開発フェーズ

| Phase | 内容 | 状態 |
|---|---|---|
| Phase 0 | 基盤整備（モノレポ・Docker Compose・CI 雛形） | _未着手_ |
| Phase 1 | MVP（認証・問題生成・採点・最低限フロント） | _未着手_ |
| Phase 2 | 品質保証パイプライン（Judge・ミューテーションテスト） | _未着手_ |
| Phase 3 | サンドボックス強化（gVisor） | _未着手_ |
| Phase 4 | 観測性（OTel・Grafana・管理ダッシュボード） | _未着手_ |
| Phase 5 | 仕上げ（IaC・E2E・本番デプロイ） | _未着手_ |
| Phase 7 | Python 評価パイプライン + RAG | _Phase 6 以降の任意_ |

詳細は [08_milestones.md](docs/requirements/base/08_milestones.md) を参照。

---

## 設計原則

このプロジェクトで一貫している設計判断の哲学：

- **可逆な判断は遅延させる**：LLM モデル選定・Python 型チェッカー選定など、市場が変化する領域は実装着手時に決定
- **過剰設計を避ける**：使うか分からない抽象化を先取りで作らない（YAGNI）
- **ただし拡張容易性は構造的に確保**：認証プロバイダ・LLM プロバイダ・サンドボックスランタイムは差し替え可能に
- **規模に応じた選定**：このプロジェクト規模（小〜中）に最適なツールを選ぶ。Bazel・Kafka・Nx 等の "本格派" は不採用
- **設計判断を ADR で記録**：「なぜそう決めたか」「他案は何だったか」を Append-only で残す

---

## 開発フロー

- **ブランチ戦略**：Trunk-based + フィーチャーブランチ
  - `main` が唯一の長期ブランチ
  - 機能開発は `feature/<short-name>` で作業 → PR → main へマージ
  - リリースはタグ（`v0.1.0` 等）で管理、リリースブランチは作らない
- **コミット**：意味のある単位で commit、メッセージは英語推奨（実装中に Conventional Commits 採用判断）

---

## ライセンス

[MIT License](LICENSE) © 2026 Yohei Jinbo

---

## 著者

神保 陽平 — Backend / AI Engineer 候補
