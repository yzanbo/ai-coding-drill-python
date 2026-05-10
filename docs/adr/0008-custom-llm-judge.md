# 0008. LLM-as-a-Judge を自前実装（DeepEval / Ragas に依存しない）

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

LLM が生成した問題の品質を自動評価する仕組みが必要。

- 評価軸：問題文の明確さ、テストケースの網羅性、難易度の妥当性、教育的価値、独自性
- 既存の LLM 評価フレームワーク（Ragas、DeepEval）も存在
- 評価ロジック自体がポートフォリオの差別化軸になる

## Decision（決定内容）

LLM-as-a-Judge は **採点 Worker（`apps/workers/grading/`、Go）内で自前実装**する。Judge 呼び出しは LLM プロバイダ抽象化レイヤ（→ [ADR 0007](./0007-llm-provider-abstraction.md)）経由で行い、品質評価の 4 レイヤ（決定論チェック / Judge / ユーザーシグナル / 集合的評価）を構築する。

既存フレームワークの優れた手法（DeepEval の `G-Eval` など）は**参考にする**が依存はしない。

## Why（採用理由）

1. **評価ロジック自体がポートフォリオの差別化軸**
   - 「LLM 出力をどう評価するか」の設計判断を自前実装で語れる方が、フレームワーク呼び出しコードを見せるより訴求力が高い
   - 評価軸（明確さ・網羅性・難易度・教育的価値・独自性）の設計を自分の判断として説明できる
2. **採点 Worker と同居させる方が責務が単純**
   - Judge 呼び出しは「採点の一部」であり、採点 Worker（Go）に閉じる方がジョブ境界がきれい
   - Ragas / DeepEval は Python ライブラリだが、採点 Worker は Go（→ [ADR 0034](./0034-fastapi-for-backend.md) で API は Python、Worker は Go の役割分担）。別言語の評価フレームワークを引き込むより、抽象化レイヤ経由の自前実装の方が責務が一貫する
3. **用途のミスマッチ**
   - Ragas は RAG 評価特化で問題生成評価には合わない
   - DeepEval は pytest 風 API・テストランナー統合など本件では機能過多
4. **カスタマイズの自由度が最大**
   - 4 レイヤ品質評価（決定論チェック / Judge / ユーザーシグナル / 集合的評価）を独自に組み合わせる設計に既存フレームワークは不向き
   - サンドボックス実行・ミューテーション系の決定論チェックとの統合も自前実装の方が直接的
5. **「参考にして依存しない」というハイブリッド戦略**
   - DeepEval の G-Eval 等の優れた手法は参考にできるため、自前実装でも先行研究の知見を取り込める
   - 完全な車輪の再発明ではなく、依存関係を持たずにベストプラクティスを採り入れる構造
6. **観測性スタックとの整合**
   - LangSmith / LangFuse の SaaS 観測性は、OpenTelemetry + 自前メトリクス（→ [ADR 0007](./0007-llm-provider-abstraction.md)）で代替可能

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| 採点 Worker（Go）内で自前実装 | LLM プロバイダ抽象化レイヤ経由で多軸スコアリング | （採用） |
| Ragas | RAG 評価フレームワーク（Python） | RAG 前提、問題生成評価には合わない。Worker は Go で実装するため別言語ランタイムが必要になる |
| DeepEval | LLM 評価フレームワーク（Python、pytest 風） | 本件用途では機能過多。Worker（Go）から呼ぶには別ランタイムが必要 |
| LangSmith / LangFuse | LLM 観測性 SaaS | 観測性は OpenTelemetry + 自前メトリクスで十分 |

## Consequences（結果・トレードオフ）

### 得られるもの
- 評価ロジックそのものをポートフォリオの差別化軸として語れる
- 採点ジョブの全工程（決定論チェック・Judge・スコアリング）を採点 Worker（Go）に閉じ込められる
- カスタマイズの自由度が最大

### 失うもの・受容するリスク
- Ragas / DeepEval の既存メトリクス・ユーティリティを使えない
- 評価ロジックの妥当性は自前で検証する必要がある（人間評価との相関分析を R7 で実施）

### 将来の見直しトリガー
- R7 で RAG（教材準拠の問題生成）を導入する場合は **Ragas を限定的に採用**（その場合は別ランタイム or 別 Worker を立てる前提で再評価）
- 評価軸が複雑化して自前実装の保守コストが大きくなった場合

## References

- [03-llm-pipeline.md: 品質評価の 4 レイヤ](../requirements/2-foundation/03-llm-pipeline.md)
- [05-runtime-stack.md: 品質評価まわりのツール](../requirements/2-foundation/05-runtime-stack.md#品質評価まわりのツール)
