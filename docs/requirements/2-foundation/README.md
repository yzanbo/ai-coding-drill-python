# 2-foundation/

**変更頻度：小**（アーキテクチャ刷新時のみ大きく更新、それ以外は微調整）

---

## このディレクトリの役割

プロジェクトの**変わりにくい全体要件**を定義する。

- 非機能要件（性能・セキュリティ・コスト・可用性）
- アーキテクチャ全体構造（コンポーネント責務・データフロー）
- LLM 生成・評価パイプライン
- 観測性（ログ・トレース・メトリクス）
- 実装技術スタック（サービスを動かすランタイム技術）
- 開発フロー・品質保証技術（モノレポ・コード品質ツール・CI/CD・テスト）
- GitHub リポジトリ設定（ブランチ保護・マージ動作・Actions・Security）

機能個別の詳細・スプリント計画・ER 図・API エンドポイントは扱わない（他バケットを参照）。

---

## ファイル一覧

| # | ファイル | 内容 |
|---|---|---|
| 01 | [non-functional](./01-non-functional.md) | 性能・セキュリティ・コスト・可用性・観測性・テスト |
| 02 | [architecture](./02-architecture.md) | システム全体図・コンポーネント責務・データ/ジョブのフロー |
| 03 | [llm-pipeline](./03-llm-pipeline.md) | LLM 生成・評価パイプラインの設計、品質評価の多層防御 |
| 04 | [observability](./04-observability.md) | 観測性（ログ・トレース・メトリクス・アラート） |
| 05 | [runtime-stack](./05-runtime-stack.md) | **サービスを動かす実装技術スタック**（FE / BE / ワーカー / DB / LLM / サンドボックス / インフラ / 観測性ツール） |
| 06 | [dev-workflow](./06-dev-workflow.md) | **開発フロー・品質保証**（モノレポ / コード品質 / 共有型生成 / CI/CD / テスト） |
| 07 | [github-settings](./07-github-settings.md) | **GitHub リポジトリ設定**（ブランチ保護 Ruleset / Pull Request 動作 / Actions 権限 / Security / Features） |
| _template.md | [_template.md](./_template.md) | 新規章追加用テンプレ |

---

## 更新タイミング

- 採用技術の変更（→ 同時に [docs/adr/](../../adr/) に判断を記録）
- アーキテクチャ刷新（コンポーネント分割・責務再定義）
- 非機能要件の見直し（性能目標・コスト上限）
- 新しい観測項目の追加（ただしダッシュボード設計レベルの詳細は別文書）

---

## ファイル間の使い分け（最も重複しやすい組）

### 02 と 05（責務 vs 技術選定）

| ファイル | 担当 |
|---|---|
| **02-architecture.md** | コンポーネントの **責務** と **連携**。ライブラリ名・サービス名は書かない |
| **05-runtime-stack.md** | 各レイヤで採用する **技術名** と **選定理由**。コンポーネント責務は書かない |

### 05 と 06（ランタイム技術 vs 開発フロー技術）

| ファイル | 担当 |
|---|---|
| **05-runtime-stack.md** | **サービスを動かす技術**（NestJS / Drizzle / Postgres / LLM プロバイダ等）。エンドユーザーのリクエストを処理する |
| **06-dev-workflow.md** | **開発体験を支える技術**（Biome / Knip / lefthook / commitlint / syncpack / Jest / Playwright / GitHub Actions 等）。開発者の生産性・品質保証 |

### 06 と 07（CI 中身 vs リポジトリ設定）

| ファイル | 担当 |
|---|---|
| **06-dev-workflow.md** | **CI/CD のジョブ設計**（lint / typecheck / test 等のジョブ定義、テストフレームワーク選定）。`.github/workflows/*.yml` の中身 |
| **07-github-settings.md** | **GitHub の管理画面 / API で設定するもの**（Ruleset / Pull Request 動作 / Actions 権限 / Security / Features）。コードリポジトリには含まれず GitHub 側に保存される設定 |

詳細は [.claude/rules/requirements-docs.md](../../../.claude/rules/requirements-docs.md) を参照。

---

## 関連

- [3-cross-cutting/](../3-cross-cutting/) — 機能追加で成長する横断要件（ER 図・API 共通仕様）
- [4-features/](../4-features/) — 個別機能の詳細仕様
- [docs/adr/](../../adr/) — 技術選定・設計判断の履歴
