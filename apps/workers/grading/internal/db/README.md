# internal/db

## とは何か

Postgres 接続の**インフラ層**だけを担当する package。具体的には `pgx` の **接続プール**を作って配り、**トランザクション**のヘルパを提供する。「採点ジョブの取得 SQL」や「結果書き戻しの UPDATE」のような業務ロジックは置かない（→ そちらは `internal/job/`）。

## なぜ `internal/job/` と分けるか（重要）

- 「DB 接続が落ちた」と「キューが空」は**全く別のエラー**。混ぜると上位レイヤで判別が難しくなる
- Backend FastAPI 側の `apps/api/app/db/`（→ engine + AsyncSession）と責務分担が揃う
- 将来 `internal/results/` のような別ドメインを足すとき、`db/` を肥大化させずに `results → db` の依存を 1 本足すだけで済む

## 役割

- `pgxpool.New(ctx, dsn)` で接続プールを作る `NewPool(ctx, cfg) (*pgxpool.Pool, error)`
- shutdown 関数：プロセス終了時に `pool.Close()` を呼ぶ
- トランザクションのヘルパ：`WithTx(ctx, pool, func(tx pgx.Tx) error)` のような共通パターンを 1 つ提供

## 接続数の見積もり

`pgxpool.MaxConns` は **「業務 SQL で使う本数」** を指定する。LISTEN/NOTIFY 用の long-lived な接続は `internal/job/listener.go` が `pgx.ConnectConfig` で **pool の外**に 1 本確保する（pgxpool は接続を返却前提のため LISTEN 向きでない）。そのため運用上は:

- `MaxConns` = 業務クエリ並列度（≒ `WORKER_CONCURRENCY`）程度
- Postgres 側で確保すべき接続上限は **`MaxConns + 1 (listener)` 以上**

を見積もる。Worker を多数台並べる時は **「listener 接続 × Worker 台数」** が DB 側の `max_connections` に効くので、Concurrency を増やす前にここを再計算する。

## やってはいけないこと

- ここに **`SELECT FROM jobs ...`** 等のジョブテーブル SQL を書く：それは `internal/job/` の仕事（`§E §3` の逆流 NG）
- `internal/db/` から `internal/job/` を import：依存は `job → db` の一方向（[worker-layers.md §C](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- `*pgxpool.Pool` をグローバル変数に置く：必ず main.go で生成し、依存先に引数で渡す（テスト時に fake を差し込めるため）

## 関連

- 規約 SSoT：[.claude/rules/worker.md](../../../../.claude/rules/worker.md)
- ジョブテーブル定義：Backend `apps/api/app/models/`（SQLAlchemy 側で SSoT、Worker は読み書きするだけ、[ADR 0037](../../../../docs/adr/0037-sqlalchemy-alembic-for-database.md)）
- ジョブキュー設計：[ADR 0004](../../../../docs/adr/0004-postgres-as-job-queue.md)
