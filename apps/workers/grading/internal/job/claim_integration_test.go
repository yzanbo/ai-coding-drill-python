//go:build integration

// claim_integration_test.go: ClaimNext の実 Postgres での挙動。
//
// 検証対象:
//   - 空キュー時に ErrNoJob を返す
//   - queued ジョブを取って state='running' + attempts +1 + locked_by を書き込む
//   - run_at が未来のジョブは取得しない
//   - 複数 worker から同時 ClaimNext しても 1 件のみ取れる (SKIP LOCKED)
package job_test

import (
	"context"
	"encoding/json"
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/job"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/testsupport"
)

// insertJob: テスト用に 1 行 jobs を INSERT する helper。
//
// runAtOffset: 現在時刻からのオフセット。0 なら NOW()、負なら過去 (取れる)、
// 正なら未来 (取れない) を意味する。Go 側 time.Now() を渡すと host /
// container のクロックスキューで NOW() <= run_at 判定が外れる場合があるため、
// Postgres 側の NOW() に対する相対値で指定する。
func insertJob(t *testing.T, ctx context.Context, pool *pgxpool.Pool, queue, typ, state string, runAtOffset time.Duration) int64 {
	t.Helper()
	payload, err := json.Marshal(map[string]any{"k": "v"})
	require.NoError(t, err)
	interval := fmt.Sprintf("%d milliseconds", runAtOffset.Milliseconds())
	var id int64
	err = pool.QueryRow(ctx, `
INSERT INTO jobs (queue, type, payload, state, run_at)
VALUES ($1, $2, $3::jsonb, $4, NOW() + $5::interval)
RETURNING id`, queue, typ, payload, state, interval).Scan(&id)
	require.NoError(t, err)
	return id
}

func TestClaimNext_EmptyQueueReturnsErrNoJob(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	got, err := job.ClaimNext(ctx, pool, job.GenerationQueue, "worker-1")
	assert.Nil(t, got)
	assert.ErrorIs(t, err, job.ErrNoJob)
}

func TestClaimNext_PicksQueuedJob(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	jobID := insertJob(t, ctx, pool, job.GenerationQueue, job.TypeProblemGenerate, "queued", -1*time.Second)

	got, err := job.ClaimNext(ctx, pool, job.GenerationQueue, "worker-1")
	require.NoError(t, err)
	require.NotNil(t, got)
	assert.Equal(t, jobID, got.ID)
	assert.Equal(t, job.GenerationQueue, got.Queue)
	assert.Equal(t, job.TypeProblemGenerate, got.Type)
	assert.Equal(t, 1, got.Attempts, "claim 時に attempts +1 されるべき")

	// DB 側状態を直接確認: state='running' / locked_by が書かれている。
	var state, lockedBy string
	err = pool.QueryRow(ctx, `SELECT state, locked_by FROM jobs WHERE id = $1`, jobID).Scan(&state, &lockedBy)
	require.NoError(t, err)
	assert.Equal(t, "running", state)
	assert.Equal(t, "worker-1", lockedBy)
}

func TestClaimNext_SkipsFutureRunAt(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	// 5 分後の run_at は今は取れないべき。
	_ = insertJob(t, ctx, pool, job.GenerationQueue, job.TypeProblemGenerate, "queued", 5*time.Minute)

	_, err := job.ClaimNext(ctx, pool, job.GenerationQueue, "worker-1")
	assert.ErrorIs(t, err, job.ErrNoJob, "run_at が未来のジョブは取れない")
}

func TestClaimNext_SkipsOtherQueue(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	_ = insertJob(t, ctx, pool, "other", "noop", "queued", -1*time.Second)

	_, err := job.ClaimNext(ctx, pool, job.GenerationQueue, "worker-1")
	assert.ErrorIs(t, err, job.ErrNoJob)
}

func TestClaimNext_SkipLockedConcurrent(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	// 1 ジョブだけ入れて 2 worker が同時に取りに行く。SKIP LOCKED の効きで
	// 1 つは取れて 1 つは ErrNoJob になる。
	_ = insertJob(t, ctx, pool, job.GenerationQueue, job.TypeProblemGenerate, "queued", -1*time.Second)

	var (
		wg      sync.WaitGroup
		results [2]error
		jobs    [2]*job.Job
	)
	for i := range 2 {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			j, err := job.ClaimNext(ctx, pool, job.GenerationQueue, "worker")
			jobs[idx] = j
			results[idx] = err
		}(i)
	}
	wg.Wait()

	// 片方は取れて (err=nil)、片方は ErrNoJob。
	successCount := 0
	noJobCount := 0
	for i := 0; i < 2; i++ {
		switch {
		case results[i] == nil && jobs[i] != nil:
			successCount++
		case results[i] != nil && results[i].Error() == job.ErrNoJob.Error():
			noJobCount++
		}
	}
	assert.Equal(t, 1, successCount, "SKIP LOCKED: 1 つだけが ジョブを取る")
	assert.Equal(t, 1, noJobCount, "もう片方は ErrNoJob")
}
