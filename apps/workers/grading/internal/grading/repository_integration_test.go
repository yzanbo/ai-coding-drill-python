//go:build integration

// repository_integration_test.go: insertProblem / markGenerationRequestCompleted /
// markGenerationRequestFailed の SQL を実 Postgres で検証。
//
// 検証対象:
//   - insertProblem が problems 行を作って UUID を返す
//   - markGenerationRequestCompleted が status='completed' + produced_problem_id を書く
//   - markGenerationRequestFailed が status='failed' に遷移
//   - 該当 generation_requests が無い時は error を返す
package grading

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/testsupport"
)

// makeDraft: 最小要件を満たす ProblemDraft を作る helper。
func makeDraft() *ProblemDraft {
	return &ProblemDraft{
		Title:             "テスト問題",
		Description:       "配列の合計を返す関数を実装してください",
		Examples:          []Example{{Input: "[1,2,3]", Output: "6"}},
		TestCases:         []TestCase{{Input: []any{[]any{1, 2, 3}}, Expected: 6}},
		ReferenceSolution: "export function solve(a: number[]) { return a.reduce((s,n)=>s+n,0); }",
	}
}

// makeScores: judge 通過後の typical scores。
func makeScores() JudgeScoresPayload {
	return JudgeScoresPayload{
		Clarity:          5,
		TestCoverage:     4,
		DifficultyMatch:  5,
		EducationalValue: 4,
		Originality:      4,
		Total:            22,
		Threshold:        20,
		CostUSD:          0.001,
	}
}

// insertGenerationRequest: テスト用に generation_requests 1 行 INSERT。
func insertGenerationRequest(t *testing.T, ctx context.Context, pool *pgxpool.Pool, userID string) uuid.UUID {
	t.Helper()
	var id uuid.UUID
	err := pool.QueryRow(ctx, `
INSERT INTO generation_requests (user_id, category, difficulty)
VALUES ($1, 'array', 'easy')
RETURNING id`, userID).Scan(&id)
	require.NoError(t, err)
	return id
}

func TestInsertProblem_WritesAllFields(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	draft := makeDraft()
	scores := makeScores()
	created, err := insertProblem(ctx, pool, draft, "array", "easy", scores)
	require.NoError(t, err)
	assert.NotEqual(t, uuid.Nil, created.ID)

	// DB に書かれた内容を直接確認。
	var (
		title, description, category, difficulty, language, refSolution string
		examples, testCases, judgeScores                                []byte
	)
	err = pool.QueryRow(ctx, `
SELECT title, description, category, difficulty, language, reference_solution,
       examples, test_cases, judge_scores
  FROM problems WHERE id = $1`, created.ID).
		Scan(&title, &description, &category, &difficulty, &language, &refSolution,
			&examples, &testCases, &judgeScores)
	require.NoError(t, err)
	assert.Equal(t, "テスト問題", title)
	assert.Equal(t, "array", category)
	assert.Equal(t, "easy", difficulty)
	assert.Equal(t, "typescript", language, "language は typescript 固定")
	assert.Contains(t, string(examples), "[1,2,3]")
	assert.Contains(t, string(testCases), `"expected"`)
	// JSONB は格納時にキー間隔を正規化する (`"total": 22`)。文字数比較ではなく
	// パースして値を見る方が安定。
	assert.Contains(t, string(judgeScores), `"total"`)
	assert.Contains(t, string(judgeScores), "22")
}

func TestMarkGenerationRequestCompleted_SetsStatusAndProblemID(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	userID := testsupport.InsertTestUser(t, pool)
	reqID := insertGenerationRequest(t, ctx, pool, userID)

	// 関連 problems も作って FK 用の UUID を確保。
	created, err := insertProblem(ctx, pool, makeDraft(), "array", "easy", makeScores())
	require.NoError(t, err)

	err = markGenerationRequestCompleted(ctx, pool, reqID, created.ID)
	require.NoError(t, err)

	var status string
	var producedProblemID *uuid.UUID
	err = pool.QueryRow(ctx, `SELECT status, produced_problem_id FROM generation_requests WHERE id = $1`, reqID).
		Scan(&status, &producedProblemID)
	require.NoError(t, err)
	assert.Equal(t, "completed", status)
	require.NotNil(t, producedProblemID)
	assert.Equal(t, created.ID, *producedProblemID)
}

