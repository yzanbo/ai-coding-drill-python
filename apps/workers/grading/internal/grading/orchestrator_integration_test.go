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
//
// jobHandler interface (Type / Handle / OnDead) を全て実装する。R1-5 で
// Orchestrator が generic 化した時に Type/OnDead が追加された (関連ドメイン行の
// failed 遷移をハンドラ側に委譲する責務分離)。
type fakeJobHandler struct {
	err         error
	jobType     string
	calls       int
	onDeadCalls int
}

func (f *fakeJobHandler) Type() string {
	if f.jobType != "" {
		return f.jobType
	}
	return job.TypeProblemGenerate
}

func (f *fakeJobHandler) Handle(_ context.Context, _ *job.Job) error {
	f.calls++
	return f.err
}

func (f *fakeJobHandler) OnDead(_ context.Context, _ *job.Job) {
	f.onDeadCalls++
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

	// dead 確定時に handler.OnDead が呼ばれる契約 (R1-5 で generic 化、Orchestrator は
	// 関連ドメイン行の failed 遷移をハンドラ側に委譲する)。
	// generation_requests の failed 遷移は problemGenerateHandler.OnDead の責務で、
	// 本テスト (fakeJobHandler) では OnDead の呼び出し回数だけ pin する。
	assert.Equal(t, 1, handler.onDeadCalls, "OnDead が 1 回呼ばれる")
	// generation_requests は本テストでは pending のまま (fakeJobHandler は UPDATE しない)。
	assert.Equal(t, "pending", fetchGenerationRequestStatus(t, ctx, pool, requestID))
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

	// dead 確定時に handler.OnDead が呼ばれる契約 (上記 PermanentErrorMarksDead と同じ)。
	assert.Equal(t, 1, handler.onDeadCalls, "OnDead が 1 回呼ばれる")
	_ = requestID // generation_requests への副作用は handler 責務 (本テストは pin しない)
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

// insertGradingJob: jobs テーブルに submission.grade ジョブを 1 行 INSERT (R1-5)。
// FK 制約 (submissions.user_id → users.id / submissions.problem_id → problems.id)
// を満たすため、users / problems / submissions も先に作る。
func insertGradingJob(t *testing.T, ctx context.Context, pool *pgxpool.Pool) (jobID int64, submissionID, userID, problemID uuid.UUID) {
	t.Helper()
	userID = uuid.New()
	_, err := pool.Exec(ctx, `
INSERT INTO users (id, display_name) VALUES ($1, 'test-user')`, userID)
	require.NoError(t, err)

	problemID = uuid.New()
	_, err = pool.Exec(ctx, `
INSERT INTO problems (id, title, description, category, difficulty, language,
                      examples, test_cases, reference_solution, judge_scores)
VALUES ($1, 't', 'd', 'array', 'easy', 'typescript',
        '[]'::jsonb,
        '[{"input":[1],"expected":1}]'::jsonb,
        'export const solve = (n) => n;',
        '{}'::jsonb)`, problemID)
	require.NoError(t, err)

	submissionID = uuid.New()
	_, err = pool.Exec(ctx, `
INSERT INTO submissions (id, user_id, problem_id, code, status)
VALUES ($1, $2, $3, 'export const solve = (n) => n;', 'pending')`, submissionID, userID, problemID)
	require.NoError(t, err)

	payload, err := json.Marshal(jobtypes.GradingJobPayload{
		SubmissionID: submissionID.String(),
		UserID:       userID.String(),
		ProblemID:    problemID.String(),
		Code:         "export const solve = (n) => n;",
	})
	require.NoError(t, err)

	err = pool.QueryRow(ctx, `
INSERT INTO jobs (queue, type, payload, state, attempts, run_at)
VALUES ($1, $2, $3::jsonb, 'queued', 0, NOW() - interval '1 second')
RETURNING id`, job.GradingQueue, job.TypeSubmissionGrade, payload).Scan(&jobID)
	require.NoError(t, err)
	return jobID, submissionID, userID, problemID
}

// fetchSubmissionStatus: submissions 行の status を取って返す (R1-5)。
func fetchSubmissionStatus(t *testing.T, ctx context.Context, pool *pgxpool.Pool, submissionID uuid.UUID) string {
	t.Helper()
	var status string
	err := pool.QueryRow(ctx, `SELECT status FROM submissions WHERE id = $1`, submissionID).Scan(&status)
	require.NoError(t, err)
	return status
}

// makeGradingTestOrchestrator: fakeJobHandler を握った採点 Orchestrator (queue=grading) を作る。
// fakeJobHandler の jobType を "submission.grade" に揃えて dispatch を通す。
func makeGradingTestOrchestrator(t *testing.T, ctx context.Context, pool *pgxpool.Pool, handler jobHandler) *Orchestrator {
	t.Helper()
	orch, err := newWithHandler(ctx, Deps{
		Pool:     pool,
		Queue:    job.GradingQueue,
		WorkerID: "test-worker-grading",
	}, handler)
	require.NoError(t, err)
	t.Cleanup(func() {
		_ = orch.Close()
	})
	return orch
}

// TestOrchestrator_GradingDispatchSucceeded:
// queue='grading' の Orchestrator が submission.grade ジョブを claim し、
// handler.Handle を呼んで MarkSucceeded まで進むことを確認 (R1-5)。
func TestOrchestrator_GradingDispatchSucceeded(t *testing.T) {
	ctx := context.Background()
	pool := testsupport.StartPostgres(t)

	handler := &fakeJobHandler{jobType: job.TypeSubmissionGrade, err: nil}
	orch := makeGradingTestOrchestrator(t, ctx, pool, handler)

	jobID, submissionID, _, _ := insertGradingJob(t, ctx, pool)

	orch.tryProcessOne(ctx)

	assert.Equal(t, 1, handler.calls, "採点ハンドラが 1 回呼ばれる")
	state, _, _ := fetchJobState(t, ctx, pool, jobID)
	assert.Equal(t, "succeeded", state, "成功なら state='succeeded'")
	// fakeJobHandler は submissions を UPDATE しないため pending のまま。
	// submissions の graded 遷移は submissionGradeHandler.Handle の責務
	// (本テストは orchestrator の dispatch / 成功経路だけ pin する)。
	assert.Equal(t, "pending", fetchSubmissionStatus(t, ctx, pool, submissionID))
}

// TestOrchestrator_GradingTypeMismatchMarksDead:
// queue=grading に何らかの事故で別 type のジョブが混入したら、
// dispatch は error を返して dead 経路に流す (orchestrator.dispatch の type 検査)。
func TestOrchestrator_GradingTypeMismatchMarksDead(t *testing.T) {
	ctx := context.Background()
	pool := testsupport.StartPostgres(t)

	// handler は submission.grade を期待するが、INSERT するジョブの type を
	// 別の値にして mismatch を作る。
	handler := &fakeJobHandler{jobType: job.TypeSubmissionGrade}
	orch := makeGradingTestOrchestrator(t, ctx, pool, handler)

	// queue=grading だが type=problem.generate のジョブを INSERT (運用事故シミュ)。
	userID := uuid.New()
	_, err := pool.Exec(ctx, `INSERT INTO users (id, display_name) VALUES ($1, 't')`, userID)
	require.NoError(t, err)
	var jobID int64
	err = pool.QueryRow(ctx, `
INSERT INTO jobs (queue, type, payload, state, attempts, run_at)
VALUES ($1, 'problem.generate', '{}'::jsonb, 'queued', 0, NOW() - interval '1 second')
RETURNING id`, job.GradingQueue).Scan(&jobID)
	require.NoError(t, err)

	orch.tryProcessOne(ctx)

	// handler は呼ばれない (dispatch の type 検査で弾かれる)。
	assert.Equal(t, 0, handler.calls, "type mismatch なら handler.Handle は呼ばない")
	state, _, _ := fetchJobState(t, ctx, pool, jobID)
	assert.Equal(t, "dead", state, "type mismatch は永続失敗扱いで即 dead")
	// OnDead は呼ばれる (orchestrator は handler を 1 個しか持たない契約)。
	assert.Equal(t, 1, handler.onDeadCalls)
}
