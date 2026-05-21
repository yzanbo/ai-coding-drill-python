# AI Coding Drill（Python 版）

LLM が自動生成したプログラミング問題を、サンドボックス環境で検証・採点する学習サイト。

ローカルで動かすための手順を以下に示します。プロジェクトの概観・設計判断・差別化軸については [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。

---

## 現在の進捗（2026-05 時点）

| フェーズ | 状態 | 内容 |
|---|---|---|
| 設計フェーズ（TS 版） | ✅ 完了 | ADR / 要件定義書 / アーキテクチャ図 / バックログ — `v1.0.0-typescript` で凍結 |
| Python pivot 設計 | ✅ 完了 | ADR 0033〜0049 起票、Pydantic SSoT + 境界別 2 伝送路に再設計 |
| **R0 基盤構築** | ✅ 完了 | mise / uv / pnpm / Docker Compose / CI / Backend・Frontend・Worker レイヤ分割 / 型同期パイプライン / MCP（11 項目すべて完了） |
| **R1 MVP** | ✅ 完了 | R1-1 GitHub OAuth / R1-2 LLM プロバイダ抽象化 / R1-3 問題生成 / R1-4 問題表示・解答入力 / R1-5 自動採点 / R1-6 学習履歴・統計 / R1-7 問題生成履歴・状態管理（すべて完了） |
| **R2 品質保証パイプライン** ★ | ⏳ 着手前（次フェーズ） | LLM-as-a-Judge（grading worker 内）/ ミューテーションテスト / プロンプトキャッシュ + Redis レスポンスキャッシュ / 構造化出力厳密化 / 非同期ジョブ化（リトライ・DLQ・スタックジョブ回収・180 秒タイムアウト・コスト上限）。**ポートフォリオ評価の核**（「LLM 出力を信用しない」設計思想を動作で示す） |
| **R3 サンドボックス強化** ★ | ⏳ 未着手 | gVisor 対応 + Docker vs gVisor ベンチマーク / セキュリティドキュメント化 |
| **R4 観測性** ★ | ⏳ 未着手 | OpenTelemetry SDK（FastAPI / Go 両側）/ プロセス境界トレース連携（W3C Trace Context 実値化）/ Grafana ダッシュボード / Sentry 接続 + PII マスキング / アラート整備 / 管理ダッシュボード |
| **R5 仕上げ・公開** | ⏳ 未着手 | IaC（Terraform）/ 本番デプロイパイプライン / E2E テスト主要フロー（Playwright）/ README に設計判断・ベンチマーク・デモ動画を整備 |
| R6〜R9（任意） | ⏸️ 後回し | R6 適応型出題 + LLM ヒント / R7 apps/workers/generation 機能実装 + RAG / R8 多言語化（Python / React）/ R9 Firecracker microVM |

> ★ = ポートフォリオ評価の核となるフェーズ（[01-roadmap.md: ロードマップ](docs/requirements/5-roadmap/01-roadmap.md#ロードマップリリース単位) より）。期間目安：R0〜R5 で 専業 6〜8 週 / 兼業 2〜3 ヶ月。

---

## 基本操作

問題作成

https://github.com/user-attachments/assets/1a062a44-836f-4c13-a663-56003dcfdd8b


解答

https://github.com/user-attachments/assets/274945a1-9627-4cd0-a479-c72b0f2b7744



## 必要ツール

`mise` を入れれば残りは `mise install` で揃う（→ [ADR 0039](docs/adr/0039-mise-for-task-runner-and-tool-versions.md)）。

| ツール | 用途 | 取得方法 |
|---|---|---|
| `mise` | 言語ランタイム + パッケージマネージャ + タスクランナー | `curl https://mise.run \| sh` または `brew install mise`（macOS） |
| Docker | サンドボックス + ローカル DB / Redis | Docker Desktop / Engine |
| psql | DB クライアント（任意） | `brew install postgresql` 等 |

`mise install` が `mise.toml` から Python / Node.js / Go / uv / pnpm / lefthook / commitlint を自動投入する。具体版数の SSoT は [mise.toml](mise.toml)。

---

## セットアップ

```bash
# 1. リポジトリ取得
git clone https://github.com/yzanbo/ai-coding-drill-python.git
cd ai-coding-drill-python

# 2. mise でツール一括インストール + Git フック登録
mise run bootstrap
# 内部で `mise install` + `lefthook install` を実行

# 3. 環境変数を設定（ルート .env は不要、各 app に配置する）
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env
cp apps/workers/grading/.env.example apps/workers/grading/.env
# 各 .env を編集：DATABASE_URL / REDIS_URL / GitHub OAuth Secret / LLM API Key 等

# 4. ローカル DB / Redis を起動
docker compose up -d

# 5. DB マイグレーション
mise run api:db-migrate

# 6. シードデータ投入（任意、apps/api 着手後）
cd apps/api && uv run python -m app.db.seeds

# 7. 各アプリを起動
mise run dev:all               # FastAPI + Next.js を並行起動（推奨、Ctrl-C で両方止まる）
mise run dev:restart           # :3000 / :8000 を listen 中のプロセスを kill して dev:all
# 個別に動かしたい場合は別ターミナルで:
mise run api:dev               # FastAPI のみ
mise run web:dev               # Next.js のみ
mise run worker:grading:dev    # 採点 Worker
```

### 動作確認

| サービス | URL |
|---|---|
| Web | http://localhost:3000 |
| API ヘルスチェック | http://localhost:8000/healthz |
| Swagger UI | http://localhost:8000/docs |
| Redoc | http://localhost:8000/redoc |
| OpenAPI 3.1 JSON | http://localhost:8000/openapi.json |

### データモデル（ER 図）

- [docs/requirements/3-cross-cutting/01-data-model.md](docs/requirements/3-cross-cutting/01-data-model.md) — Mermaid 形式の全体俯瞰 ER 図 + 命名規則 / ID 戦略 / 削除方針 / インデックス設計
- GitHub 上で開くと Mermaid が自動レンダリングされます

---

## 主要な環境変数

3 種類に分類されます。色付きで区別：

- 🟢 **コピーだけで動く**：`.env.example` をコピーすれば既定値で起動可能（編集不要）
- 🟡 **自分で取得して設定が必要**：外部サービスでキー発行などが要る（**未設定だと該当機能が動かない**）
- ⚪ **任意の上書き**：通常は既定値のままで OK、必要に応じて変更

### `apps/api/.env`（FastAPI）

| | 変数 | 既定値 / 説明 |
|---|---|---|
| 🟡 | `GITHUB_CLIENT_ID` | **要設定**。[GitHub Developer Settings](https://github.com/settings/developers) で OAuth App を作成して取得 |
| 🟡 | `GITHUB_CLIENT_SECRET` | **要設定**。同上 |
| 🟢 | `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/ai_coding_drill` |
| 🟢 | `REDIS_URL` | `redis://localhost:6379/0` |
| 🟢 | `APP_ENV` | `dev`（本番は `production` で安全装置が有効化される） |
| 🟢 | `GITHUB_REDIRECT_URI` | `http://localhost:8000/auth/github/callback`（GitHub OAuth App の Authorization callback URL と一致させる） |
| 🟢 | `SESSION_SIGNING_SECRET` | `dev-only-change-me`（dev はこのまま、**本番は必ず差し替え**。例：`python -c "import secrets; print(secrets.token_urlsafe(48))"`） |
| 🟢 | `COOKIE_SECURE` / `SESSION_TTL_SECONDS` / `FRONTEND_BASE_URL` 等 | 既定値で動作（詳細は `.env.example` のコメント） |

### `apps/web/.env`（Next.js）

| | 変数 | 既定値 / 説明 |
|---|---|---|
| 🟢 | `API_PROXY_TARGET` | `http://localhost:8000`（FastAPI への rewrites 転送先） |

### `apps/workers/grading/.env`（採点 Worker）

| | 変数 | 既定値 / 説明 |
|---|---|---|
| 🟡 | `GOOGLE_API_KEY` | **要設定**。Google Gemini API キー。[Google AI Studio](https://aistudio.google.com/apikey) で取得（無料枠あり、MVP は Gemini 単独運用、[ADR 0049](docs/adr/0049-initial-llm-model-selection.md)） |
| 🟢 | `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/ai_coding_drill`（pgx 用） |
| 🟢 | `WORKER_CONCURRENCY` | `4`（並列 goroutine 数） |
| 🟢 | `JOB_TIMEOUT_SECONDS` | `5`（1 ジョブのタイムアウト秒） |
| 🟢 | `RECLAIM_AFTER_MINUTES` | `5`（スタックジョブを `queued` に戻す閾値） |
| 🟢 | `SANDBOX_IMAGE` | `ai-coding-drill-sandbox:latest` |
| 🟢 | `LLM_CONFIG_PATH` | `llm.yaml`（プロバイダ / モデル割り当て YAML、再ビルド不要で差し替え可能、[ADR 0007](docs/adr/0007-llm-provider-abstraction.md)） |
| ⚪ | `WORKER_ID` | 空欄なら `os.Hostname()` にフォールバック |
| ⚪ | `SANDBOX_TMP_DIR` | 空欄なら OS 既定 `$TMPDIR`。macOS Docker Desktop の File Sharing 制限時のみ `/tmp` 等を明示 |
| ⚪ | `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | R2 ベンチマーク開始時のみ設定。MVP は空欄で構わない |

> 要するに、ローカルで動かすために**自分で取得が必要な値は `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` / `GOOGLE_API_KEY` の 3 つだけ**。残りはコピーで起動できます。

---

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| `docker compose up` で Postgres ポート衝突 | ホストの 5432 を使う既存 Postgres を停止、または `docker-compose.yml` のポートを変更 |
| `mise install` がツールを取得できない | shell を再起動して mise の activation を反映、または `mise doctor` で診断 |
| Alembic マイグレーション失敗 | `docker compose ps` で DB 起動確認、ローカル限定で `dropdb`/`createdb` で初期化 |
| API が GitHub OAuth で 500 を返す | `.env` の `GITHUB_CLIENT_*` と `SESSION_SECRET` を確認 |
| 採点 Worker が Docker に接続できない | `docker.sock` の権限と Docker Desktop の起動を確認 |

---

## 開発コマンド

タスク命名は `<scope>:<sub>:<verb>`。定義の SSoT は [mise.toml](mise.toml)。

### 横断（全言語）

```bash
mise run lint             # 全言語 lint
mise run test             # 全言語 test
mise run typecheck        # 全言語 typecheck（api + web）
mise run dev:all          # web + api を並行起動
mise run dev:restart      # :3000 / :8000 を kill してから dev:all
mise run types-gen        # 両境界の型を一括再生成（OpenAPI + Job Schema + Hey API + quicktype）
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
mise run web:types-gen    # Hey API で OpenAPI から TS / Zod / クライアント生成
mise run web:e2e          # Playwright E2E（先に test:up が動く）
mise run test:up          # テスト用 Postgres :5433 + Redis :6380 を起動して migrations 適用
mise run test:down        # テスト用 Postgres + Redis を停止 + ボリューム破棄
```

> E2E は dev DB と物理分離（issue #86）。専用 Postgres :5433 / `ai_coding_drill_test` + 専用 Redis :6380 に接続するため、`dev:all` と並行起動可。

### Workers（apps/workers/*、Go）

```bash
# 採点 Worker
mise run worker:grading:dev          # apps/workers/grading の go run
mise run worker:grading:test         # go test ./...
mise run worker:grading:lint         # golangci-lint run
mise run worker:grading:audit        # govulncheck ./...
mise run worker:grading:deps-check   # go mod tidy 後の差分チェック
mise run worker:grading:types-gen    # quicktype で Go struct 生成

# 問題生成 Worker（R7 以降、現状はスタブ）
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
```

### サンドボックスイメージ（R1 以降）

```bash
docker build -t ai-coding-drill-sandbox:latest apps/workers/grading/sandbox
```

---

## Claude Code MCP サーバー

リポジトリ root の [`.mcp.json`](.mcp.json) により、Claude Code 拡張起動時に Context7 / shadcn / next-devtools / playwright の 4 サーバーが自動接続される。初回は `npx` のダウンロードで `/mcp` が `connected` になるまで 1〜2 分かかる。詳細は [docs/requirements/5-roadmap/r0-setup/mcp-servers.md](docs/requirements/5-roadmap/r0-setup/mcp-servers.md)。

---

## ディレクトリ構成

```
apps/
├── web/                       Next.js（ADR 0036）
├── api/                       FastAPI + SQLAlchemy 2.0 + Alembic（ADR 0034 / 0037）
└── workers/
    ├── grading/               採点 Worker（Go、ADR 0016 / 0040）
    └── generation/            問題生成 Worker（Go、将来追加、ADR 0040）
infra/                         Terraform
docs/                          要件定義書（5 バケット）+ ADR + Runbook
.github/workflows/             GitHub Actions
docker-compose.yml             ローカル開発環境
mise.toml                      mise 設定（tool 版数 + タスク定義 SSoT）
lefthook.yml                   Git フック設定
commitlint.config.mjs          コミットメッセージ規約
```

詳細は [docs/requirements/2-foundation/02-architecture.md](docs/requirements/2-foundation/02-architecture.md)。

---

## ブランチ・コミット

- Trunk-based + `feature/<scope>/<short-name>`、リリースはタグ管理
- コミットは Conventional Commits 形式（`feat(api): ...` 等）、commitlint で機械検証（[ADR 0029](docs/adr/0029-commit-scope-convention.md)）
- `mise run bootstrap` で lefthook が pre-commit / commit-msg を自動セットアップ
- 詳細は [.claude/CLAUDE.md](.claude/CLAUDE.md)

---

## カスタムコマンド

`.claude/skills/` に要件駆動開発フローのコマンド一式（`/new-requirements` / `/backend-implement` / `/frontend-implement` / `/worker-implement` / `/*-test` 等）を用意。詳細は各 `SKILL.md`（[.claude/skills/](.claude/skills/)）。

---

## ライセンス

[MIT License](LICENSE) © 2026 Yohei Jinbo
