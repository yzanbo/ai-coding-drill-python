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
| `apps/web/` | Next.js 16+（App Router、フロント専用） | TypeScript |
| `apps/api/` | NestJS API（認証・問題 CRUD・LLM 呼び出し・ジョブ投入） | TypeScript |
| `apps/grading-worker/` | 採点ワーカー（Postgres ジョブを取得して Docker で実行） | Go |
| `packages/shared-types/` | JSON Schema を SSoT、TS/Go/Python 向けに型を自動生成 | — |
| `packages/prompts/` | LLM プロンプト（YAML、バージョン管理） | — |
| `packages/config/` | Biome / TSConfig 共有設定 | — |
| `infra/` | Terraform（AWS） | HCL |
| `docs/requirements/` | 要件定義書（時系列 5 バケット：1-vision / 2-foundation / 3-cross-cutting / 4-features / 5-roadmap） | Markdown |
| `docs/adr/` | Architecture Decision Records | Markdown |

詳細は [SYSTEM_OVERVIEW.md](../SYSTEM_OVERVIEW.md) と [docs/requirements/2-foundation/02-architecture.md](../docs/requirements/2-foundation/02-architecture.md) を参照。

### 主要な規約

- パッケージマネージャは **pnpm**、モノレポは **Turborepo**（→ [ADR 0012](../docs/adr/0012-turborepo-pnpm-monorepo.md)）
- TS のリント・フォーマットは **Biome**、型チェックは `tsc --noEmit`（→ [ADR 0013](../docs/adr/0013-biome-for-tooling.md)）
- Go は `gofmt` + `golangci-lint`（→ [ADR 0013](../docs/adr/0013-biome-for-tooling.md)）
- DB は **Postgres + Drizzle ORM**（→ [ADR 0001](../docs/adr/0001-postgres-as-job-queue.md)、[ADR 0016](../docs/adr/0016-drizzle-orm-over-prisma.md)）
- ジョブキューは **Postgres `SELECT FOR UPDATE SKIP LOCKED` + LISTEN/NOTIFY**（外部キューミドルウェア不使用）
- Redis は **キャッシュ・セッション・レート制限のみ**、ジョブキュー用途では使わない（→ [ADR 0006](../docs/adr/0006-redis-not-for-job-queue.md)）
- LLM プロバイダは **抽象化レイヤ経由**で呼び出し、設定で差し替え可能（→ [ADR 0011](../docs/adr/0011-llm-provider-abstraction.md)）
- 共有データ型は **JSON Schema を SSoT** とし各言語向けに自動生成（→ [ADR 0014](../docs/adr/0014-json-schema-as-single-source-of-truth.md)）

## よく使うコマンド

リポジトリルートで実行する：

```bash
pnpm install              # 依存パッケージインストール
docker compose up -d      # ローカル DB / Redis 起動
pnpm db:migrate           # Drizzle マイグレーション
pnpm db:seed              # シードデータ投入
pnpm dev                  # 全アプリを並列起動（Turborepo）
pnpm build                # 全パッケージビルド
pnpm test                 # 全テスト実行
pnpm lint                 # Biome チェック
pnpm format               # Biome フォーマット
pnpm typecheck            # tsc --noEmit
```

個別アプリ：

```bash
pnpm --filter @ai-coding-drill/web dev
pnpm --filter @ai-coding-drill/api dev
pnpm --filter @ai-coding-drill/grading-worker dev
```

各レイヤ固有のコマンド・規約は `.claude/rules/` 配下の各ファイルを参照。

## ローカル環境

### 起動 URL

| サービス | URL |
|---|---|
| Web | http://localhost:3000 |
| API ヘルスチェック | http://localhost:3001/healthz |
| Swagger UI | http://localhost:3001/api/docs |
| Drizzle Studio | `pnpm db:studio` で起動 |

### データベース接続

- DB 種類：PostgreSQL 16
- ホスト：`localhost:5432`
- ユーザー：`postgres`（ローカル既定、本番は別途）
- DB 名：`ai_coding_drill`
- 接続コマンド：`docker compose exec postgres psql -U postgres ai_coding_drill`

### Redis 接続

- ホスト：`localhost:6379`
- 接続コマンド：`docker compose exec redis redis-cli`

### 初期ログイン

GitHub OAuth のみ。ローカルでは GitHub OAuth App を別途作成し、`.env` に `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` を設定する。

