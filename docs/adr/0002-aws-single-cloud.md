# 0002. クラウドは AWS 単独に統一（マルチクラウド不採用）

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

ポートフォリオプロジェクトとしてクラウドプロバイダを 1 つに決める必要がある。

- 就活ターゲットは国内 Web 系・AI 系の中堅〜大手
- ポートフォリオで「動くこと」「設計判断ができること」を見せたい
- 月額コストは $30 以内に抑えたい（コスト目標とコンポーネント別内訳の SSoT は [01-non-functional.md: コスト](../requirements/2-foundation/01-non-functional.md#コスト)）
- マルチクラウド構成にも興味があった

## Decision（決定内容）

**AWS 単独**に統一する。マルチクラウド（GCP 併用等）は採用しない。

## Why（採用理由）

1. **求人市場での評価マジョリティ**
   - 国内 Web 系・AI 系の中堅〜大手の求人で AWS 経験は事実上の前提
   - GCP 単独は技術的には魅力的だが、ポートフォリオ評価軸では一段低く見られる傾向がある
2. **設計判断の集中投資**
   - IAM・VPC・観測性を 1 系統で深く設計でき、ポートフォリオで掘り下げて語れる
   - マルチクラウドは IAM / Terraform / CI を 2 系統に分割し、深さより広さに労力が分散する
3. **「規模に応じた選定」の体現**
   - マルチクラウドは egress コスト・運用負荷・デバッグ困難性のコストが本プロジェクト規模に対して過剰
   - 「マルチクラウドの利点を理解した上で複雑度コストが上回ると判断した」と説明可能（無秩序分散より明確に優れる）
4. **エコシステム・情報量の優位**
   - Terraform モジュール・Claude Code のサポート・公式ドキュメントが AWS で最も厚い
   - トラブル時の調査コストが最小
5. **R7 での部分併用余地は残す**
   - Vertex AI / BigQuery が必要になった場合は「その範囲だけ GCP」と限定すれば、原則と整合した拡張が可能
   - 最初から二系統に分けるより、必要箇所だけ追加する方が判断順序として健全

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| AWS 単独 | 標準・無難 | （採用） |
| GCP 単独 | Cloud Run の scale-to-zero でコスト優位 | 求人での評価が AWS より一段低い、既知度が低い |
| AWS + GCP ハイブリッド（役割分担あり） | 各クラウドの強みを使い分け | 役割分担が明確でないと「無理に複雑にした」と見られる、egress コスト発生、IAM/Terraform/CI が 2 系統 |
| AWS + GCP ハイブリッド（無秩序分散） | DB は GCP、API は AWS 等 | 設計判断の意図が薄い、最も避けるべき構成 |
| Vercel + Fly.io + Supabase 等の SaaS 寄せ集め | 各 SaaS の無料枠で運用 | クラウド選定の見せ場が薄い、IAM/IaC の練習機会が減る（コアの設計判断は AWS で行いつつ、Frontend / Redis のみ無料枠 SaaS を活用する判断は別途 [ADR 0012](./0012-upstash-redis-over-elasticache.md) / [ADR 0013](./0013-vercel-for-frontend-hosting.md) で正当化） |

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
- **「AWS 単独」の原則は維持しつつ、適合性とコスト効率の観点から個別に正当化された逸脱を 2 つ受け入れている**：Redis ホスティングの Upstash（[ADR 0012](./0012-upstash-redis-over-elasticache.md)）と Frontend ホスティングの Vercel（[ADR 0013](./0013-vercel-for-frontend-hosting.md)）。Backend API / 採点ワーカー / DB / IAM / 観測性のコア設計はすべて AWS 上で完結している

### 将来の見直しトリガー
- R7（Python 評価・分析パイプライン）で GCP の Vertex AI / BigQuery を活用したくなった場合は、その範囲だけ GCP を併用する余地を残す
- AWS の特定サービスでコストが大幅に膨らんだ場合

## References

- [02-architecture.md: クラウド](../requirements/2-foundation/02-architecture.md#クラウドaws-に確定)
- [05-runtime-stack.md: インフラ](../requirements/2-foundation/05-runtime-stack.md#インフラ)
