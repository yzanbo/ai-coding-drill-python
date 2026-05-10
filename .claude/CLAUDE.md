# CLAUDE.md

このファイルは、Claude Code (claude.ai/code) がこのリポジトリで作業する際のガイダンスを提供します。

---

## 思考モード

常にultrathinkモードで応答すること（git操作を除く）。

---

## プロジェクト概要

**AI Coding Drill** は、LLM が自動生成したプログラミング問題をサンドボックス環境で検証・採点する学習サイト。
ポートフォリオ用途で「LLM の出力を信用せず、サンドボックスで動作保証する」設計思想を実装している。

中級プログラマ（GitHub アカウント所有層）向けに、TypeScript の練習問題を無限に提供する。

## 技術スタック（モノレポ）

| ディレクトリ | 役割 | 言語 |
|---|---|---|
| `apps/web/` | Next.js 16+（App Router、Frontend ツーリング（Biome / Knip / syncpack / tsconfig）も同 app 配下に閉じる） | TypeScript |
| `apps/api/` | FastAPI（**認証・問題 CRUD・ジョブ enqueue のみ**、LLM 呼び出しは Worker に委譲、Pydantic SSoT） | Python |
| `apps/workers/grading/` | 採点ワーカー（Postgres ジョブ取得 + Docker サンドボックス + judge LLM 呼び出し） | Go |
| `apps/workers/generation/` | 問題生成ワーカー（Postgres ジョブ取得 + 問題生成 LLM 呼び出し、将来追加） | Go |
| `infra/` | Terraform（AWS） | HCL |
| `docs/requirements/` | 要件定義書（時系列 5 バケット：1-vision / 2-foundation / 3-cross-cutting / 4-features / 5-roadmap） | Markdown |
| `docs/adr/` | Architecture Decision Records | Markdown |

