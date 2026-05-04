# 0001. ジョブキューに Postgres `SELECT FOR UPDATE SKIP LOCKED` を採用

- **Status**: Accepted
- **Date**: 2026-04-25
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

採点ジョブと問題生成ジョブを非同期処理する仕組みが必要。

- Producer：NestJS（TypeScript）
- Consumer：採点ワーカー（Go）
- 規模：数百ジョブ/日（ポートフォリオ運用）
- 制約：TS と Go の両方からネイティブに扱える必要がある（言語ロックインを避ける）
- コスト目標：月 $0〜10 で運用したい
- 既に Postgres をアプリ DB として採用予定

## Decision（決定内容）

専用キューミドルウェアを使わず、**Postgres に `jobs` テーブルを置き、`SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` で行ロックベースのキュー**として運用する。`LISTEN/NOTIFY` + 30 秒間隔の低頻度ポーリングのハイブリッドで取得する。

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| Redis Streams + Consumer Group | Redis ベースのストリーム型キュー | PEL/XAUTOCLAIM の自前管理、遅延ジョブ未対応、Postgres と分離されると Outbox パターンが必要 |
| Redis List（LPUSH/BRPOP） | シンプル | クラッシュ耐性弱、複数ワーカー管理が手動 |
| BullMQ（Node 専用） | TS で定番 | Go から扱えない、ポリグロット要件と矛盾 |
| asynq（Go 専用） | Go で定番 | TS から扱えない |
| RabbitMQ | 枯れた AMQP ブローカー | Erlang VM、規模に対して過剰 |
| NATS JetStream | 軽量、Pub/Sub にも使える | 1 サービス追加が必要、現規模では Postgres で十分 |
| Kafka / Redpanda | 高スループット | 規模に対して大幅に過剰 |
| Inngest / Trigger.dev | マネージドジョブランナー | TS 中心で Go 連携が弱く、ポリグロット訴求が消える |
| graphile-worker | TS 専用 Postgres ベース | TS 専用 |
| River | Go 専用 Postgres ベース | Go 専用 |

## Consequences（結果・トレードオフ）

### 得られるもの
- 既存 Postgres を再利用 → インフラ追加なし、バックアップ/PITR 一元化
- 解答登録とジョブ登録を同一トランザクションで実行（Outbox パターン不要、二重書き込み問題なし）
- `pg`（Node）も `pgx`（Go）も生 SQL で操作 → ライブラリロックインなし
- `SELECT * FROM jobs WHERE state='failed'` で観測性最強
- 想定規模の 1000 倍以上のスループット余力

### 失うもの・受容するリスク
- 自前で運用作法（行ロックの短期保持、スタックジョブのリクレイム、リトライ・DLQ）を実装する必要がある
- 専用キューミドルウェアにある GUI ダッシュボードが標準では使えない
- 大規模ファンアウト・Pub/Sub には向かない

### 将来の見直しトリガー
- ジョブが日次 10 万件を超えた場合
- ファンアウト（1 ジョブから複数ワーカータイプへ配信）が必要になった場合
- → そのときは **NATS JetStream** に移行する

## References

- [02-architecture.md: ジョブキュー](../requirements/2-foundation/02-architecture.md#ジョブキューpostgres-select-for-update-skip-locked)
- [05-runtime-stack.md: ジョブキュー](../requirements/2-foundation/05-runtime-stack.md#ジョブキューpostgres-select-for-update-skip-locked)
- [01-data-model.md: jobs テーブル](../requirements/3-cross-cutting/01-data-model.md)
