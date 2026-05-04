# 0002. クラウドは AWS 単独に統一（マルチクラウド不採用）

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

ポートフォリオプロジェクトとしてクラウドプロバイダを 1 つに決める必要がある。

- 就活ターゲットは国内 Web 系・AI 系の中堅〜大手
- ポートフォリオで「動くこと」「設計判断ができること」を見せたい
- 月額コストは $30 以内に抑えたい
- マルチクラウド構成にも興味があった

## Decision（決定内容）

**AWS 単独**に統一する。マルチクラウド（GCP 併用等）は採用しない。

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| AWS 単独 | 標準・無難 | （採用） |
| GCP 単独 | Cloud Run の scale-to-zero でコスト優位 | 求人での評価が AWS より一段低い、既知度が低い |
| AWS + GCP ハイブリッド（役割分担あり） | 各クラウドの強みを使い分け | 役割分担が明確でないと「無理に複雑にした」と見られる、egress コスト発生、IAM/Terraform/CI が 2 系統 |
| AWS + GCP ハイブリッド（無秩序分散） | DB は GCP、API は AWS 等 | 設計判断の意図が薄い、最も避けるべき構成 |
| Vercel + Fly.io + Supabase 等の SaaS 寄せ集め | 各 SaaS の無料枠で運用 | クラウド選定の見せ場が薄い、IAM/IaC の練習機会が減る |

## Consequences（結果・トレードオフ）

### 得られるもの
- 求人需要・情報量・エコシステムでマジョリティを取れる
- IAM・VPC・観測性の設計が 1 系統に集中、深掘りしやすい
- Terraform / CI / シークレット管理が 1 系統で完結
- ポートフォリオで「規模に応じた選定判断」を語れる（マルチクラウドの利点は理解しつつ複雑度のコストが上回ると判断）

### 失うもの・受容するリスク
- GCP 固有のサービス（Cloud Run scale-to-zero、Vertex AI、BigQuery）を直接触る経験が得られない
- ベンダーロックインの一定の受容
- AWS の最小構成では Cloud Run のような完全な scale-to-zero が難しく、多少の固定費が発生

### 将来の見直しトリガー
- Phase 7（Python 評価・分析パイプライン）で GCP の Vertex AI / BigQuery を活用したくなった場合は、その範囲だけ GCP を併用する余地を残す
- AWS の特定サービスでコストが大幅に膨らんだ場合

## References

- [02-architecture.md: クラウド](../requirements/2-foundation/02-architecture.md#クラウドaws-に確定)
- [05-runtime-stack.md: インフラ](../requirements/2-foundation/05-runtime-stack.md#インフラ)
