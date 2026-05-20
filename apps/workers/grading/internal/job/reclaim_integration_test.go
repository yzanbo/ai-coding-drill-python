//go:build integration

// reclaim_integration_test.go: locked_at が古い running ジョブを queued に
// 戻すことを実 Postgres で検証。attempts は維持される (claim 時の +1 のまま
// 復帰)。
package job_test

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/job"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/testsupport"
)

func TestReclaimStuck_OldLockedReturnsToQueued(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	// locked_at = 10 分前で state='running' のジョブを 1 件作る。
	jobID := insertJob(t, ctx, pool, job.GenerationQueue, job.TypeProblemGenerate, "running", -1*time.Second)
	_, err := pool.Exec(ctx, `UPDATE jobs SET locked_at = NOW() - INTERVAL '10 minutes', locked_by = 'dead-worker', attempts = 1 WHERE id = $1`, jobID)
	require.NoError(t, err)

	// 5 分閾値で reclaim。
	ids, err := job.ReclaimStuck(ctx, pool, 5*time.Minute)
	require.NoError(t, err)
	assert.Contains(t, ids, jobID)

	var state string
	var attempts int
	var lockedAt *time.Time
	err = pool.QueryRow(ctx, `SELECT state, attempts, locked_at FROM jobs WHERE id = $1`, jobID).Scan(&state, &attempts, &lockedAt)
	require.NoError(t, err)
	assert.Equal(t, "queued", state)
	assert.Equal(t, 1, attempts, "reclaim では attempts は維持される (= 1 のまま復帰)")
	assert.Nil(t, lockedAt, "locked_at が NULL に戻る")
}

func TestReclaimStuck_RecentLockNotReclaimed(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	// locked_at = 1 分前 (5 分閾値より新しい)。
	jobID := insertJob(t, ctx, pool, job.GenerationQueue, job.TypeProblemGenerate, "running", -1*time.Second)
	_, err := pool.Exec(ctx, `UPDATE jobs SET locked_at = NOW() - INTERVAL '1 minute' WHERE id = $1`, jobID)
	require.NoError(t, err)

	ids, err := job.ReclaimStuck(ctx, pool, 5*time.Minute)
	require.NoError(t, err)
	assert.Empty(t, ids, "閾値より新しい lock は reclaim されない")
}

func TestReclaimStuck_NotRunningStateUnchanged(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	// state='queued' は対象外。
	_ = insertJob(t, ctx, pool, job.GenerationQueue, job.TypeProblemGenerate, "queued", -1*time.Second)

	ids, err := job.ReclaimStuck(ctx, pool, 1*time.Millisecond)
	require.NoError(t, err)
	assert.Empty(t, ids, "state='queued' のジョブは reclaim されない")
}