> **注**：`packages/` ディレクトリは廃止（中身が全て apps/ 配下に移動済み）：
> - **packages/shared-types/**（不採用）：共有データ型は **`apps/api/app/schemas/` の Pydantic を SSoT** とし、**境界別の 2 伝送路**（HTTP API 境界 = `apps/api/openapi.json` → Hey API、Job キュー境界 = `apps/api/job-schemas/` → quicktype `--src-lang schema`）で TS / Go に展開する（→ [ADR 0006](../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
> - **packages/config/**（廃止済み）：Frontend が単一 Next.js app（→ [ADR 0036](../docs/adr/0036-frontend-monorepo-pnpm-only.md)）のため multi-consumer 前提が成立せず、tsconfig / vitest.config.ts は `apps/web/` 直下に直接配置する
> - **packages/prompts/**（apps/workers/<name>/ に移動済み、ADR 0040）：
>   - judge プロンプト → [apps/workers/grading/prompts/judge/](../apps/workers/grading/prompts/judge/)
>   - generation プロンプト → [apps/workers/generation/prompts/generation/](../apps/workers/generation/prompts/generation/)

詳細は [SYSTEM_OVERVIEW.md](../SYSTEM_OVERVIEW.md) と [docs/requirements/2-foundation/02-architecture.md](../docs/requirements/2-foundation/02-architecture.md) を参照。

### 主要な規約

- **タスクランナー兼 tool 版数管理は `mise`**（root 起動、3 言語横断、Turborepo 不採用）（→ [ADR 0039](../docs/adr/0039-mise-for-task-runner-and-tool-versions.md)）
- **Python 側**：パッケージ管理 / 仮想環境 / lockfile / workspace は **`uv`**（→ [ADR 0035](../docs/adr/0035-uv-for-python-package-management.md)）。lint+format は **`ruff`**、型は **`pyright`**、脆弱性は **`pip-audit`**、依存衛生は **`deptry`**（→ [ADR 0020](../docs/adr/0020-python-code-quality.md)）
- **TS 側**：パッケージマネージャは **`pnpm workspaces`**（Turborepo 不採用、→ [ADR 0036](../docs/adr/0036-frontend-monorepo-pnpm-only.md)）。lint+format は **Biome**、型は `tsc --noEmit`（→ [ADR 0018](../docs/adr/0018-biome-for-tooling.md)、Frontend 用途として継続採用）
- **Go 側**：`gofmt` + `golangci-lint`（→ [ADR 0019](../docs/adr/0019-go-code-quality.md)）。依存衛生は `go mod tidy`、脆弱性は `govulncheck`（Worker 着手時）
- **バックエンド framework は FastAPI**（→ [ADR 0034](../docs/adr/0034-fastapi-for-backend.md)）
- DB は **Postgres + SQLAlchemy 2.0（async）+ Alembic**（→ [ADR 0037](../docs/adr/0037-sqlalchemy-alembic-for-database.md)、[ADR 0004](../docs/adr/0004-postgres-as-job-queue.md)）
- ジョブキューは **Postgres `SELECT FOR UPDATE SKIP LOCKED` + LISTEN/NOTIFY**（外部キューミドルウェア不使用）
- Redis は **キャッシュ・セッション・レート制限のみ**、ジョブキュー用途では使わない（→ [ADR 0005](../docs/adr/0005-redis-not-for-job-queue.md)）
- LLM プロバイダは **抽象化レイヤ経由**で呼び出し、設定で差し替え可能（→ [ADR 0007](../docs/adr/0007-llm-provider-abstraction.md)）
- 共有データ型は **`apps/api/app/schemas/` の Pydantic を SSoT** とし、**境界別の 2 伝送路**で各言語に展開（→ [ADR 0006](../docs/adr/0006-json-schema-as-single-source-of-truth.md)）：
  - **HTTP API 境界（API ⇄ Web）**：FastAPI 自動 OpenAPI 3.1（`apps/api/openapi.json`）→ Hey API で TS 型 + Zod + HTTP クライアント生成
  - **Job キュー境界（API → DB → Worker）**：Pydantic `model.model_json_schema()` で個別 JSON Schema を `apps/api/job-schemas/` に出力 → quicktype `--src-lang schema` で Go struct 生成
- **テスト**：pytest（Backend）/ Vitest + Playwright（Frontend）/ Go testing + testify（Worker）（→ [ADR 0038](../docs/adr/0038-test-frameworks.md)）

## よく使うコマンド

リポジトリルートで `mise run <task>` 形式で実行する（→ [ADR 0039](../docs/adr/0039-mise-for-task-runner-and-tool-versions.md)）。タスク定義の SSoT は `mise.toml`。代表例（実装着手後に整備、現状は ADR レベルの命名規約）：

```bash
mise install              # mise.toml の tools（Python / Node / Go / uv / pnpm）を一括インストール
docker compose up -d      # ローカル DB / Redis 起動

# タスク命名は `<scope>:<sub>:<verb>` 階層コロン形式（scope-first）

# Backend (Python / FastAPI)
mise run api:dev                  # FastAPI 開発サーバ
mise run api:test                 # pytest
mise run api:lint                 # ruff check + format
mise run api:typecheck            # pyright
mise run api:audit                # pip-audit
mise run api:deps-check           # deptry
mise run api:db-migrate           # alembic upgrade head
mise run api:openapi-export       # FastAPI から OpenAPI 3.1 を apps/api/openapi.json に書き出し（HTTP API 境界 artifact）
mise run api:job-schemas-export   # Pydantic Job payload から JSON Schema を apps/api/job-schemas/ に書き出し（Job キュー境界 artifact）

# Frontend (Next.js / TS)
mise run web:dev          # next dev
mise run web:test         # vitest
mise run web:lint         # biome check
mise run web:typecheck    # tsc --noEmit
mise run web:syncpack     # apps/web/.syncpackrc.ts に基づく自動修正
mise run web:types-gen    # Hey API で OpenAPI から TS / Zod / HTTP クライアントを生成

# Workers (Go) — apps/workers/<name>/ ごとに mise タスクを定義（ADR 0040）
mise run worker:grading:dev      # apps/workers/grading の go run
mise run worker:grading:test     # apps/workers/grading の go test
mise run worker:grading:lint     # apps/workers/grading の golangci-lint
mise run worker:generation:dev   # apps/workers/generation（将来追加）
# 横断（全 worker）
mise run worker:test             # 全 Worker の go test
mise run worker:lint             # 全 Worker の golangci-lint
mise run worker:types-gen        # quicktype --src-lang schema で apps/api/job-schemas/ から各 Worker 内に Go struct 生成

# 横断（全言語）
mise run lint             # 全言語 lint
mise run test             # 全言語 test
mise run git:clean        # マージ済みでリモートが消えたローカルブランチを掃除
```

各レイヤ固有のコマンド・規約は `.claude/rules/` 配下の各ファイルを参照。

## ローカル環境

### 起動 URL

| サービス | URL |
|---|---|
| Web | http://localhost:3000 |
| API ヘルスチェック | http://localhost:8000/healthz |
| Swagger UI（FastAPI 自動生成） | http://localhost:8000/docs |
| Redoc（FastAPI 自動生成） | http://localhost:8000/redoc |
| OpenAPI 3.1 JSON | http://localhost:8000/openapi.json |

### データベース接続

- DB 種類：PostgreSQL 16
- ホスト：`localhost:5432`
- ユーザー：`postgres`（ローカル既定、本番は別途）
- DB 名：`ai_coding_drill`
- 接続コマンド：`docker compose exec postgres psql -U postgres ai_coding_drill`
- 接続文字列例（SQLAlchemy async + asyncpg、`.env` の `DATABASE_URL` に設定）：
  - `DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/ai_coding_drill`

### Redis 接続

- ホスト：`localhost:6379`
- 接続コマンド：`docker compose exec redis redis-cli`

### 初期ログイン

GitHub OAuth のみ。ローカルでは GitHub OAuth App を別途作成し、`.env` に `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` を設定する。

## ⚠️ 絶対ルール

絶対遵守。違反は許容しない。

### サイト全体の禁止事項（commit / PR / issue / `.md` ドキュメント全てに適用）

- **`#数字` 形式の使い分け**
  - ❌ プロジェクト内部の項目参照に使わない：要件・タスク・機能等の内部 ID を「#5」のように書くと、GitHub が issue / PR #5 に自動リンクして誤誘導を招く。内部 ID は `R0-2` / `R1-3` / `F-01` 等のプレフィックス付き形式を使う
  - ✅ GitHub の issue / PR / discussion の意図的参照には使う：`#11` / `PR #10` の形式が正しい用途（自動リンク化が望ましい挙動）
- **AI 生成文言を含めない**（「Claude」「AI」「Generated with」「Co-Authored-By」等、署名・ヘッダー含む）

### Git 操作の禁止

- main で直接作業しない（必ず別ブランチを切る）
- 明示指示なしに **`git add` / `git commit` / `git push` / PR 作成** を行わない（4 操作いずれもユーザの明示指示が必須）
- 「コミットして」と明示指示された場合でも、対象は**既にステージされているファイルのみ**。未ステージ変更の自動 `git add` は行わない

### ブランチ運用

- `main` を唯一の長期ブランチとし、リリースはタグ（`v0.1.0` 等）で管理する
- 複数領域を跨ぐ作業は **ブランチ名に詰めず commit 側で表現**（例：commit `feat(api,worker): ...`）
- 日本語・スペース・シェル特殊文字・予約名（`main` / `master` / `HEAD`）を使わない

#### 新規ブランチの命名規則（下記パターンから 1 つ選ぶ）

| パターン | 用途 |
|---|---|
| `feature/web/<機能名>` | フロントエンドの機能開発 |
| `feature/api/<機能名>` | バックエンドの機能開発 |
| `feature/worker/<機能名>` | 採点ワーカーの機能開発 |
| `feature/shared/<機能名>` | 共有パッケージ（types, prompts, config）の変更 |
| `feature/infra/<機能名>` | インフラ（Terraform）の変更 |
| `fix/<scope>/<内容>` | バグ修正 |
| `refactor/<scope>/<内容>` | リファクタリング |
| `docs/<内容>` | ドキュメント変更 |
| `chore/<scope>/<内容>` | 依存関係更新等の雑務 |

### コミットメッセージ

> SSoT は [06-dev-workflow.md: コミットメッセージ規約](../docs/requirements/2-foundation/06-dev-workflow.md#コミットメッセージ規約)、機械強制は [commitlint.config.mjs](../commitlint.config.mjs)、採用根拠は [ADR 0029](../docs/adr/0029-commit-scope-convention.md)。本セクションは Claude が直接読む用の縮約版（SSoT 更新時はここも合わせて更新する）。

- 日本語で記載、commitlint で機械強制
- 形式は `<type>(<scope>): <subject>` / scope 任意 / ヘッダー 100 文字以内 / 本文 1 行 200 文字以内
- 複数領域はカンマ区切り（例：`feat(api,worker): ...`）

#### type（Conventional Commits 標準、下記から 1 つ選ぶ）

`feat` / `fix` / `docs` / `refactor` / `test` / `chore` / `ci` / `build` / `perf` / `style` / `revert`

#### scope（プロジェクト固有、下記から 1 つ以上選ぶ）

| scope | 対応領域 |
|---|---|
| `web` | apps/web |
| `api` | apps/api |
| `worker` | apps/workers/*（grading / generation 等、ADR 0040） |
| `shared` | OpenAPI / JSON Schema artifact など複数 app から参照される共有 artifact（`apps/api/openapi.json` / `apps/api/job-schemas/` 等。`packages/` は廃止済み） |
| `config` | root 直接配置の tooling 設定群（`mise.toml` / `lefthook.yml` / `commitlint.config.mjs` 等。`packages/config/` は廃止済み） |
| `infra` | infra/ |
| `docs` | docs/ |
| `db` | DB スキーマ・マイグレーション（SQLAlchemy 2.0 モデル + Alembic、→ [ADR 0037](../docs/adr/0037-sqlalchemy-alembic-for-database.md)） |
| `deps` | 依存パッケージ更新（production / github-actions、Dependabot 自動付与含む） |
| `deps-dev` | 依存パッケージ更新（devDependencies、Dependabot 自動付与） |

### PR

- 本文・見出しは日本語（見出し例：「概要」「テスト方法」）
- テスト方法は `- [ ]` チェックリスト形式
- タイトルは `type(scope): subject` 形式が望ましい

## 開発ワークフロー・カスタムコマンド

要件駆動の開発フローを採用：

```
/new-requirements → /backend-implement → /backend-test
                  → /frontend-implement → /frontend-test
                  → /worker-implement → /worker-test
```

| コマンド | 用途 |
|---|---|
| `/new-requirements` | 要件 .md を対話的に新規作成（`docs/requirements/4-features/` 配下） |
| `/update-requirements` | 要件を先に更新してから実装を修正 |
| `/verify-requirements` | 要件と実装の整合性を検証 |
| `/backend-implement` | 要件 .md を読んで FastAPI 実装 |
| `/backend-test` | バックエンドのユニットテスト生成・実行 |
| `/backend-new-module` | FastAPI モジュール（router / schema / service / repository）をスキャフォールド |
| `/frontend-implement` | 要件 .md を読んで Next.js 実装 |
| `/frontend-test` | フロントエンドのテスト生成・実行 |
| `/worker-implement` | Go 採点ワーカーの実装 |
| `/worker-test` | Go ワーカーのテスト生成・実行 |
| `/update-documents` | ユーザー / 管理者マニュアルを生成・更新（HTML + PDF） |
| `/verify-documents` | マニュアルとアプリケーションの整合性検証 |
| `/onboarding` | 新規参画者向けプロジェクト案内 |

**重要**：機能追加は必ず `docs/requirements/` の要件 .md から始める。

## ルールファイルの管理

レイヤごとのルールは `.claude/rules/` 配下に分散：

- フロントエンドに関すること → `.claude/rules/frontend.md`
- バックエンド（FastAPI / Python）に関すること → `.claude/rules/backend.md`
- 採点ワーカー（Go）に関すること → `.claude/rules/worker.md`
- SQLAlchemy / Alembic スキーマ・マイグレーションに関すること → `.claude/rules/alembic-sqlalchemy.md`
- LLM プロンプトに関すること → `.claude/rules/prompts.md`
- 要件定義書（base）の編集ルール → `.claude/rules/docs-rules.md`
- プロジェクト全体に関することはこのファイルに追記

## コーディング規約（全体共通）

### 後方互換性について

- 後方互換性のためのコード（deprecated 変数、re-export、shim 等）は作成しない
- 不要になったコードは削除し、影響箇所を直接修正する

### 設計原則

- **可逆な判断は遅延させる**：LLM モデル選定・Python 型チェッカー選定など、市場が変化する領域は実装着手時に決定（→ [ADR 0007](../docs/adr/0007-llm-provider-abstraction.md)、[ADR 0020](../docs/adr/0020-python-code-quality.md)）
- **YAGNI**：使うか分からない抽象化を先取りで作らない
- **拡張容易性は構造的に確保**：認証プロバイダ・LLM プロバイダ・サンドボックスランタイムは差し替え可能に
- **規模に応じた選定**：このプロジェクト規模（小〜中）に最適なツールを選ぶ。Bazel・Kafka・Nx 等の "本格派" は不採用
- **設計判断を ADR で記録**：「なぜそう決めたか」「他案は何だったか」を残す。判断が変わった時は ADR 本文を**直接書き換えて**最新状態に保つ（履歴は git log で辿れる）（→ [docs/adr/](../docs/adr/)）

### 言語・ツール非依存の規約

- ファイル名・ディレクトリ名は**ケバブケース**（例：`use-get-problems.ts`、`grading-result/`）
- コミットメッセージ・コメントは**日本語**でも英語でもよい（一貫していれば可）
- IDE の問題タブにエラー・警告があれば適宜修正する
- lint・型チェック・knip 等のコマンド実行時に警告が出たら、即時修正する（警告を放置しない）

### 設定ファイル形式の優先順位

> SSoT は [06-dev-workflow.md: 設定ファイル形式の優先順位](../docs/requirements/2-foundation/06-dev-workflow.md#設定ファイル形式の優先順位)、採用根拠は [ADR 0022](../docs/adr/0022-config-file-format-priority.md)。本セクションは Claude が直接読む用の縮約版（SSoT 更新時はここも合わせて更新する）。

ツールの設定ファイル形式は以下の優先順位で選ぶ：

**前提原則**：設定ファイルには「なぜこのルールがあるか」をインラインコメントで残す。コメントが書けない純 JSON は他形式が受容される限り採用しない。

1. **ツール強制があればそれに従う**：GitHub Actions / Dependabot / pnpm workspace は YAML 強制
2. **ツール ecosystem 慣習が確立されていればそれに従う**：Biome → `biome.jsonc` / TypeScript → `tsconfig.json` / mise → `mise.toml` / Python ecosystem → `pyproject.toml`
3. **自由選択時は以下の優先順位**：
   - **TS（`.ts`）**：ツールが型を export している場合（syncpack の `RcFile`、commitlint の `UserConfig` 等）。typo を保存時に IDE / `tsc` が即時に弾く
   - **JSONC（`.jsonc`）**：純データかつ `$schema` が IDE 補完を提供する場合
   - **JS 系（`.mjs` ＞ `.cjs` ＞ `.js`）**：TS が使えず JSONC も合わない場合の妥協（ロジック必要時 / TS loader 不在時）
   - **YAML（`.yaml`）**：ツール強制 / 慣習以外で選ぶ理由は無い
   - **純 JSON（`.json`）**：ツールが他形式を一切受容しない場合のみ（コメント書けないため最終手段）

#### 拡張子 `.json` だが JSONC として扱われる例外ファイル

ツール ecosystem 慣習により、拡張子は `.json` でも対応ツールが JSONC として解釈するファイル群がある。**「`.json` だからコメント書けない」と誤認しない**ようリストで把握する：

| ファイル | 実態 | 読むツール |
|---|---|---|
| `tsconfig.json` | **JSONC** | TypeScript コンパイラ |
| `.vscode/settings.json` / `launch.json` / `tasks.json` | **JSONC** | VSCode |
| `package.json` / `package-lock.json` | **strict JSON**（コメント不可） | npm / pnpm / Node.js |

これらは ecosystem 慣習でファイル名が固定されており、**改名すると周辺ツールが壊れる**ため `.jsonc` 拡張子に変更しない。代わりに該当ファイル冒頭に「JSONC として扱われる」旨のコメントを残して混乱を防ぐ。
