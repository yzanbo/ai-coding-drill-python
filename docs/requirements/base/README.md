# 要件定義書（base）

AI Coding Drill — プログラミング学習サイト（問題自動生成 + サンドボックス検証）のポートフォリオ用要件定義。

## ドキュメント構成

| # | ファイル | 守備範囲 |
|---|---|---|
| 01 | [overview](./01_overview.md) | プロジェクト概要・ゴール・ターゲット・言語ロードマップ |
| 02 | [functional](./02_functional.md) | 機能要件（What を作るか） |
| 03 | [non_functional](./03_non_functional.md) | 非機能要件（性能・セキュリティ・コスト・可用性） |
| 04 | [architecture](./04_architecture.md) | システム全体の論理構造、コンポーネント責務、データ・ジョブの流れ |
| 05 | [llm_pipeline](./05_llm_pipeline.md) | LLM 問題生成・評価パイプライン、品質評価の多層防御 |
| 06 | [observability](./06_observability.md) | 観測性（ログ・トレース・メトリクス・アラート） |
| 07 | [tech_stack](./07_tech_stack.md) | 採用技術 + 選定理由 + ライブラリ・サービス具体名 + コスト試算 |
| 08 | [milestones](./08_milestones.md) | 開発マイルストーン・フェーズごとの完了条件 |
| 09 | [data_model](./09_data_model.md) | ER 図、テーブル定義、ジョブペイロード JSON Schema、命名規則 |
| 10 | [api_spec](./10_api_spec.md) | 主要エンドポイント、認証、エラーフォーマット、OpenAPI 方針 |

## 関連ドキュメント

- [../../adr/](../../adr/) — Architecture Decision Records（重要な設計判断の履歴）
- [../../../SYSTEM_OVERVIEW.md](../../../SYSTEM_OVERVIEW.md) — システム全体構成のサマリ

## 文書間の関係

```
[01 overview] ─ ロードマップ・ゴール
       │
       ▼
[02 functional]      [03 non_functional]
   What を作るか        どう作るか（性能・SLA）
       │                       │
       ▼                       ▼
[10 api_spec]        [04 architecture]
   外向きの仕様         コンポーネント責務・データフロー
       │                       │
       ▼                       ▼
[09 data_model]      [05 llm_pipeline]
   データ構造           LLM 設計・品質評価
                              │
                              ▼
                       [06 observability]
                          観測性
                              │
                              ▼
                        [07 tech_stack]
                       具体的な技術選定
                              │
                              ▼
                        [08 milestones]
                          開発計画
```

## 編集ルール

要件定義書を編集する際は [.claude/rules/base-requirements-docs.md](../../../.claude/rules/base-requirements-docs.md) を参照（重複記述禁止・リンク運用・守備範囲分担）。
