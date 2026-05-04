# 0009. LLM-as-a-Judge を自前実装（DeepEval / Ragas に依存しない）

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

LLM が生成した問題の品質を自動評価する仕組みが必要。

- 評価軸：問題文の明確さ、テストケースの網羅性、難易度の妥当性、教育的価値、独自性
- 既存の LLM 評価フレームワーク（Ragas、DeepEval）も存在
- 評価ロジック自体がポートフォリオの差別化軸になる

## Decision（決定内容）

LLM-as-a-Judge は **NestJS の `GenerationModule` 内で自前実装**する。`stryker-js` でミューテーションテストも組み合わせ、品質評価の 4 レイヤ（決定論チェック / Judge / ユーザーシグナル / 集合的評価）を構築する。

既存フレームワークの優れた手法（DeepEval の `G-Eval` など）は**参考にする**が依存はしない。

## Why（採用理由）

1. **評価ロジック自体がポートフォリオの差別化軸**
   - 「LLM 出力をどう評価するか」の設計判断を自前実装で語れる方が、フレームワーク呼び出しコードを見せるより訴求力が高い
   - 評価軸（明確さ・網羅性・難易度・教育的価値・独自性）の設計を自分の判断として説明できる
2. **MVP の TS スタックに統一できる**
   - Ragas / DeepEval は Python 前提で、MVP に Python を持ち込むと言語の段階導入（→ ADR 0010）と矛盾
   - NestJS の `GenerationModule` 内で完結し、Phase 7 まで Python 依存を遅延できる
3. **用途のミスマッチ**
   - Ragas は RAG 評価特化で問題生成評価には合わない
   - DeepEval は pytest 風 API・テストランナー統合など本件では機能過多
4. **カスタマイズの自由度が最大**
   - 4 レイヤ品質評価（決定論チェック / Judge / ユーザーシグナル / 集合的評価）を独自に組み合わせる設計に既存フレームワークは不向き
   - `stryker-js` ミューテーションテストとの統合も自前実装の方が直接的
5. **「参考にして依存しない」というハイブリッド戦略**
   - DeepEval の G-Eval 等の優れた手法は参考にできるため、自前実装でも先行研究の知見を取り込める
   - 完全な車輪の再発明ではなく、依存関係を持たずにベストプラクティスを採り入れる構造
6. **観測性スタックとの整合**
   - LangSmith / LangFuse の SaaS 観測性は、OpenTelemetry + 自前メトリクス（→ ADR 0011）で代替可能

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| 自前実装（Sonnet で多軸スコアリング） | TS でフルコントロール | （採用） |
| Ragas | RAG 評価フレームワーク（Python） | RAG 前提、問題生成評価には合わない、Python 依存が増える |
| DeepEval | LLM 評価フレームワーク（Python、pytest 風） | Python 依存、本件用途では機能過多 |
| LangSmith / LangFuse | LLM 観測性 SaaS | 観測性は OpenTelemetry + 自前メトリクスで十分 |

## Consequences（結果・トレードオフ）

### 得られるもの
- 評価ロジックそのものをポートフォリオの差別化軸として語れる
- TS スタックに統一でき、Python 依存を Phase 7 まで遅らせられる
- カスタマイズの自由度が最大

### 失うもの・受容するリスク
- Ragas / DeepEval の既存メトリクス・ユーティリティを使えない
- 評価ロジックの妥当性は自前で検証する必要がある（人間評価との相関分析を Phase 7 で実施）

### 将来の見直しトリガー
- Phase 7 で RAG（教材準拠の問題生成）を導入する場合は **Ragas を限定的に採用**
- 評価軸が複雑化して自前実装の保守コストが大きくなった場合

## References

- [03-llm-pipeline.md: 品質評価の 4 レイヤ](../requirements/2-foundation/03-llm-pipeline.md)
- [05-runtime-stack.md: 品質評価まわりのツール](../requirements/2-foundation/05-runtime-stack.md#品質評価まわりのツール)
