# 0011. LLM プロバイダ抽象化戦略（特定モデルへの依存を排除する）

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

LLM プロバイダ・モデルを 1 つに固定するか、抽象化して差し替え可能にするかの判断。

- LLM 市場は半年単位で価格・性能・無料枠が大きく変動する（2025〜2026 にかけて Claude Haiku 4.5、Gemini 2.5 系、DeepSeek V3、GPT-4o-mini 等が相次いで登場・値下げ）
- 「今最適な選択」は数か月で陳腐化する可能性が高い
- アーキテクチャ判断は不可逆だが、モデル選択は本来可逆である
- LLM アプリの品質はモデル単体より「プロンプト × 評価 × キャッシュ戦略」で 8 割決まる
- ベンダーロックインを避けたい

## Decision（決定内容）

**特定モデル・特定ベンダーに依存しない `LlmProvider` 抽象化レイヤを最優先で設計**する。具体的なモデル選定は MVP 実装着手時に最も合理的なものを 1〜2 個選び、Phase 2 以降にベンチマークと運用ログに基づき適時更新する。

### 抽象化レイヤの責務
- 各プロバイダ API の差分吸収（Anthropic / Google / OpenAI / OpenRouter / DeepSeek 等）
- 構造化出力のスキーマバリデーション（Zod / Pydantic）
- キャッシュ層（Redis、プロバイダ非依存）
- コスト計測（入出力トークン × モデル単価で USD 換算）
- 観測性（OpenTelemetry スパン、プロバイダ・モデル名・コストをトレースに記録）
- リトライ・フォールバック（プロバイダ A 失敗時に B へ自動切替）
- プロンプトのバージョン管理（YAML、Git で履歴）

### 設定駆動の切替
プロバイダ・モデルは YAML で指定し、コード変更なしで切替できる。
```yaml
providers:
  generation:   { provider: <vendor>, model: <model-id> }
  judge:        { provider: <vendor>, model: <model-id> }
  regeneration: { provider: <vendor>, model: <model-id> }
```

### モデル選定の運用方針
- 生成と Judge は**別ベンダー・別モデル**を使う（自己評価バイアス回避）
- MVP では実装着手時に最も合理的な選定を 1〜2 個で開始
- Phase 2 以降に複数プロバイダのベンチマークを実施、結果を README に表で公開
- Phase 7 の Python 評価パイプラインで継続的にモデル比較

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| 抽象化レイヤを採用、モデル選定は実装時 | （採用） | — |
| 特定モデル（例：Claude Haiku 4.5）に固定 | シンプル | 半年で陳腐化、価格変動・新モデル登場に追従できない、ベンダーロックイン |
| LangChain / LlamaIndex の Provider 抽象を使う | 既存フレームワーク利用 | TS 版（LangChain.js）は成熟度が低い、機能過多、`GenerationModule` の責務が肥大化 |
| LiteLLM 等の LLM Gateway を導入 | OpenAI 互換プロキシ | 別サービス追加、規模に対して過剰、自前抽象化で十分 |
| プロバイダごとに別 Module を作る | NestJS 流儀 | 用途（生成・Judge・再生成）で切替したいので Module 単位は不適、`LlmProvider` インターフェースの方が直交する |

## Consequences（結果・トレードオフ）

### 得られるもの
- LLM 市場の変化に追従できる（数か月単位で最適モデルが変わっても対応可能）
- プロバイダ・モデル選定にエネルギーを使いすぎず、プロンプト・評価設計に集中できる
- ベンダーロックイン回避
- 「アーキテクチャ判断とモデル選定を分離した」という設計判断をポートフォリオで語れる
- Phase 2 以降のベンチマークが「実データに基づく選定」として README で強い説得力を持つ

### 失うもの・受容するリスク
- 抽象化レイヤの初期実装コスト（中〜高）
- 各プロバイダ固有の高機能（Anthropic Prompt Caching、Gemini Context Caching 等）を最大活用するには抽象化レイヤに専用ロジックが必要
- 構造化出力の挙動差分を吸収するロジックの保守コスト

### 将来の見直しトリガー
- 抽象化レイヤの保守コストが価値を上回った場合（特定 1 ベンダーに固定する判断もあり得る）
- LiteLLM 等の OSS Gateway が成熟し、自前抽象化を置き換えるメリットが出た場合

## References

- [03-llm-pipeline.md: モデル選定ポリシー](../requirements/2-foundation/03-llm-pipeline.md)
- [05-runtime-stack.md: LLM](../requirements/2-foundation/05-runtime-stack.md#llm)
- [ADR 0009: LLM-as-a-Judge を自前実装](./0009-custom-llm-judge.md)
- [ADR 0010: 言語の段階導入](./0010-phased-language-introduction.md)