func TestMarkGenerationRequestCompleted_VanishedReturnsSentinel(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	err := markGenerationRequestCompleted(ctx, pool, uuid.New(), uuid.New())
	require.Error(t, err)
	// issue #83: 行不在は ErrGenerationRequestVanished sentinel に統一。
	//   handler 側で errors.Is で識別して INFO + nil 返却に倒すため、
	//   文字列マッチではなく sentinel チェックで pin する。
	assert.ErrorIs(t, err, ErrGenerationRequestVanished)
}

func TestMarkGenerationRequestFailed_SetsStatusFailed(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	userID := testsupport.InsertTestUser(t, pool)
	reqID := insertGenerationRequest(t, ctx, pool, userID)

	err := markGenerationRequestFailed(ctx, pool, reqID, "test_reason")
	require.NoError(t, err)

	// R1-7: status だけでなく failure_reason / completed_at も書かれる契約。
	var status string
	var failureReason *string
	var completedAt *time.Time
	err = pool.QueryRow(ctx,
		`SELECT status, failure_reason, completed_at FROM generation_requests WHERE id = $1`,
		reqID,
	).Scan(&status, &failureReason, &completedAt)
	require.NoError(t, err)
	assert.Equal(t, "failed", status)
	require.NotNil(t, failureReason)
	assert.Equal(t, "test_reason", *failureReason)
	assert.NotNil(t, completedAt)
}

func TestMarkGenerationRequestFailed_VanishedReturnsSentinel(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	err := markGenerationRequestFailed(ctx, pool, uuid.New(), "test_reason")
	require.Error(t, err)
	// issue #83: 行不在は ErrGenerationRequestVanished sentinel に統一。
	assert.ErrorIs(t, err, ErrGenerationRequestVanished)
}

// ----------------------------------------------------------------------------
// pgGradingStore (R1-5): GetProblemForGrading / UpdateSubmissionGraded /
//                       UpdateSubmissionFailed の SQL を実 Postgres で検証。
// ----------------------------------------------------------------------------

// insertTestProblem: テスト用の problems 行を 1 件 INSERT して id を返す。
//
//	test_cases JSONB: 引数 cases をそのまま埋め込む (シリアライズ済み JSON 文字列)。
//	deleted=true ならソフトデリート印を付ける (採点不可ケースの観測)。
func insertTestProblem(t *testing.T, ctx context.Context, pool *pgxpool.Pool, testCasesJSON string, deleted bool) uuid.UUID {
	t.Helper()
	problemID := uuid.New()
	_, err := pool.Exec(ctx, `
INSERT INTO problems (id, title, description, category, difficulty, language,
                      examples, test_cases, reference_solution, judge_scores)
VALUES ($1, 't', 'd', 'array', 'easy', 'typescript',
        '[]'::jsonb, $2::jsonb,
        'export const solve = (n) => n;',
        '{}'::jsonb)`, problemID, testCasesJSON)
	require.NoError(t, err)
	if deleted {
		_, err = pool.Exec(ctx, `UPDATE problems SET deleted_at = NOW() WHERE id = $1`, problemID)
		require.NoError(t, err)
	}
	return problemID
}

// insertTestSubmission: テスト用の submissions 行を 1 件 INSERT して id を返す。
//
//	status='pending' で作成 (Worker が UPDATE する前の状態)。
func insertTestSubmission(t *testing.T, ctx context.Context, pool *pgxpool.Pool, userID, problemID uuid.UUID) uuid.UUID {
	t.Helper()
	subID := uuid.New()
	_, err := pool.Exec(ctx, `
INSERT INTO submissions (id, user_id, problem_id, code, status)
VALUES ($1, $2, $3, 'x', 'pending')`, subID, userID, problemID)
	require.NoError(t, err)
	return subID
}

func TestPgGradingStore_GetProblemForGrading_ReturnsTestCases(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	problemID := insertTestProblem(t, ctx, pool,
		`[{"input":[1,2],"expected":3},{"input":[5],"expected":5}]`, false)

	store := newPgGradingStore(pool)
	cases, err := store.GetProblemForGrading(ctx, problemID)
	require.NoError(t, err)
	require.Len(t, cases, 2)
	assert.Equal(t, 3.0, cases[0].Expected, "1 番目の expected は 3")
	assert.Equal(t, 5.0, cases[1].Expected, "2 番目の expected は 5")
}

