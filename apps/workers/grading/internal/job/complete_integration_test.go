//go:build integration

// complete_integration_test.go: MarkSucceeded / MarkFailed / MarkDead の state
// 遷移を実 Postgres で検証。
//
// 検証ポイント:
//   - MarkSucceeded: state='succeeded' + result JSONB + locked_* クリア
//   - MarkFailed (attempts < MaxAttempts): state='queued' + run_at が未来 + last_error
//   - MarkFailed (attempts == MaxAttempts): state='dead' に落ちる
//   - MarkDead: 即 state='dead'
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

func TestMarkSucceeded_WritesStateAndResult(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	jobID := insertJob(t, ctx, pool, job.GenerationQueue, job.TypeProblemGenerate, "running", -1*time.Second)

	err := job.MarkSucceeded(ctx, pool, jobID, map[string]any{"problem_id": "abc"})
	require.NoError(t, err)

	var state string
	var lockedBy *string
	var lastError *string
	var result []byte
	err = pool.QueryRow(ctx, `SELECT state, locked_by, last_error, result FROM jobs WHERE id = $1`, jobID).
		Scan(&state, &lockedBy, &lastError, &result)
	require.NoError(t, err)
	assert.Equal(t, "succeeded", state)
	assert.Nil(t, lockedBy, "locked_by はクリアされる")
	assert.Nil(t, lastError)
	assert.Contains(t, string(result), `"problem_id"`)
}

func TestMarkFailed_RetryUnderMaxAttempts(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	jobID := insertJob(t, ctx, pool, job.GenerationQueue, job.TypeProblemGenerate, "running", -1*time.Second)

	// attempts=1 失敗 → backoff 10s 後に state='queued' で復帰。
	err := job.MarkFailed(ctx, pool, jobID, 1, "boom")
	require.NoError(t, err)

	var state string
	var runAt time.Time
	var lastError string
	err = pool.QueryRow(ctx, `SELECT state, run_at, last_error FROM jobs WHERE id = $1`, jobID).
		Scan(&state, &runAt, &lastError)
	require.NoError(t, err)
	assert.Equal(t, "queued", state)
	assert.Equal(t, "boom", lastError)
	assert.True(t, runAt.After(time.Now().Add(8*time.Second)),
		"run_at がバックオフ分 (10s) 未来に押し戻されている: %s", runAt)
}

func TestMarkFailed_MaxAttemptsBecomesDead(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	jobID := insertJob(t, ctx, pool, job.GenerationQueue, job.TypeProblemGenerate, "running", -1*time.Second)

	// attempts=MaxAttempts(3) で失敗 → dead に落ちる。
	err := job.MarkFailed(ctx, pool, jobID, job.MaxAttempts, "exhausted")
	require.NoError(t, err)

	var state, lastError string
	err = pool.QueryRow(ctx, `SELECT state, last_error FROM jobs WHERE id = $1`, jobID).
		Scan(&state, &lastError)
	require.NoError(t, err)
	assert.Equal(t, "dead", state, "MaxAttempts 到達は dead に落ちる")
	assert.Equal(t, "exhausted", lastError)
}

func TestMarkDead_GoesDirectlyToDead(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	jobID := insertJob(t, ctx, pool, job.GenerationQueue, job.TypeProblemGenerate, "running", -1*time.Second)

	err := job.MarkDead(ctx, pool, jobID, "unauthorized")
	require.NoError(t, err)

	var state string
	err = pool.QueryRow(ctx, `SELECT state FROM jobs WHERE id = $1`, jobID).Scan(&state)
	require.NoError(t, err)
	assert.Equal(t, "dead", state)
}
