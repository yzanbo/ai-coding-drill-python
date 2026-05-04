# 06. 開発フロー・品質保証

> **このドキュメントの守備範囲**：開発者の生産性と品質保証に関わる技術選定（モノレポ構成・コード品質ツール・共有型生成パイプライン・CI/CD・テストフレームワーク）。**「サービスを動かす実装技術」ではなく「開発体験を支える技術」**を扱う。
> **サービス実装技術（フロントエンド / バックエンド / 採点ワーカー / DB / LLM / サンドボックス / インフラ）**は [05-runtime-stack.md](./05-runtime-stack.md) を参照。
> **コンポーネントの責務・データフロー**は [02-architecture.md](./02-architecture.md) を参照。

---

## リポジトリ・モノレポ構成

- **Turborepo + pnpm workspaces** を採用（→ [ADR 0012](../../adr/0012-turborepo-pnpm-monorepo.md)）
  - pnpm workspaces：JS/TS パッケージの依存解決・リンク（土台）
  - Turborepo：ビルド順序・並列実行・キャッシュ・Vercel リモートキャッシュ（上層）
  - Go は `go mod`、Python（R7）は `uv` を使い、Turborepo は `package.json` script から薄く統合
- ディレクトリ構成の最終版は [ADR 0012](../../adr/0012-turborepo-pnpm-monorepo.md) を参照

---

## コード品質ツール

- **Biome**（lint + format、Rust 製で高速）を TS で書かれた全アプリ・全パッケージで統一使用（→ [ADR 0013](../../adr/0013-biome-for-tooling.md)）
  - 共有設定：`packages/config/biome-config/`
  - ESLint + Prettier の組み合わせは不採用
- **TypeScript（`tsc --noEmit`）** で型チェック（Biome は型チェックを行わないため必須）
- 補完ツール（**R0 / リポジトリ初期セットアップ時から導入**、→ [ADR 0018](../../adr/0018-phase-0-tooling-discipline.md)）：
  - **共通の根拠**：これらのツールは**途中導入のコストが線形的に膨張**する（蓄積したコードが規約違反だらけになり、後追いで全件修正する作業が発生する）。R0 で入れれば修正対象がほぼゼロ、R4 まで放置すると数百ファイル規模の整地 PR が必要になりレビュー不能。**初期導入が圧倒的に低コスト**
  - **lefthook**：Git フック管理（pre-commit で Biome / 型チェック、commit-msg で commitlint を起動）。壊れたコードが main に入る前に弾く
  - **commitlint**（Conventional Commits）：コミットメッセージ規約の機械的検証。**過去のコミット履歴は遡及修正できない**ため、最初から規約を効かせる必要がある
  - **Knip**：未使用 export / 依存 / ファイルの検出。蓄積後の一斉検出は削除可否の個別判断で時間を消費する
  - **syncpack**：モノレポ内 `package.json` のバージョン整合性を強制。Turborepo + pnpm workspaces 構成で必須レベル。**バージョンずれは積もると一括修正に動作リスクが伴う**
  - 設定はすべて `packages/config/` 配下に集約し、各アプリから参照
- **Go**：`gofmt` + `golangci-lint`
- **Python（R7）**：`ruff`（Linter + Formatter 統合）

---

## 共有型・スキーマ（JSON Schema を SSoT）

- **JSON Schema を Single Source of Truth とし、各言語向けの型を自動生成**する設計（→ [ADR 0014](../../adr/0014-json-schema-as-single-source-of-truth.md)）
- 配置：`packages/shared-types/`
  - `schemas/`：JSON Schema 本体（SSoT）
  - `generated/ts/`：Zod スキーマ + TS 型（コミットする）
  - `generated/go/`：Go struct（gitignore、build 時生成）
  - `generated/python/`：Pydantic モデル（gitignore、build 時生成、R7）
- 生成ツール候補：`json-schema-to-zod`（TS）、`quicktype`（Go）、`datamodel-code-generator`（Python）
- 選定理由：3 言語間の型整合性を構造的に保証、スキーマ変更が 1 箇所で全言語追従、新言語追加コスト最小

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
- [ADR 0012: Turborepo + pnpm workspaces](../../adr/0012-turborepo-pnpm-monorepo.md)
- [ADR 0013: コード品質ツールに Biome](../../adr/0013-biome-for-tooling.md)
- [ADR 0014: JSON Schema を SSoT に](../../adr/0014-json-schema-as-single-source-of-truth.md)
- [ADR 0018: 補完ツールを R0 から導入](../../adr/0018-phase-0-tooling-discipline.md)
