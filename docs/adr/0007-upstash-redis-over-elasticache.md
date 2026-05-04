# 0007. Redis ホスティングに Upstash を採用（ElastiCache 不採用）

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

[ADR 0002](./0002-aws-single-cloud.md) で AWS 単独に決めたが、Redis のホスティングを検討した結果、**Redis だけは外部 SaaS の方が合理的**と判断する局面が出た。

- Redis の用途：キャッシュ・セッション・レート制限（[ADR 0006](./0006-redis-not-for-job-queue.md)）
- 「消えても再取得可」な性質
- 想定トラフィック：数百ユーザー × 数十リクエスト/日
- コスト目標：Redis 部分で月 $0〜3

## Decision（決定内容）

**Upstash Redis** を採用。AWS 単独の方針からは一部外れるが、ホスティングのコスト効率を優先する。

## Why（採用理由）

1. **コスト目標（月 $0〜3）への適合**
   - サーバレス・リクエスト課金・無料枠で本プロジェクトのトラフィック（数百ユーザー × 数十リクエスト/日）を十分カバー
   - ElastiCache の最小構成（`cache.t4g.micro` で月 ~$10）は本用途には過剰
2. **用途と耐久性要件の一致**
   - Redis の用途は「消えても再取得可」なキャッシュ・セッション・レート制限（→ ADR 0006）
   - ElastiCache の高耐久性・マルチ AZ は本用途に対して過剰スペックで、価格に反映される
3. **運用負荷ゼロ**
   - サーバレスのためパッチ・スケール・バックアップが不要、個人プロジェクトの運用コストを最小化
   - EC2 自前ホスティングはコストは抑えられるが運用負荷とワーカー VM 同居時の障害分離が問題
4. **AWS 単一クラウド方針からの逸脱を「合理的判断」として説明可能**
   - ADR 0002 の方針からは一部外れるが、原則の機械的適用ではなくコスト効率を優先した明示的判断として README に記録できる
   - ポートフォリオで「原則と例外を区別する判断力」を語れる
5. **将来の戻り道が確保されている**
   - 無料枠超過時は ElastiCache へ移行可能で、Redis API 互換のため移行コストが低い

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| Upstash Redis | サーバレス、リクエスト課金、無料枠 | （採用） |
| ElastiCache Redis（cache.t4g.micro） | AWS 純正、AWS 単一クラウド方針に沿う | 無料枠なし、最小 ~$10/月、用途的に高耐久性は過剰 |
| EC2 上に自前 Redis | 安い | 運用負荷あり、ワーカー VM と同居させると障害分離の観点で弱い |
| Redis を使わない（Postgres で代替） | サービス削減 | キャッシュ・レート制限で Postgres は速度・TTL 機能で不利 |

## Consequences（結果・トレードオフ）

### 得られるもの
- 月 $0〜3 で運用可能、無料枠で本プロジェクトのトラフィックを十分カバー
- サーバレスで運用負荷ゼロ（パッチ・スケール・バックアップ不要）
- 「AWS 一本」を維持しつつ、コスト効率の合理的判断として一部 SaaS を採用、と README で説明可能

### 失うもの・受容するリスク
- 厳密には「AWS 一本」の方針に例外を作っている
- VPC 外の SaaS なので、ネットワーク経路は public（HTTPS over TLS、ただし Upstash REST API or TLS 接続なので安全）
- マネージド SaaS のベンダーロックインがある

### 将来の見直しトリガー
- トラフィックが増えて Upstash 無料枠を超過した場合は ElastiCache へ移行
- VPC 内に閉じ込めたいセキュリティ要件が出た場合

## References

- [02-architecture.md: キャッシュ](../requirements/2-foundation/02-architecture.md#インフラの論理配置)
- [05-runtime-stack.md: キャッシュ / セッション](../requirements/2-foundation/05-runtime-stack.md#キャッシュ--セッション)
- [ADR 0002](./0002-aws-single-cloud.md)、[ADR 0006](./0006-redis-not-for-job-queue.md)
