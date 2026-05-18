# internal/job

## とは何か

Postgres の `jobs` テーブルに対する**キュー操作**を集めた package。具体的には「取る」「リスナーで起こされる」「スタックしたものを戻す」「完了させる」の 4 つの動作。`internal/db/` の pool を受け取って SQL を打つだけで、生の pgx 設定は持たない。

## 4 つの仕事

| ファイル想定 | 役割 |
|---|---|
| `claim.go` | `SELECT FOR UPDATE SKIP LOCKED` でジョブを 1 件取り、`state='running'` に遷移させる（[ADR 0004](../../../../docs/adr/0004-postgres-as-job-queue.md)） |
| `listener.go` | Postgres `LISTEN/NOTIFY` で「新しいジョブが入った」通知を受け取り、ポーリングと併用してレイテンシを下げる |
| `reclaim.go` | `locked_at < now() - 5 min` のレコードを `state='queued'` に戻す（プロセスダウン等で取りっぱなしになったジョブの救済） |
| `complete.go`（実装時に追加） | 成功時 `state='done'` + 結果書き戻し / 失敗時 `state='failed'` または `state='dead'`（最大試行回数超過時） |

## なぜ専用 package か

- 「pgx を使った Postgres 接続」と「queue という業務的な抽象」は層が違う
- 将来 `internal/results/` 等を追加するときも、`db/` 直下に新しい SQL を足すのではなく独立 package として横並びに置ける
- `claim → process → complete` のサイクルを 1 package で読めば理解できる

## 配送保証契約

at-least-once / 可視性タイムアウト 5 分 / 指数バックオフ 10s → 60s / 最大試行超過で `state='dead'` / handler 冪等性は Worker 責務 — 詳細は [ADR 0046](../../../../docs/adr/0046-job-queue-delivery-guarantees.md) を SSoT として参照。本 package は実装側、ADR が契約側。

## やってはいけないこと

- `SELECT ... FOR UPDATE` を `SKIP LOCKED` 無しで書く：複数 Worker でデッドロック相当の待ちが発生する（[worker-layers.md §E §10](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- ジョブペイロードのバリデーション漏れ：`internal/jobtypes/` の quicktype 生成型で受け取る（手書きの struct は使わない）
- `trace_id` を無視：jobs テーブルの `trace_context` カラムから W3C Trace Context を `internal/observability/` 経由で復元する（[ADR 0010](../../../../docs/adr/0010-w3c-trace-context-in-job-payload.md)）
- 行ロックを長く握る：状態遷移を短いトランザクションで完了し、重い処理（Docker 実行・LLM 呼び出し）は別トランザクションに分ける（[02-architecture.md ジョブキュー](../../../../docs/requirements/2-foundation/02-architecture.md)）

## 関連

- 規約 SSoT：[.claude/rules/worker.md「ジョブキュー取得」セクション](../../../../.claude/rules/worker.md)
- 配送保証 SSoT：[ADR 0046](../../../../docs/adr/0046-job-queue-delivery-guarantees.md)
- ジョブキュー設計：[ADR 0004](../../../../docs/adr/0004-postgres-as-job-queue.md)
