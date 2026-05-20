// repository.go: orchestrator が触る業務テーブル (problems / generation_requests) の
// 書き込み SQL を集約する。jobs テーブルの読み書きは internal/job/ の責務、
// 本ファイルは「生成成功時に何を書くか」のドメイン側 SQL。
//
// 配置: orchestrator package 内 (= internal/grading/) に置くのは、
// problem.generate handler が唯一の利用者だから。横断的に増えてきたら
// internal/repo/ 等に切り出す。
package grading

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// JudgeScoresPayload: problems.judge_scores カラムに JSONB で保存する形。
// 5 軸スコア + 合計 + 閾値 + 評価コストを 1 record で残す (運用ログ用)。
type JudgeScoresPayload struct {
	Clarity          int     `json:"clarity"`
	TestCoverage     int     `json:"test_coverage"`
	DifficultyMatch  int     `json:"difficulty_match"`
	EducationalValue int     `json:"educational_value"`
	Originality      int     `json:"originality"`
	Total            int     `json:"total"`
	Threshold        int     `json:"threshold"`
	CostUSD          float64 `json:"cost_usd"`
}

// CreatedProblem: insertProblem の戻り値。
type CreatedProblem struct {
	ID uuid.UUID
}

// insertProblem: problems テーブルへ 1 行 INSERT。
//
// 引数の役割:
//   - draft        : LLM 生成 + サンドボックス検証 + judge を通過した問題本体
//   - category/difficulty : ジョブ payload 由来 (LLM の自己申告ではなく enqueue 値)
//   - judgeScores  : judge_scores カラムに書く JSONB
//
// 戻り値: 生成された UUID (generation_requests.produced_problem_id に書き込む)。
func insertProblem(ctx context.Context, pool *pgxpool.Pool, draft *ProblemDraft, category, difficulty string, judgeScores JudgeScoresPayload) (*CreatedProblem, error) {
	examplesJSON, err := json.Marshal(draft.Examples)
	if err != nil {
		return nil, fmt.Errorf("grading: marshal examples: %w", err)
	}
	testCasesJSON, err := json.Marshal(draft.TestCases)
	if err != nil {
		return nil, fmt.Errorf("grading: marshal test cases: %w", err)
	}
	scoresJSON, err := json.Marshal(judgeScores)
	if err != nil {
		return nil, fmt.Errorf("grading: marshal judge scores: %w", err)
	}

	var id uuid.UUID
	err = pool.QueryRow(ctx, `
INSERT INTO problems
  (title, description, category, difficulty, language,
   examples, test_cases, reference_solution, judge_scores)
VALUES
  ($1, $2, $3, $4, $5, $6::jsonb, $7::jsonb, $8, $9::jsonb)
RETURNING id;
`,
		draft.Title,
		draft.Description,
		category,
		difficulty,
		"typescript",
		examplesJSON,
		testCasesJSON,
		draft.ReferenceSolution,
		scoresJSON,
	).Scan(&id)
	if err != nil {
		return nil, fmt.Errorf("grading: insert problem: %w", err)
	}
	return &CreatedProblem{ID: id}, nil
}

// markGenerationRequestCompleted: generation_requests を completed に遷移し
// produced_problem_id を埋める。Backend の GET /problems/generate/:requestId が
// この行を SELECT して返す。
func markGenerationRequestCompleted(ctx context.Context, pool *pgxpool.Pool, requestID, problemID uuid.UUID) error {
	tag, err := pool.Exec(ctx, `
UPDATE generation_requests
   SET status = 'completed',
       produced_problem_id = $2,
       updated_at = NOW()
 WHERE id = $1;
`, requestID, problemID)
	if err != nil {
		return fmt.Errorf("grading: update generation_request to completed: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return fmt.Errorf("grading: generation_request %s not found", requestID)
	}
	return nil
}

// markGenerationRequestFailed: 再生成を最大試行回数まで尽くしても作れなかった
// 場合に status='failed' に遷移する。Frontend の「生成に失敗しました」表示の
// トリガ。
func markGenerationRequestFailed(ctx context.Context, pool *pgxpool.Pool, requestID uuid.UUID) error {
	tag, err := pool.Exec(ctx, `
UPDATE generation_requests
   SET status = 'failed',
       updated_at = NOW()
 WHERE id = $1;
`, requestID)
	if err != nil {
		return fmt.Errorf("grading: update generation_request to failed: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return fmt.Errorf("grading: generation_request %s not found", requestID)
	}
	return nil
}
