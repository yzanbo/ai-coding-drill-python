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

func TestMarkGenerationRequestCompleted_NotFoundReturnsError(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	err := markGenerationRequestCompleted(ctx, pool, uuid.New(), uuid.New())
	require.Error(t, err)
	assert.Contains(t, err.Error(), "not found")
}

func TestMarkGenerationRequestFailed_SetsStatusFailed(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	userID := testsupport.InsertTestUser(t, pool)
	reqID := insertGenerationRequest(t, ctx, pool, userID)

	err := markGenerationRequestFailed(ctx, pool, reqID)
	require.NoError(t, err)

	var status string
	err = pool.QueryRow(ctx, `SELECT status FROM generation_requests WHERE id = $1`, reqID).Scan(&status)
	require.NoError(t, err)
	assert.Equal(t, "failed", status)
}

func TestMarkGenerationRequestFailed_NotFoundReturnsError(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	err := markGenerationRequestFailed(ctx, pool, uuid.New())
	require.Error(t, err)
	assert.Contains(t, err.Error(), "not found")
}
