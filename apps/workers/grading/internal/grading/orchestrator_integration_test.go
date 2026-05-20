//go:build integration

// orchestrator_integration_test.go: Orchestrator の retry / dead 振り分けを実 Postgres で検証。
//
// 単体テスト (problem_generate_test.go) は handler 内部の error 分類を見るが、
// 「orchestrator が ErrInvalidProblem wrap を MarkFailed (= state='queued' + run_at future)、
//
//	bare error を MarkDead (= state='dead')、MaxAttempts 到達を MarkDead に流す」
//
// という end-to-end の経路は orchestrator + jobs テーブルを通さないと検証できない。
//
// fakeJobHandler を newWithHandler に差し込み、jobs を 1 件 INSERT → tryProcessOne →
// jobs 行の状態を SQL で確認する形式。
package grading

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/job"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/jobtypes"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/testsupport"
)

// fakeJobHandler: Orchestrator に差し込む jobHandler 実装。任意のエラーを返す。
type fakeJobHandler struct {
	err   error
	calls int
}

func (f *fakeJobHandler) Handle(_ context.Context, _ *job.Job) error {
	f.calls++
	return f.err
}

// insertGenerationJob: jobs テーブルに problem.generate ジョブを 1 行 INSERT。
// state='queued' / run_at は過去 (= claim 可能) / payload は最小有効値。
// FK 制約 (generation_requests.user_id → users.id) のため users も先に作る。
func insertGenerationJob(t *testing.T, ctx context.Context, pool *pgxpool.Pool, attempts int) (jobID int64, requestID uuid.UUID) {
	t.Helper()
	userID := uuid.New()
	_, err := pool.Exec(ctx, `
INSERT INTO users (id, display_name) VALUES ($1, 'test-user')`, userID)
	require.NoError(t, err)

	requestID = uuid.New()
	// generation_requests を pending で作っておく。orchestrator が dead 経路に
	// 流す時に failGenerationRequest が status='pending' で UPDATE する。
	_, err = pool.Exec(ctx, `
INSERT INTO generation_requests (id, user_id, category, difficulty, status)
VALUES ($1, $2, 'array', 'easy', 'pending')`, requestID, userID)
	require.NoError(t, err)

	payload, err := json.Marshal(jobtypes.ProblemGenerationJobPayload{
		GenerationRequestID: requestID.String(),
		Category:            "array",
		Difficulty:          "easy",
	})
	require.NoError(t, err)

	err = pool.QueryRow(ctx, `
INSERT INTO jobs (queue, type, payload, state, attempts, run_at)
VALUES ($1, $2, $3::jsonb, 'queued', $4, NOW() - interval '1 second')
RETURNING id`, job.GenerationQueue, job.TypeProblemGenerate, payload, attempts).Scan(&jobID)
	require.NoError(t, err)
	return jobID, requestID
}

// fetchJobState: jobs 行の state / attempts / run_at を取って返す。
func fetchJobState(t *testing.T, ctx context.Context, pool *pgxpool.Pool, jobID int64) (state string, attempts int, runAt time.Time) {
	t.Helper()
	err := pool.QueryRow(ctx, `SELECT state, attempts, run_at FROM jobs WHERE id = $1`, jobID).
		Scan(&state, &attempts, &runAt)
	require.NoError(t, err)
	return
}

// fetchGenerationRequestStatus: generation_requests 行の status を取って返す。
func fetchGenerationRequestStatus(t *testing.T, ctx context.Context, pool *pgxpool.Pool, requestID uuid.UUID) string {
	t.Helper()
	var status string
	err := pool.QueryRow(ctx, `SELECT status FROM generation_requests WHERE id = $1`, requestID).Scan(&status)
	require.NoError(t, err)
	return status
}

// makeTestOrchestrator: fakeJobHandler を握った Orchestrator を作る。
// listener は本物だが poll loop は呼ばずに tryProcessOne を直接叩く想定。
func makeTestOrchestrator(t *testing.T, ctx context.Context, pool *pgxpool.Pool, handler jobHandler) *Orchestrator {
	t.Helper()
	orch, err := newWithHandler(ctx, Deps{
		Pool:     pool,
		WorkerID: "test-worker",
	}, handler)
	require.NoError(t, err)
	t.Cleanup(func() {
		_ = orch.Close()
	})
	return orch
}

