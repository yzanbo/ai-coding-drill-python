# 0005. Redis をジョブキュー用途では使わない（キャッシュ・セッション・レート制限のみ）

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

当初は Redis をジョブキューとしても使う想定だった。しかし [ADR 0004](./0004-postgres-as-job-queue.md) で Postgres ベースのジョブキューを採用したため、Redis の役割を再整理する必要が出た。

## Decision（決定内容）

Redis は **LLM レスポンスキャッシュ・セッション・レート制限**の 3 用途に限定する。**ジョブキュー用途では使用しない**。

## Why（採用理由）

1. **ジョブキューは Postgres に確定済み（ADR 0004）との整合**
   - ジョブの永続性・トランザクション整合性は Postgres で担保され、Redis Streams を二系統目として導入する積極的理由がない
   - 二系統に分けると Outbox パターン的な同期問題が再発するため、役割を完全分離する方が健全
2. **Redis の強みが活きる用途への限定**
   - 高頻度アクセス（キャッシュ・レート制限）と短命データ（セッション）は Postgres より Redis が明確に優位
   - 標準で TTL を持ち、`INCR` 等のアトミック操作が高速
3. **「消えても再取得可」な性質に絞ることでホスティング自由度が広がる**
   - 永続性要件が低いため、Upstash 無料枠（→ ADR 0012）など軽量な選択肢が成立
   - もし Redis 障害が起きても DB 側のデータが正であり、サービス継続が可能
4. **バックアップ戦略の単純化**
   - Redis 側のバックアップ・PITR を考慮不要にでき、運用コストが下がる
5. **完全廃止より合理的**
   - キャッシュ・レート制限を Postgres で代替すると `pg_advisory_lock` や独自 TTL 実装が必要で複雑化
   - Redis の用途を絞った状態で残す方がトータルでシンプル

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| Redis を 3 用途に限定 | キャッシュ・セッション・レート制限のみ | （採用） |
| Redis を完全廃止（Postgres で代替） | サービス削減 | キャッシュ・レート制限の高頻度アクセスでは Postgres は不向き、TTL も Redis が標準で持つ |
| Redis をジョブキューにも使う（Streams） | 統一感 | [ADR 0004](./0004-postgres-as-job-queue.md) で Postgres を選択済み、二系統に分けるメリットなし |

## Consequences（結果・トレードオフ）

### 得られるもの
- ジョブの永続性は Postgres のトランザクションで担保
- Redis は「消えても再取得可」な性質のデータだけを持つ → 無料枠サーバレス Redis（Upstash）でも十分
- バックアップ戦略が単純化（Redis は気にしなくて良い）

### 失うもの・受容するリスク
- Redis Streams で得られる Pub/Sub 機能を使えない（必要になれば NATS JetStream へ）

### 将来の見直しトリガー
- リアルタイム通知（WebSocket / SSE 経由のイベント配信）が必要になった場合は Redis Pub/Sub または NATS を検討

## References

- [02-architecture.md: データストア](../requirements/2-foundation/02-architecture.md#データストア)
- [05-runtime-stack.md: キャッシュ / セッション](../requirements/2-foundation/05-runtime-stack.md#キャッシュ--セッション)
- [ADR 0004](./0004-postgres-as-job-queue.md)
