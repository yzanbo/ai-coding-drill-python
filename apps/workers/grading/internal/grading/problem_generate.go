// problem_generate.go: type="problem.generate" ジョブのハンドラ。
//
// フロー (docs/requirements/4-features/problem-generation.md の sequenceDiagram):
//  1. payload を ProblemGenerationJobPayload に Unmarshal
//  2. ProblemGenerator.Generate で LLM から ProblemDraft を取得
//  3. sandbox runner で reference_solution + 自動生成 spec を Vitest 実行
//     - 全テスト pass しなければ ErrInvalidProblem として再生成へ
//  4. judge.Evaluate で品質スコアを取得
//     - threshold 未満なら ErrInvalidProblem として再生成へ
//  5. problems INSERT + generation_requests を completed に遷移
//
// 「再生成」は本 PR では「jobs テーブルでバックオフ retry させる」方式で実装する。
// (= MarkFailed で run_at を未来にずらして state='queued' に戻す、ADR 0046)。
// 最大試行回数 (MaxAttempts=3) 到達で MarkDead + generation_requests を failed に。
package grading

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/job"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/jobtypes"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/judge"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/sandbox"
)

// vitestCmd: sandbox 内で実行する vitest コマンド。
// グローバルインストール済み (apps/workers/grading/sandbox/Dockerfile) なので
// PATH 解決で起動する。--reporter=json で stdout に JSON 1 オブジェクトが出る。
var vitestCmd = []string{"vitest", "run", "--reporter=json"}

// problemGenerateHandler: orchestrator が dispatch するハンドラ実装。
type problemGenerateHandler struct {
	pool      *pgxpool.Pool
	generator *ProblemGenerator
	sandbox   *sandbox.Runner
	judge     *judge.Judge
}

// Handle: 1 件のジョブを処理する。
//
// 戻り値:
//   - nil:                 成功 (problems INSERT + generation_requests completed 済み)
//   - ErrInvalidProblem を wrap した error: 再生成可能な失敗 (sandbox 不合格 or
//     judge 不合格 or LLM 出力 schema 違反)。orchestrator は MarkFailed で
//     リトライ or MaxAttempts 到達で MarkDead に流す
//   - その他 error: リトライしても直らない失敗 (LLM unauthorized, DB エラー等)
func (h *problemGenerateHandler) Handle(ctx context.Context, j *job.Job) error {
	var payload jobtypes.ProblemGenerationJobPayload
	if err := json.Unmarshal(j.Payload, &payload); err != nil {
		return fmt.Errorf("grading: unmarshal payload: %w", err)
	}
	requestID, err := uuid.Parse(payload.GenerationRequestID)
	if err != nil {
		return fmt.Errorf("grading: parse generation_request_id %q: %w", payload.GenerationRequestID, err)
	}
	category := string(payload.Category)
	difficulty := string(payload.Difficulty)

	slog.InfoContext(ctx, "problem.generate: start",
		"job_id", j.ID,
		"attempts", j.Attempts,
		"generation_request_id", requestID,
		"category", category,
		"difficulty", difficulty,
	)

	// 1. LLM 生成
	draft, err := h.generator.Generate(ctx, category, difficulty)
	if err != nil {
		return err
	}
	slog.InfoContext(ctx, "problem.generate: llm done",
		"job_id", j.ID,
		"title", draft.Title,
		"cost_usd", draft.GeneratedBy.CostUSD,
		"input_tokens", draft.GeneratedBy.InputTokens,
		"output_tokens", draft.GeneratedBy.OutputTokens,
	)

	// 2. サンドボックス検証
	if err := h.verifyInSandbox(ctx, draft); err != nil {
		return err
	}

	// 3. judge 評価
	judgeRes, err := h.evaluateQuality(ctx, draft, category, difficulty)
	if err != nil {
		return err
	}
	if !judgeRes.Passed() {
		return fmt.Errorf("%w: judge score %d below threshold %d", ErrInvalidProblem, judgeRes.Total, judgeRes.Threshold)
	}

	// 4. problems INSERT + generation_requests completed
	scores := JudgeScoresPayload{
		Clarity:          judgeRes.Clarity.Score,
		TestCoverage:     judgeRes.TestCoverage.Score,
		DifficultyMatch:  judgeRes.DifficultyMatch.Score,
		EducationalValue: judgeRes.EducationalValue.Score,
		Originality:      judgeRes.Originality.Score,
		Total:            judgeRes.Total,
		Threshold:        judgeRes.Threshold,
		CostUSD:          judgeRes.CostUSD,
	}
	created, err := insertProblem(ctx, h.pool, draft, category, difficulty, scores)
	if err != nil {
		return err
	}
	if err := markGenerationRequestCompleted(ctx, h.pool, requestID, created.ID); err != nil {
		// problems は INSERT 済み。generation_requests 側の整合性のみ崩れる。
		// このパスは「同じ generation_request_id で 2 度処理」(at-least-once、
		// reclaim 後) でも起き得るため、orchestrator 上位で冪等にリカバリ
		// できるよう error を返す。
		return err
	}
	slog.InfoContext(ctx, "problem.generate: completed",
		"job_id", j.ID,
		"problem_id", created.ID,
		"judge_total", judgeRes.Total,
	)
	return nil
}

