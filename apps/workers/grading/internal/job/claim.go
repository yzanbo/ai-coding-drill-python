// claim.go: jobs テーブルから 1 件取り state='running' に遷移させる SQL を発行する。
//
// 設計上の重要ポイント (詳細は .claude/rules/worker.md「ジョブ取得のパターン」):
//   - SELECT ... FOR UPDATE SKIP LOCKED で複数 Worker 同時稼働でも待ちが出ない
//   - claim は 1 トランザクション内で短時間に閉じる
//     (Docker 実行 / LLM 呼び出しのような長時間処理は別 tx で行う)
//   - attempts は claim 時に +1 してから RETURNING で返す
//     (Worker が落ちて reclaim される時は attempts は +1 のまま戻り、
//     MaxAttempts を超えたら dead に落ちる契約に乗る、ADR 0046)
package job

import (
	"context"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// sqlClaim: queue が指定値、state='queued'、run_at <= now() のジョブを 1 件
// FOR UPDATE SKIP LOCKED で取り、同一文で state='running' に UPDATE する。
//
// CTE (WITH next AS ...) でロック対象を 1 行に絞り込み、外側の UPDATE で
// 同じ行を更新する。これにより RETURNING で必要なカラムを 1 round-trip で
// 取れる。
//
// LIMIT 1 は本 PR では固定 (バッチ取得は不要、1 ジョブずつ処理する)。
const sqlClaim = `
WITH next AS (
  SELECT id FROM jobs
   WHERE queue = $1
     AND state = 'queued'
     AND run_at <= NOW()
   ORDER BY run_at
   FOR UPDATE SKIP LOCKED
   LIMIT 1
)
UPDATE jobs SET
  state = 'running',
  locked_at = NOW(),
  locked_by = $2,
  attempts = attempts + 1,
  updated_at = NOW()
WHERE id IN (SELECT id FROM next)
RETURNING id, queue, type, payload, attempts, run_at;
`

// ClaimNext: queue から処理可能なジョブを 1 件取り、state='running' にして返す。
//
// 引数:
//   - ctx:      呼び出し元の deadline / cancel
//   - pool:     internal/db.NewPool で作った pgxpool.Pool
//   - queue:    対象論理キュー名 (例: GenerationQueue = "generation")
//   - workerID: jobs.locked_by に書く識別子 (Worker プロセス名 + host)
//
// 戻り値:
//   - *Job: 取得できたジョブ。本関数を抜けた時点で DB 上は state='running'
//   - error: ジョブが 1 件も無いときは ErrNoJob を返す。それ以外は SQL エラー
//
// 副作用: jobs.attempts を +1、locked_at / locked_by / state / updated_at を更新。
func ClaimNext(ctx context.Context, pool *pgxpool.Pool, queue, workerID string) (*Job, error) {
	row := pool.QueryRow(ctx, sqlClaim, queue, workerID)
	var j Job
	if err := row.Scan(&j.ID, &j.Queue, &j.Type, &j.Payload, &j.Attempts, &j.RunAt); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil, ErrNoJob
		}
		return nil, fmt.Errorf("job: claim next: %w", err)
	}
	return &j, nil
}
