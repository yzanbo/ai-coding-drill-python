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
	"errors"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

// dbExecutor: *pgxpool.Pool と pgx.Tx の両方が満たす最小インターフェース。
// Handler が「単発の Pool 直叩き」と「db.WithTx 内の Tx」のどちらでも同じ
// repository 関数を呼べるようにするための DI 点 (insertProblem +
// markGenerationRequestCompleted を 1 tx に閉じるため)。
type dbExecutor interface {
	Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error)
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
}

// ErrGenerationRequestAlreadyFinalized: generation_requests がすでに
// completed / failed に遷移済みで UPDATE 対象が 0 行だった時の sentinel。
// at-least-once 配送で同一ジョブが 2 回処理された場合のうち、後発側は
// この sentinel を errors.Is で判定してログのみで握り潰す。
var ErrGenerationRequestAlreadyFinalized = errors.New("grading: generation_request already finalized")

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
func insertProblem(ctx context.Context, exec dbExecutor, draft *ProblemDraft, category, difficulty string, judgeScores JudgeScoresPayload) (*CreatedProblem, error) {
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
	err = exec.QueryRow(ctx, `
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
//
// WHERE に status='pending' を入れることで、at-least-once 配送で 2 回目以降の
// 処理が「完了済 / 失敗済」の状態を上書きするのを防ぐ。0 行更新時は
// ErrGenerationRequestAlreadyFinalized を返し、呼び出し側で「行不在」と
// 「すでに finalized」を区別できるようにする (前者は実害、後者は重複処理)。
func markGenerationRequestCompleted(ctx context.Context, exec dbExecutor, requestID, problemID uuid.UUID) error {
	tag, err := exec.Exec(ctx, `
UPDATE generation_requests
   SET status = 'completed',
       produced_problem_id = $2,
       updated_at = NOW()
 WHERE id = $1
   AND status = 'pending';
`, requestID, problemID)
	if err != nil {
		return fmt.Errorf("grading: update generation_request to completed: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return finalizeMissOrAlreadyDone(ctx, exec, requestID)
	}
	return nil
}

// markGenerationRequestFailed: 再生成を最大試行回数まで尽くしても作れなかった
// 場合に status='failed' に遷移する。Frontend の「生成に失敗しました」表示の
// トリガ。
//
// WHERE に status='pending' を入れることで、すでに completed のリクエストを
// failed で塗り潰す事故を防ぐ (handler 短絡で防ぐ前段防御 + DB 側多重防御)。
func markGenerationRequestFailed(ctx context.Context, exec dbExecutor, requestID uuid.UUID) error {
	tag, err := exec.Exec(ctx, `
UPDATE generation_requests
   SET status = 'failed',
       updated_at = NOW()
 WHERE id = $1
   AND status = 'pending';
`, requestID)
	if err != nil {
		return fmt.Errorf("grading: update generation_request to failed: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return finalizeMissOrAlreadyDone(ctx, exec, requestID)
	}
	return nil
}

// finalizeMissOrAlreadyDone: status='pending' 制約付き UPDATE が 0 行を返した時の
// 後処理。「行が存在しない」と「行はあるが既に completed/failed」を区別して
// 別の error を返す。
func finalizeMissOrAlreadyDone(ctx context.Context, exec dbExecutor, requestID uuid.UUID) error {
	var status string
	err := exec.QueryRow(ctx, `SELECT status FROM generation_requests WHERE id = $1`, requestID).Scan(&status)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return fmt.Errorf("grading: generation_request %s not found", requestID)
		}
		return fmt.Errorf("grading: lookup generation_request %s: %w", requestID, err)
	}
	return fmt.Errorf("%w: id=%s status=%s", ErrGenerationRequestAlreadyFinalized, requestID, status)
}

// selectGenerationRequestStatus: 現在の status と produced_problem_id を返す。
// Handler 冒頭の冪等性チェックで「すでに completed の request を再処理しない」
// ために使う。行が無ければ pgx.ErrNoRows を返す。
func selectGenerationRequestStatus(ctx context.Context, exec dbExecutor, requestID uuid.UUID) (status string, producedProblemID *uuid.UUID, err error) {
	err = exec.QueryRow(ctx, `
SELECT status, produced_problem_id
  FROM generation_requests
 WHERE id = $1;
`, requestID).Scan(&status, &producedProblemID)
	if err != nil {
		return "", nil, err
	}
	return status, producedProblemID, nil
}