// verifyInSandbox: reference_solution + 自動生成 spec を Vitest 実行する。
// 全テスト pass しなければ ErrInvalidProblem を wrap して返す (= 再生成へ)。
func (h *problemGenerateHandler) verifyInSandbox(ctx context.Context, draft *ProblemDraft) error {
	specBody, err := buildSpecFile(draft)
	if err != nil {
		return fmt.Errorf("%w: build spec: %v", ErrInvalidProblem, err)
	}
	res, err := h.sandbox.Run(ctx, []sandbox.FileSource{
		{Name: SolutionFileName, Content: draft.ReferenceSolution},
		{Name: SpecFileName, Content: specBody},
	}, vitestCmd)
	if err != nil {
		// Docker / 環境エラーは「リトライしても直らない可能性が高い」が、
		// MaxAttempts に到達するまでは retry でリカバリさせる (transient な
		// docker daemon hang もあるため)。Bare error は MarkFailed 経路に流す。
		return fmt.Errorf("grading: sandbox run: %w", err)
	}
	if res.TimedOut {
		return fmt.Errorf("%w: sandbox timed out", ErrInvalidProblem)
	}
	if res.ExitCode != 0 {
		// テスト失敗 (exit code 1) と vitest 起動失敗の区別は stdout の JSON
		// 有無で見る: JSON が出ていれば「テスト失敗」、出ていなければ
		// 「環境エラー」扱い。
		summary, parseErr := sandbox.ParseVitest(res.Stdout)
		if parseErr != nil {
			return fmt.Errorf("%w: vitest run failed (exit=%d, stderr=%s)", ErrInvalidProblem, res.ExitCode, truncate(res.Stderr, 200))
		}
		if !summary.AllPassed() {
			return fmt.Errorf("%w: %d/%d tests failed", ErrInvalidProblem, summary.Failed, summary.Total)
		}
	}
	// ExitCode 0 でも本当に走ったか確認 (テスト 0 件は不合格扱い)。
	summary, parseErr := sandbox.ParseVitest(res.Stdout)
	if parseErr != nil {
		return fmt.Errorf("%w: parse vitest output: %v", ErrInvalidProblem, parseErr)
	}
	if !summary.AllPassed() {
		return fmt.Errorf("%w: vitest reported %d/%d", ErrInvalidProblem, summary.Failed, summary.Total)
	}
	return nil
}

// evaluateQuality: ProblemDraft を judge LLM に渡してスコアを取る。
// 問題本文 + テスト + 模範解答を JSON で渡す (judge prompt の {{problem_json}})。
func (h *problemGenerateHandler) evaluateQuality(ctx context.Context, draft *ProblemDraft, category, difficulty string) (*judge.Result, error) {
	// judge に渡す JSON: category / difficulty を含めて「指定難易度に合っているか」も
	// 評価できるようにする。
	payload := map[string]any{
		"title":              draft.Title,
		"description":        draft.Description,
		"category":           category,
		"difficulty":         difficulty,
		"examples":           draft.Examples,
		"test_cases":         draft.TestCases,
		"reference_solution": draft.ReferenceSolution,
	}
	js, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("grading: marshal problem for judge: %w", err)
	}
	res, err := h.judge.Evaluate(ctx, string(js))
	if err != nil {
		// judge JSON パース失敗は問題本文の品質に起因することも多いため
		// ErrInvalidProblem として再生成に流す (= judge.ErrInvalidResponse は
		// wrap されたまま errors.Is で判定可能)。
		if errors.Is(err, judge.ErrInvalidResponse) {
			return nil, fmt.Errorf("%w: judge invalid response: %v", ErrInvalidProblem, err)
		}
		return nil, err
	}
	return res, nil
}
