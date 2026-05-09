# 06. 開発フロー・品質保証

> **このドキュメントの守備範囲**：開発者の生産性と品質保証に関わる技術選定（モノレポ構成・コード品質ツール・共有型生成パイプライン・CI/CD・テストフレームワーク）。**「サービスを動かす実装技術」ではなく「開発体験を支える技術」**を扱う。
> **サービス実装技術（フロントエンド / バックエンド / 採点ワーカー / DB / LLM / サンドボックス / インフラ）**は [05-runtime-stack.md](./05-runtime-stack.md) を参照。
> **コンポーネントの責務・データフロー**は [02-architecture.md](./02-architecture.md) を参照。

---

## リポジトリ・モノレポ構成

- **Turborepo + pnpm workspaces** を採用（→ [ADR 0023](../../adr/0023-turborepo-pnpm-monorepo.md)）
  - pnpm workspaces：JS/TS パッケージの依存解決・リンク（土台）
  - Turborepo：ビルド順序・並列実行・キャッシュ・Vercel リモートキャッシュ（上層）
  - Go は `go mod`、Python（R7）は `uv` を使い、Turborepo は `package.json` script から薄く統合
- ディレクトリ構成の最終版は [ADR 0023](../../adr/0023-turborepo-pnpm-monorepo.md) を参照

---

## コード品質ツール

- **Biome**（lint + format、Rust 製で高速）を TS で書かれた全アプリ・全パッケージで統一使用（→ [ADR 0018](../../adr/0018-biome-for-tooling.md)）
  - ESLint + Prettier の組み合わせは不採用
- **TypeScript（`tsc --noEmit`）** で型チェック（Biome は型チェックを行わないため必須）
- 補完ツール（**R0 / リポジトリ初期セットアップ時から導入**、→ [ADR 0021](../../adr/0021-r0-tooling-discipline.md)）：
  - **共通の根拠**：これらのツールは**途中導入のコストが線形的に膨張**する（蓄積したコードが規約違反だらけになり、後追いで全件修正する作業が発生する）。R0 で入れれば修正対象がほぼゼロ、R4 まで放置すると数百ファイル規模の整地 PR が必要になりレビュー不能。**初期導入が圧倒的に低コスト**
  - **lefthook**：Git フック管理（pre-commit で Biome / 型チェック、commit-msg で commitlint を起動）。壊れたコードが main に入る前に弾く
  - **commitlint**（Conventional Commits）：コミットメッセージ規約の機械的検証。**過去のコミット履歴は遡及修正できない**ため、最初から規約を効かせる必要がある
  - **Knip**：未使用 export / 依存 / ファイルの検出。蓄積後の一斉検出は削除可否の個別判断で時間を消費する
  - **syncpack**：モノレポ内 `package.json` のバージョン整合性を強制（→ [ADR 0024](../../adr/0024-syncpack-package-json-consistency.md)）。Turborepo + pnpm workspaces 構成で必須レベル。**バージョンずれは積もると一括修正に動作リスクが伴う**
- **Go**：`gofmt` + `golangci-lint`（→ [ADR 0019](../../adr/0019-go-code-quality.md)）
- **Python（R7）**：`ruff`（Linter + Formatter 統合）。型チェッカーは R7 着手時に決定（→ [ADR 0020](../../adr/0020-python-code-quality.md)）
- **設定ファイルの物理配置**：Layer 1（ルート直接配置）/ Layer 2（`packages/config/` 経由）の住人・判断基準・投入タイミングは [packages/config/README.md](../../../packages/config/README.md) に集約

---

## 共有型・スキーマ（JSON Schema を SSoT）

- **JSON Schema を Single Source of Truth とし、各言語向けの型を自動生成**する設計
- 配置・生成ツール候補・コミット方針（言語別）・選定理由の SSoT は [ADR 0006](../../adr/0006-json-schema-as-single-source-of-truth.md) を参照

---

## CI/CD

- **GitHub Actions**
- pre-commit（lint/format、lefthook 経由）
- Dependabot
- PR 時：lint、型チェック、テスト
- main マージ時：Docker build → ECR push → デプロイ
- Terraform plan/apply もワークフロー化

---

## テスト

- **Jest**（NestJS 標準。API・LLM パイプライン・ユニット・E2E スペック）
- Go 標準 `testing` + `testify`（採点ワーカー）
- **Playwright**（E2E）
- **ミューテーションテスト**：`stryker-js`（TS 向け、R2 以降）
- テストカバレッジ：Codecov

---

## 関連

- [05-runtime-stack.md](./05-runtime-stack.md) — サービスを動かす実装技術スタック
- [02-architecture.md](./02-architecture.md) — コンポーネントの責務・データフロー
- [ADR 0023: Turborepo + pnpm workspaces](../../adr/0023-turborepo-pnpm-monorepo.md)
- [ADR 0018: TypeScript のコード品質ツールに Biome](../../adr/0018-biome-for-tooling.md)
- [ADR 0019: Go のコード品質ツール](../../adr/0019-go-code-quality.md)
- [ADR 0020: Python のコード品質ツール](../../adr/0020-python-code-quality.md)
- [ADR 0006: JSON Schema を SSoT に](../../adr/0006-json-schema-as-single-source-of-truth.md)
- [ADR 0021: 補完ツールを R0 から導入](../../adr/0021-r0-tooling-discipline.md)
