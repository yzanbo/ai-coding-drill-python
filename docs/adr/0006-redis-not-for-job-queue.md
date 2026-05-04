# 0006. Redis をジョブキュー用途では使わない（キャッシュ・セッション・レート制限のみ）

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

当初は Redis をジョブキューとしても使う想定だった。しかし [ADR 0001](./0001-postgres-as-job-queue.md) で Postgres ベースのジョブキューを採用したため、Redis の役割を再整理する必要が出た。

## Decision（決定内容）

Redis は **LLM レスポンスキャッシュ・セッション・レート制限**の 3 用途に限定する。**ジョブキュー用途では使用しない**。

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| Redis を 3 用途に限定 | キャッシュ・セッション・レート制限のみ | （採用） |
| Redis を完全廃止（Postgres で代替） | サービス削減 | キャッシュ・レート制限の高頻度アクセスでは Postgres は不向き、TTL も Redis が標準で持つ |
| Redis をジョブキューにも使う（Streams） | 統一感 | [ADR 0001](./0001-postgres-as-job-queue.md) で Postgres を選択済み、二系統に分けるメリットなし |

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
- [ADR 0001](./0001-postgres-as-job-queue.md)