// TestOrchestrator_TransientErrorRequeuesWithBackoff:
// handler が ErrInvalidProblem を背負った error を返したら、jobs は
// state='queued' に戻り run_at が future にずれていることを確認。
// (= MarkFailed 経路 + backoff schedule)
func TestOrchestrator_TransientErrorRequeuesWithBackoff(t *testing.T) {
	ctx := context.Background()
	pool := testsupport.StartPostgres(t)

	handler := &fakeJobHandler{
		err: fmt.Errorf("%w: transient external error: sandbox docker hang", ErrInvalidProblem),
	}
	orch := makeTestOrchestrator(t, ctx, pool, handler)

	jobID, requestID := insertGenerationJob(t, ctx, pool, 0)

	orch.tryProcessOne(ctx)

	assert.Equal(t, 1, handler.calls, "handler が 1 回呼ばれるはず")

	state, attempts, runAt := fetchJobState(t, ctx, pool, jobID)
	assert.Equal(t, "queued", state, "transient error は state='queued' に戻る")
	assert.Equal(t, 1, attempts, "claim で attempts +1")
	assert.True(t, runAt.After(time.Now()), "run_at が future にずれているはず (backoff)")

	// generation_requests は pending のまま (retry なので failed にしない)。
	assert.Equal(t, "pending", fetchGenerationRequestStatus(t, ctx, pool, requestID))
}

// TestOrchestrator_PermanentErrorMarksDead:
// handler が bare error (= ErrInvalidProblem を背負わない) を返したら、
// jobs は state='dead' になり generation_requests も failed に。
func TestOrchestrator_PermanentErrorMarksDead(t *testing.T) {
	ctx := context.Background()
	pool := testsupport.StartPostgres(t)

	handler := &fakeJobHandler{
		err: errors.New("unauthorized: API key invalid"),
	}
	orch := makeTestOrchestrator(t, ctx, pool, handler)

	jobID, requestID := insertGenerationJob(t, ctx, pool, 0)

	orch.tryProcessOne(ctx)

	state, _, _ := fetchJobState(t, ctx, pool, jobID)
	assert.Equal(t, "dead", state, "permanent error は state='dead' に直行")

	// generation_requests は failed に遷移するはず (orchestrator.failGenerationRequest 経路)。
	assert.Equal(t, "failed", fetchGenerationRequestStatus(t, ctx, pool, requestID))
}

// TestOrchestrator_TransientErrorAtMaxAttemptsMarksDead:
// claim 時に attempts が MaxAttempts (=3) に到達したジョブで transient error が
// 出たら、IsTerminalAttempt 判定で MarkDead に流れることを確認。
// (= attempts=2 のジョブを INSERT → claim で attempts=3 → handler は ErrInvalidProblem →
//
//	IsTerminalAttempt(3)=true → MarkDead)
func TestOrchestrator_TransientErrorAtMaxAttemptsMarksDead(t *testing.T) {
	ctx := context.Background()
	pool := testsupport.StartPostgres(t)

	handler := &fakeJobHandler{
		err: fmt.Errorf("%w: still failing", ErrInvalidProblem),
	}
	orch := makeTestOrchestrator(t, ctx, pool, handler)

	// 既に 2 回 attempt 済 → claim で attempts=3 (= MaxAttempts) になる。
	jobID, requestID := insertGenerationJob(t, ctx, pool, 2)

	orch.tryProcessOne(ctx)

	state, attempts, _ := fetchJobState(t, ctx, pool, jobID)
	assert.Equal(t, "dead", state, "MaxAttempts 到達後の transient error は dead に")
	assert.Equal(t, 3, attempts, "claim で attempts +1 されて MaxAttempts に到達")

	assert.Equal(t, "failed", fetchGenerationRequestStatus(t, ctx, pool, requestID))
}

// TestOrchestrator_HandlerSuccessMarksSucceeded:
// handler が nil を返したら jobs は state='succeeded' になることを確認。
// (= retry / dead 経路に流れないことの boundary check)
func TestOrchestrator_HandlerSuccessMarksSucceeded(t *testing.T) {
	ctx := context.Background()
	pool := testsupport.StartPostgres(t)

	handler := &fakeJobHandler{err: nil}
	orch := makeTestOrchestrator(t, ctx, pool, handler)

	jobID, _ := insertGenerationJob(t, ctx, pool, 0)

	orch.tryProcessOne(ctx)

	state, _, _ := fetchJobState(t, ctx, pool, jobID)
	assert.Equal(t, "succeeded", state)
}
