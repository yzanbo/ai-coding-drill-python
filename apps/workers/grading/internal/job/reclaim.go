// reclaim.go: state='running' のまま locked_at が古いジョブを queued に戻す。
//
// Worker プロセスダウン / OOM / Docker daemon ハング等で「ロックしたまま
// 死んだジョブ」が永遠に running のまま残るのを防ぐ。可視性タイムアウト
// (= ReclaimAfter) を過ぎたら別 Worker が再取得できるよう state='queued'
// に戻す。
//
// 配送保証契約は at-least-once: 既に半分処理されていた可能性があるため、
// orchestrator 側で「同じ generation_request_id を 2 回処理しても結果が
// 同じ」になるよう冪等性を担保する必要がある (ADR 0046)。
package job

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// sqlReclaim: locked_at が閾値より古い running ジョブを queued に戻す。
//
// attempts は claim 時に +1 済みなので reclaim ではいじらない (= 同じ値
// で復帰)。これにより MaxAttempts を超えたら dead に落ちる契約に乗る。
//
// last_error: 「reclaimed (locked_at が古いため queued に戻した)」を残して
// 運用時に追跡できるようにする。
const sqlReclaim = `
UPDATE jobs SET
  state = 'queued',
  locked_at = NULL,
  locked_by = NULL,
  last_error = 'reclaimed: locked_at older than threshold',
  updated_at = NOW()
WHERE state = 'running'
  AND locked_at < NOW() - $1::interval
RETURNING id;
`

// ReclaimStuck: 可視性タイムアウトを超えた running ジョブを queued に戻す。
//
// 引数:
//   - reclaimAfter: 閾値 (例: 5 * time.Minute)。これより古い locked_at の
//     ジョブが対象。
//
// 戻り値:
//   - reclaimed: 戻したジョブの ID (運用ログに出すため)
//   - error: SQL エラー
//
// 呼び出し頻度: orchestrator が 1 分ごと程度に呼ぶ想定 (頻繁すぎる必要は無い)。
func ReclaimStuck(ctx context.Context, pool *pgxpool.Pool, reclaimAfter time.Duration) ([]int64, error) {
	// interval パラメータは Postgres 側で "5 minutes" 形式の文字列を期待する。
	// time.Duration は "5m0s" のように Postgres が読めない形式に変換されるため、
	// 秒数を明示的に "%d seconds" で組み立てる。
	intervalStr := fmt.Sprintf("%d seconds", int64(reclaimAfter.Seconds()))
	rows, err := pool.Query(ctx, sqlReclaim, intervalStr)
	if err != nil {
		return nil, fmt.Errorf("job: reclaim stuck: %w", err)
	}
	defer rows.Close()

	var ids []int64
	for rows.Next() {
		var id int64
		if err := rows.Scan(&id); err != nil {
			return nil, fmt.Errorf("job: reclaim scan: %w", err)
		}
		ids = append(ids, id)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("job: reclaim rows: %w", err)
	}
	return ids, nil
}