func TestPgGradingStore_GetProblemForGrading_NotFound(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	store := newPgGradingStore(pool)
	_, err := store.GetProblemForGrading(ctx, uuid.New())
	require.Error(t, err)
	assert.ErrorIs(t, err, ErrProblemNotFound, "存在しない id は ErrProblemNotFound")
}

func TestPgGradingStore_GetProblemForGrading_SoftDeleted(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	problemID := insertTestProblem(t, ctx, pool, `[]`, true) // deleted=true

	store := newPgGradingStore(pool)
	_, err := store.GetProblemForGrading(ctx, problemID)
	require.Error(t, err)
	assert.ErrorIs(t, err, ErrProblemNotFound, "soft delete 行は ErrProblemNotFound")
}

func TestPgGradingStore_UpdateSubmissionGraded_TransitionsPendingToGraded(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	userIDStr := testsupport.InsertTestUser(t, pool)
	userID, err := uuid.Parse(userIDStr)
	require.NoError(t, err)
	problemID := insertTestProblem(t, ctx, pool, `[]`, false)
	subID := insertTestSubmission(t, ctx, pool, userID, problemID)

	store := newPgGradingStore(pool)
	resultJSON := []byte(`{"passed":true,"durationMs":120,"testResults":[]}`)
	err = store.UpdateSubmissionGraded(ctx, subID, 5, resultJSON)
	require.NoError(t, err)

	var status string
	var score int
	var result []byte
	var gradedAt *time.Time
	err = pool.QueryRow(ctx, `
SELECT status, score, result, graded_at FROM submissions WHERE id = $1`, subID).
		Scan(&status, &score, &result, &gradedAt)
	require.NoError(t, err)
	assert.Equal(t, "graded", status)
	assert.Equal(t, 5, score)
	assert.JSONEq(t, string(resultJSON), string(result), "result JSONB がそのまま書き込まれる")
	assert.NotNil(t, gradedAt, "graded_at が埋まる")
}

func TestPgGradingStore_UpdateSubmissionGraded_AlreadyFinalizedReturnsSentinel(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	userIDStr := testsupport.InsertTestUser(t, pool)
	userID, err := uuid.Parse(userIDStr)
	require.NoError(t, err)
	problemID := insertTestProblem(t, ctx, pool, `[]`, false)
	subID := insertTestSubmission(t, ctx, pool, userID, problemID)

	// 1 回目の UPDATE で graded に遷移。
	store := newPgGradingStore(pool)
	err = store.UpdateSubmissionGraded(ctx, subID, 1, []byte(`{"passed":true,"durationMs":1,"testResults":[]}`))
	require.NoError(t, err)

	// 2 回目は status='pending' でなくなっているため 0 行 → sentinel が返る契約。
	err = store.UpdateSubmissionGraded(ctx, subID, 9, []byte(`{"passed":false,"durationMs":1,"testResults":[]}`))
	require.Error(t, err)
	assert.ErrorIs(t, err, ErrSubmissionAlreadyFinalized)
}

func TestPgGradingStore_UpdateSubmissionFailed_TransitionsPendingToFailed(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	userIDStr := testsupport.InsertTestUser(t, pool)
	userID, err := uuid.Parse(userIDStr)
	require.NoError(t, err)
	problemID := insertTestProblem(t, ctx, pool, `[]`, false)
	subID := insertTestSubmission(t, ctx, pool, userID, problemID)

	store := newPgGradingStore(pool)
	err = store.UpdateSubmissionFailed(ctx, subID)
	require.NoError(t, err)

	var status string
	var gradedAt *time.Time
	err = pool.QueryRow(ctx, `SELECT status, graded_at FROM submissions WHERE id = $1`, subID).
		Scan(&status, &gradedAt)
	require.NoError(t, err)
	assert.Equal(t, "failed", status)
	assert.NotNil(t, gradedAt, "failed 確定時刻として graded_at が埋まる")
}
