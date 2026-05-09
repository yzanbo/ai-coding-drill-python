# Contributing

このプロジェクトをローカルで動かしたい・開発に参加したい人向けのガイド。**設計判断・要件定義書を読みたい場合は [README.md](README.md) と [docs/](docs/) を参照してください**。

---

> ⚠️ **現状の注意（2026-05 時点）**
>
> 本プロジェクトは **設計フェーズ完了 / R1 着手予定** の状態です。以下のセットアップ手順・コマンドは **R0（基盤整備）以降に動作するようになる予定** で、現時点では `apps/` 配下のソース実体・`docker-compose.yml` 等は未整備です。
>
> - **進捗は [docs/requirements/5-roadmap/01-roadmap.md](docs/requirements/5-roadmap/01-roadmap.md) を参照**
> - 設計レビュー・面接準備のために本プロジェクトを評価している場合は [README.md](README.md) を起点に閲覧してください
> - 実装着手後、本ドキュメントの手順を最新化していきます

---

## クイックスタート

### 必要ツール

`mise` を入れれば残りは `mise install` で全て揃う（→ [ADR 0039](docs/adr/0039-mise-for-task-runner-and-tool-versions.md)）。

| ツール | 用途 | 取得方法 |
|---|---|---|
| `mise` | 言語ランタイム + パッケージマネージャ + タスクランナー（Python / Node / Go / uv / pnpm を一括管理） | `curl https://mise.run \| sh` |
| Docker | サンドボックス + ローカル DB / Redis | Docker Desktop / Engine |
| psql | DB クライアント（任意） | `brew install postgresql` 等 |

`mise install` で `mise.toml` に固定された以下が自動投入される（個別インストール不要）：