## ⚠️ Git ルール

**以下のルールは必ず守ること。違反は許容されない。**

### コミット・PR 作成時の禁止事項

- **コミットメッセージ・PR 本文に以下の文言を絶対に含めない：**
  - 「Claude」「AI」「Generated with」「Co-Authored-By」など、AI 生成を示す一切の文言
  - `🤖 Generated with [Claude Code](https://claude.com/claude-code)` のような署名
  - `Co-Authored-By: Claude` のようなヘッダー
- **main ブランチでの作業は禁止**（コミット・push 共に禁止。必ず feature ブランチを作成してから PR を作成する）

### Push・PR 作成のルール

- **ユーザーから明示的な指示がない限り、push・PR 作成は行わない**

### コミット・PR の書き方

- コミットメッセージや PR 本文は **日本語**で記載する
- PR 本文の見出し（Summary、Test plan 等）も日本語で記載する（例: 概要、テスト方法）
- 「Test plan」は「テスト方法」と記載する
- テスト方法は `- [ ]` 形式のチェックリストで記載する
- コミット対象はステージング済みのファイルのみ
- **勝手に `git add` しない** — ユーザーがステージしたファイルのみをコミットする

### ブランチ戦略：Trunk-based + フィーチャーブランチ

- `main` が唯一の長期ブランチ、本番デプロイ対象
- 機能開発は `feature/<short-name>` で作業 → PR → main にマージ
- リリースはタグ（`v0.1.0` 等）で管理、リリースブランチは作らない
- `main` への直接 push は禁止

### ブランチ命名規則

- `feature/web/<機能名>` — フロントエンドの機能開発
- `feature/api/<機能名>` — バックエンドの機能開発
- `feature/worker/<機能名>` — 採点ワーカーの機能開発
- `feature/shared/<機能名>` — 共有パッケージ（types, prompts, config）の変更
- `feature/infra/<機能名>` — インフラ（Terraform）の変更
- `fix/<scope>/<内容>` — バグ修正
- `refactor/<scope>/<内容>` — リファクタリング
- `docs/<内容>` — ドキュメント変更
- `chore/<scope>/<内容>` — 依存関係更新等の雑務

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
| `/backend-implement` | 要件 .md を読んで NestJS 実装 |
| `/backend-test` | バックエンドのユニットテスト生成・実行 |
| `/backend-new-module` | NestJS モジュールをスキャフォールド |
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
- バックエンド（NestJS API）に関すること → `.claude/rules/backend.md`
- 採点ワーカー（Go）に関すること → `.claude/rules/worker.md`
- Drizzle スキーマ・マイグレーションに関すること → `.claude/rules/drizzle.md`
- LLM プロンプトに関すること → `.claude/rules/prompts.md`
- 要件定義書（base）の編集ルール → `.claude/rules/requirements-docs.md`
- プロジェクト全体に関することはこのファイルに追記

## コーディング規約（全体共通）

### 後方互換性について

- 後方互換性のためのコード（deprecated 変数、re-export、shim 等）は作成しない
- 不要になったコードは削除し、影響箇所を直接修正する

### 設計原則

- **可逆な判断は遅延させる**：LLM モデル選定・Python 型チェッカー選定など、市場が変化する領域は実装着手時に決定（→ [ADR 0011](../docs/adr/0011-llm-provider-abstraction.md)、[ADR 0013](../docs/adr/0013-biome-for-tooling.md)）
- **YAGNI**：使うか分からない抽象化を先取りで作らない
- **拡張容易性は構造的に確保**：認証プロバイダ・LLM プロバイダ・サンドボックスランタイムは差し替え可能に
- **規模に応じた選定**：このプロジェクト規模（小〜中）に最適なツールを選ぶ。Bazel・Kafka・Nx 等の "本格派" は不採用
- **設計判断を ADR で記録**：「なぜそう決めたか」「他案は何だったか」を Append-only で残す（→ [docs/adr/](../docs/adr/)）

### 言語・ツール非依存の規約

- ファイル名・ディレクトリ名は**ケバブケース**（例：`use-get-problems.ts`、`grading-result/`）
- コミットメッセージ・コメントは**日本語**でも英語でもよい（一貫していれば可）
- IDE の問題タブにエラー・警告があれば適宜修正する
- lint・型チェック・knip 等のコマンド実行時に警告が出たら、即時修正する（警告を放置しない）
