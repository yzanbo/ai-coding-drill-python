# Contributing

このプロジェクトをローカルで動かしたい・開発に参加したい人向けのガイド。**設計判断・要件定義書を読みたい場合は [README.md](README.md) と [docs/](docs/) を参照してください**。

---

> ⚠️ **現状の注意（2026-05 時点）**
>
> 本プロジェクトは **設計フェーズ完了 / R1 着手予定** の状態です。以下のセットアップ手順・コマンドは **R0（基盤整備）以降に動作するようになる予定** で、現時点では `apps/` `packages/` `docker-compose.yml` 等は未整備です。
>
> - **進捗は [docs/requirements/5-roadmap/01-roadmap.md](docs/requirements/5-roadmap/01-roadmap.md) を参照**
> - 設計レビュー・面接準備のために本プロジェクトを評価している場合は [README.md](README.md) を起点に閲覧してください
> - 実装着手後、本ドキュメントの手順を最新化していきます

---

## クイックスタート

### 必要ツール

| ツール | バージョン | 用途 |
|---|---|---|
| Volta | 最新 | Node.js / pnpm のバージョン管理（推奨） |
| Node.js | 22.20.0（`package.json` の `volta.node` で固定） | TS アプリ実行 |
| pnpm | 9.15.4（`package.json` の `volta.pnpm` / `packageManager` で固定） | パッケージ管理 |
| Go | 1.22+ | 採点ワーカー |
| Docker | Desktop / Engine | サンドボックス + ローカル DB |
| psql | 任意 | DB クライアント（デバッグ用） |

> **Volta を推奨する理由**：`package.json` の `volta` フィールドにより、リポジトリに `cd` した瞬間に Node / pnpm が指定バージョンへ自動切替される。手動インストールや Corepack 不要。
> Volta を使わない場合は、表のバージョンに揃えて Node / pnpm をインストールしてください（`packageManager` フィールドにより、Corepack 経由でも pnpm が固定されます）。

### Volta インストール（未導入の場合）

```bash
# macOS / Linux
curl https://get.volta.sh | bash

# シェル再起動後、リポジトリに入れば自動的に正しい Node / pnpm が使える
cd ai-coding-drill
node -v   # → v22.20.0
pnpm -v   # → 9.15.4
```

詳細は [Volta 公式ドキュメント](https://docs.volta.sh/) を参照。

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

# 3. 依存パッケージをインストール（Volta が Node / pnpm を自動切替）
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

---

## 主要な環境変数

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

---

## トラブルシューティング

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
docs/                    要件定義書（5 バケット構造）+ ADR + Runbook
.github/workflows/       GitHub Actions（CI / デプロイ）
docker-compose.yml       ローカル開発環境
turbo.jsonc              Turborepo 設定
pnpm-workspace.yaml      pnpm workspaces 設定
biome.jsonc              Biome 設定
```

詳細な構成は [docs/adr/0012-turborepo-pnpm-monorepo.md](docs/adr/0012-turborepo-pnpm-monorepo.md) を参照。

---

## 開発コマンド

### Turborepo タスク

```bash
pnpm dev                 # 全アプリ並列起動
pnpm build               # 全パッケージビルド（依存順）
pnpm test                # 全テスト実行
pnpm lint                # Biome チェック（lint + format 差分を検出）
pnpm lint:fix            # Biome 自動修正（フォーマット差分・修正可能な lint エラーを書き込み）
pnpm typecheck           # tsc --noEmit（型チェック）
```

### Git 作業の補助

```bash
pnpm g-clean             # マージ済みでリモートが消えたローカルブランチを一括削除
                         # （必要なら main へ切替・最新化）
```

`pnpm g-clean` の挙動：

1. 未コミット変更があれば中断
2. `git fetch --prune` でリモート追跡参照を整理
3. 現在ブランチがリモートで削除済み（`[gone]` 状態）なら main へ切替・`git pull --ff-only` で最新化
4. `[origin/...: gone]` 状態のローカルブランチを全列挙して `git branch -D` で削除

未 push のローカル専用ブランチや、リモートに残っているブランチは対象外（誤削除されない）。詳細は [scripts/cleanup-merged-branches.sh](scripts/cleanup-merged-branches.sh) と [ADR 0031](docs/adr/0031-github-repository-settings.md) を参照。

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

## ブランチ戦略・コミットルール

- **ブランチ戦略**：Trunk-based + フィーチャーブランチ
  - `main` が唯一の長期ブランチ
  - 機能開発は `feature/<scope>/<short-name>` で作業 → PR → main へマージ
  - リリースはタグ（`v0.1.0` 等）で管理、リリースブランチは作らない
- **コミット**：意味のある単位で commit
  - メッセージは日本語または英語、Conventional Commits 形式（`docs:`, `feat:`, `fix:`, `chore:` 等）
  - commitlint で機械的に検証（[ADR 0018](docs/adr/0018-phase-0-tooling-discipline.md)）
- **Git フック（lefthook）**：`pnpm install` 時に `prepare` script で自動セットアップ
  - **pre-commit**：ステージ済み TS/JS/JSON 系ファイルに Biome を実行、フォーマット差分は自動修正・再ステージ。lint エラー（自動修正不可）はコミットをブロック
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
| `/backend-implement` | 要件 .md を読んで NestJS 実装 |
| `/frontend-implement` | 要件 .md を読んで Next.js 実装 |
| `/worker-implement` | Go 採点ワーカーの実装 |
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