| ランタイム / ツール | バージョン | 用途 |
|---|---|---|
| Python | 3.13 | apps/api（FastAPI、ADR 0034） |
| Node.js | 22 | apps/web（Next.js、ADR 0036）+ commitlint |
| Go | 1.23 | apps/workers/*（採点・問題生成、ADR 0016 / 0040） |
| uv | latest | Python パッケージ管理（ADR 0035） |
| pnpm | latest | Frontend パッケージ管理（apps/web 内、ADR 0036） |
| lefthook | latest | Git フック管理（ADR 0021） |
| `@commitlint/cli` | latest | コミットメッセージ検証（ADR 0029） |

### セットアップ

```bash
# 1. リポジトリ取得
git clone https://github.com/yohei/ai-coding-drill.git
cd ai-coding-drill

# 2. mise でツール一括インストール + Git フック登録
mise run bootstrap
# 内部で `mise install` + `lefthook install` を実行

# 3. 環境変数を設定
cp .env.example .env
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env
# 各 .env を編集：DATABASE_URL / REDIS_URL / GitHub OAuth Secret 等

# 4. ローカル DB / Redis を起動
docker compose up -d

# 5. DB マイグレーション
mise run api:db-migrate

# 6. シードデータ投入（任意、apps/api 着手後）
cd apps/api && uv run python -m app.db.seeds

# 7. 各アプリを起動（別ターミナルで）
mise run api:dev               # FastAPI
mise run web:dev               # Next.js
mise run worker:grading:dev    # 採点 Worker
```

### 動作確認

| サービス | URL |
|---|---|
| Web | http://localhost:3000 |
| API ヘルスチェック | http://localhost:8000/healthz |
| Swagger UI（FastAPI 自動生成） | http://localhost:8000/docs |
| Redoc（FastAPI 自動生成） | http://localhost:8000/redoc |
| OpenAPI 3.1 JSON | http://localhost:8000/openapi.json |

---

## 主要な環境変数

ルート `.env`：

| 変数 | 例 | 説明 |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/ai_coding_drill` | Postgres 接続文字列（asyncpg ドライバ） |
| `REDIS_URL` | `redis://localhost:6379` | Redis 接続文字列 |

`apps/api/.env`：

| 変数 | 説明 |
|---|---|
| `PORT` | API サーバポート（既定 8000） |
| `GITHUB_CLIENT_ID` | GitHub OAuth App の Client ID |
| `GITHUB_CLIENT_SECRET` | GitHub OAuth App の Client Secret |
| `SESSION_SECRET` | セッション署名用秘密鍵（32 文字以上） |

`apps/web/.env`：

| 変数 | 説明 |
|---|---|
| `NEXT_PUBLIC_API_URL` | FastAPI の URL（例 `http://localhost:8000`） |

`apps/workers/grading/.env`（採点 Worker）：

| 変数 | 説明 |
|---|---|
| `DATABASE_URL` | Postgres 接続文字列 |
| `LLM_PROVIDER` / `LLM_MODEL` / `LLM_API_KEY` | judge LLM 設定（→ [ADR 0007](docs/adr/0007-llm-provider-abstraction.md)） |

---

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `docker compose up` で Postgres ポート衝突 | ホストの 5432 を使う既存 Postgres を停止、または `docker-compose.yml` のポートを変更 |
| `mise install` がツールを取得できない | shell を再起動して mise の activation を反映、または `mise doctor` で診断 |
| Alembic マイグレーション失敗 | DB が起動しているか `docker compose ps` で確認、ローカル限定で `dropdb`/`createdb` で初期化 |
| API が GitHub OAuth で 500 を返す | `.env` の `GITHUB_CLIENT_*` と `SESSION_SECRET` が設定されているか確認 |
| 採点 Worker が Docker に接続できない | `docker.sock` の権限確認、Docker Desktop が起動しているか確認 |

---

## ディレクトリ構成

```
apps/
├── web/                       Next.js（apps/web 配下に Frontend ツーリングを閉じる、ADR 0036）
├── api/                       FastAPI + SQLAlchemy 2.0 + Alembic（ADR 0034 / 0037）
└── workers/
    ├── grading/               採点 Worker（Go、ADR 0016 / 0040）
    └── generation/            問題生成 Worker（Go、将来追加、ADR 0040）
infra/                         Terraform（network / db / ecs / worker / monitoring）
docs/                          要件定義書（5 バケット構造）+ ADR + Runbook
.github/workflows/             GitHub Actions（CI / デプロイ）
docker-compose.yml             ローカル開発環境
mise.toml                      mise 設定（tool 版数 + タスク定義の SSoT、ADR 0039）
lefthook.yml                   Git フック設定
commitlint.config.mjs          コミットメッセージ規約（ADR 0029）
```

`packages/` は廃止済み（→ [ADR 0006](docs/adr/0006-json-schema-as-single-source-of-truth.md) / [ADR 0036](docs/adr/0036-frontend-monorepo-pnpm-only.md) / [ADR 0040](docs/adr/0040-worker-grouping-and-llm-in-worker.md)）。共有データ型は `apps/api/app/schemas/` の Pydantic を SSoT とし、境界別の 2 伝送路（HTTP API: `apps/api/openapi.json` → Hey API、Job キュー: `apps/api/job-schemas/` → quicktype）で TS / Go に展開する。

詳細は [docs/requirements/2-foundation/02-architecture.md](docs/requirements/2-foundation/02-architecture.md) を参照。

---

## 開発コマンド

タスク命名は `<scope>:<sub>:<verb>` 階層コロン形式（→ [ADR 0039](docs/adr/0039-mise-for-task-runner-and-tool-versions.md)）。タスク定義の SSoT は `mise.toml`。

### 横断（全言語）

```bash
mise run lint             # 全言語 lint
mise run test             # 全言語 test
mise run typecheck        # 全言語 typecheck
mise run types-gen        # OpenAPI → 各言語の型生成パイプライン
```

### Backend（apps/api、Python / FastAPI）

```bash
mise run api:dev                  # FastAPI 開発サーバ
mise run api:test                 # pytest
mise run api:lint                 # ruff check
mise run api:format               # ruff format
mise run api:typecheck            # pyright
mise run api:audit                # pip-audit（脆弱性スキャン）
mise run api:deps-check           # deptry（依存衛生）
mise run api:db-migrate           # alembic upgrade head
mise run api:db-revision -- "<msg>"  # alembic revision --autogenerate
mise run api:openapi-export       # OpenAPI 3.1 JSON を apps/api/openapi.json に書き出し
```

### Frontend（apps/web、Next.js / TS）

```bash
mise run web:dev          # next dev
mise run web:test         # vitest
mise run web:lint         # biome check
mise run web:format       # biome check --write
mise run web:typecheck    # tsc --noEmit
mise run web:knip         # 未使用検出
mise run web:syncpack     # package.json 整合性
mise run web:types-gen    # Hey API で OpenAPI から TS / Zod / HTTP クライアント生成
mise run web:e2e          # Playwright E2E
```

### Workers（apps/workers/*、Go）

```bash
# 採点 Worker
mise run worker:grading:dev          # go run ./cmd/grading
mise run worker:grading:test         # go test ./...
mise run worker:grading:lint         # golangci-lint run
mise run worker:grading:audit        # govulncheck ./...
mise run worker:grading:types-gen    # quicktype で Go struct 生成

# 問題生成 Worker（apps/workers/generation 着手時に有効化）
mise run worker:generation:dev
mise run worker:generation:test

# 横断
mise run worker:test      # 全 Worker の go test
mise run worker:lint      # 全 Worker の golangci-lint
mise run worker:types-gen # 全 Worker の Go struct 生成
```

### Git 作業の補助

```bash
mise run git:clean        # マージ済みでリモートが消えたローカルブランチを一括削除
                          #（必要なら main へ切替・最新化）
```

`git:clean` の挙動：

1. 未コミット変更があれば中断
2. `git fetch --prune` でリモート追跡参照を整理
3. 現在ブランチがリモートで削除済み（`[gone]` 状態）なら main へ切替・`git pull --ff-only` で最新化
4. `[origin/...: gone]` 状態のローカルブランチを全列挙して `git branch -D` で削除

未 push のローカル専用ブランチや、リモートに残っているブランチは対象外（誤削除されない）。詳細は [scripts/cleanup-merged-branches.sh](scripts/cleanup-merged-branches.sh) と [ADR 0032](docs/adr/0032-github-repository-settings.md) を参照。

### サンドボックスイメージ

```bash
docker build -t ai-coding-drill-sandbox:latest apps/workers/grading/sandbox
```

---

## ブランチ戦略・コミットルール

- **ブランチ戦略**：Trunk-based + フィーチャーブランチ
  - `main` が唯一の長期ブランチ
  - 機能開発は `feature/<scope>/<short-name>` で作業 → PR → main へマージ
  - リリースはタグ（`v0.1.0` 等）で管理、リリースブランチは作らない
- **コミット**：意味のある単位で commit
  - メッセージは日本語または英語、Conventional Commits 形式（`feat(api): ...`、`fix(worker): ...` 等）
  - commitlint で機械的に検証（[ADR 0029](docs/adr/0029-commit-scope-convention.md)）
- **Git フック（lefthook）**：`mise run bootstrap` で自動セットアップ
  - **pre-commit**：apps/* 着手時に各言語の lint / format / typecheck フックを追加
  - **commit-msg**：commitlint がコミットメッセージ規約を検証
- **PR**：本文は日本語、概要・テスト方法を記載

詳細なブランチ命名規則・PR 規約は [.claude/CLAUDE.md](.claude/CLAUDE.md) を参照。

---

## カスタムコマンド（要件駆動開発フロー）

`.claude/skills/` 配下に開発フロー支援のカスタムコマンドを用意：

| コマンド | 用途 |
|---|---|
| `/new-requirements` | 機能別要件 .md を対話的に新規作成（[4-features/](docs/requirements/4-features/) 配下） |
| `/update-requirements` | 要件を先に更新してから実装を修正 |
| `/verify-requirements` | 要件と実装の整合性を検証 |
| `/backend-implement` | 要件 .md を読んで FastAPI 実装 |
| `/backend-new-module` | FastAPI モジュール（router / schema / service / repository）をスキャフォールド |
| `/frontend-implement` | 要件 .md を読んで Next.js 実装 |
| `/worker-implement` | Go 採点 Worker の実装 |
| `/backend-test` `/frontend-test` `/worker-test` | 各レイヤのテスト生成・実行 |
| `/onboarding` | 新規参画者向けプロジェクト案内 |

詳細は各 `SKILL.md`（[.claude/skills/](.claude/skills/)）を参照。

---

## 関連ドキュメント

- [README.md](README.md) — プロジェクト概観・設計判断・差別化軸
- [docs/requirements/](docs/requirements/) — 要件定義書（5 バケット構造）
- [docs/adr/](docs/adr/) — Architecture Decision Records
- [docs/runbook/](docs/runbook/) — 運用 Runbook（R4 以降で整備）
- [.claude/CLAUDE.md](.claude/CLAUDE.md) — Claude Code 利用時のプロジェクト規約
