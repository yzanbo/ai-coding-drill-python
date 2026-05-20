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
	"github.com/jackc/pgx/v5"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/job"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/jobtypes"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/judge"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/llm"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/sandbox"
)

// generatorIface / sandboxIface / judgeIface / generationStore:
// handler が依存する外部呼び出しを最小 interface に切り出す。
// 本番では具象 (ProblemGenerator / sandbox.Runner / judge.Judge / pgGenerationStore)
// をそのまま渡し、Go の暗黙 interface 実装で適合する。
// テスト (problem_generate_test.go) では in-memory fake を渡して
// 「Handle 内で classifyHandlerError が各 step に効いているか」を検証する。
type generatorIface interface {
	Generate(ctx context.Context, category, difficulty string) (*ProblemDraft, error)
}

type sandboxIface interface {
	Run(ctx context.Context, files []sandbox.FileSource, cmd []string) (*sandbox.Result, error)
}

type judgeIface interface {
	Evaluate(ctx context.Context, problemJSON string) (*judge.Result, error)
}

// generationStore: Handle が generation_requests / problems テーブルに対して
// 行う読み書きを集約する。本番は pgGenerationStore (pool 直叩き)、
// テストは in-memory fake に差し替え。
type generationStore interface {
	// SelectStatus: 行が無い場合 pgx.ErrNoRows を返す (handler 側で短絡しない)。
	SelectStatus(ctx context.Context, requestID uuid.UUID) (status string, producedProblemID *uuid.UUID, err error)
	// InsertProblemAndCompleteRequest: problems INSERT + generation_requests を
	// 1 tx で completed に遷移。先に finalized 済みなら
	// ErrGenerationRequestAlreadyFinalized を返す (handler 側で nil 扱いに変換)。
	InsertProblemAndCompleteRequest(ctx context.Context, draft *ProblemDraft, category, difficulty string, scores JudgeScoresPayload, requestID uuid.UUID) (*CreatedProblem, error)
}

// classifyHandlerError: handler が外部 (LLM / sandbox / judge) 呼び出しで受け取った
// エラーを、orchestrator の retryable / dead 分類に乗るよう整形する。
//
// 分類規則:
//   - 既に ErrInvalidProblem を wrap している → そのまま (二重 wrap しない)
//   - llm.ErrUnauthorized / llm.ErrCostExceeded → bare で返す
//     (リトライしても直らない / 業務上の打ち切り。orchestrator が即 MarkDead)
//   - それ以外 (llm.ErrRateLimit / llm.ErrTimeout / llm.ErrInvalidSchema /
//     docker daemon の一過性ハング 等) → ErrInvalidProblem で wrap して retryable に
//
// 設計意図:
//
//	verifyInSandbox / generator / judge のコメントは「transient error も
//	MaxAttempts に到達するまで retry で吸収する」と書かれているが、
//	orchestrator.handleHandlerError は ErrInvalidProblem 以外を一律で
//	即 MarkDead に流す。この関数で外部呼び出しの bare error を
//	ErrInvalidProblem に詰め替えることでコメントの意図と一致させる。
//	(PR description「ErrInvalidProblem (LLM 出力 / sandbox 失敗 / judge 不合格)
//	 はリトライ可能、それ以外 (DB / unauthorized / 未知 type) は即 dead」と整合)
func classifyHandlerError(err error) error {
	if err == nil {
		return nil
	}
	// 既に ErrInvalidProblem を背負っていればそのまま (generator 側で
	// JSON schema 違反等を ErrInvalidProblem wrap 済みのケース)。
	if errors.Is(err, ErrInvalidProblem) {
		return err
	}
	// 永続エラー: API キー不正 / コスト上限超過は retry しても直らない。
	if errors.Is(err, llm.ErrUnauthorized) || errors.Is(err, llm.ErrCostExceeded) {
		return err
	}
	// transient とみなして retryable 側に倒す。
	// (LLM 429 は provider 内で 3 回 retry 済みでも残ったケース、
	//  ErrTimeout / ErrInvalidSchema / docker daemon hang 等)
	// fmt.Errorf に %w を 2 個渡す書き方 (Go 1.20+) で、
	// errors.Is(out, ErrInvalidProblem) と errors.Is(out, 原因) の両方を可能にする。
	return fmt.Errorf("%w: transient external error: %w", ErrInvalidProblem, err)
}

// vitestCmd: sandbox 内で実行する vitest コマンド。
// グローバルインストール済み (apps/workers/grading/sandbox/Dockerfile) なので
// PATH 解決で起動する。--reporter=json で stdout に JSON 1 オブジェクトが出る。
var vitestCmd = []string{"vitest", "run", "--reporter=json"}

// problemGenerateHandler: orchestrator が dispatch するハンドラ実装。
// 依存は全て interface で受け取り、テストで fake に差し替え可能にする。
type problemGenerateHandler struct {
	store     generationStore
	generator generatorIface
	sandbox   sandboxIface
	judge     judgeIface
}

// Handle: 1 件のジョブを処理する。
//
// 戻り値:
//   - nil:                 成功 (problems INSERT + generation_requests completed 済み)
//   - ErrInvalidProblem を wrap した error: 再生成可能な失敗
//     (sandbox 不合格 / judge 不合格 / LLM 出力 schema 違反 /
//     LLM transient エラー (429 / timeout) / Docker daemon の一過性ハング 等)。
//     orchestrator は MarkFailed で run_at バックオフ。MaxAttempts 到達なら MarkDead。
//   - その他 error: リトライしても直らない永続失敗
//     (llm.ErrUnauthorized / llm.ErrCostExceeded / DB エラー / payload 形式不正 等)。
//     orchestrator は即 MarkDead + generation_requests を failed に。
//
// 外部呼び出し (generator / sandbox / judge) からの bare error は
// classifyHandlerError で transient か永続かを分類してから返す。
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

	// 0. 冪等性ガード: at-least-once 配送で同一 generation_request が 2 回
	//    流れてきた場合 (e.g. MarkSucceeded 失敗 → reclaim → 再 claim) に、
	//    LLM 呼び出し / sandbox / judge の高コスト処理を再実行しない。
	//    1 回目で status='completed' まで進んでいれば、ここで nil を返して
	//    orchestrator に MarkSucceeded を再試行させる (冪等)。
	//    status='failed' に達している場合も同様に再処理しない。
	status, producedProblemID, statusErr := h.store.SelectStatus(ctx, requestID)
	if statusErr != nil && !errors.Is(statusErr, pgx.ErrNoRows) {
		return fmt.Errorf("grading: lookup generation_request before processing: %w", statusErr)
	}
	if statusErr == nil && status != "pending" {
		slog.InfoContext(ctx, "problem.generate: short-circuit (already finalized)",
			"job_id", j.ID,
			"generation_request_id", requestID,
			"status", status,
			"produced_problem_id", producedProblemID,
		)
		return nil
	}

	// 1. LLM 生成
	// classifyHandlerError: provider 由来の transient error (429 / timeout /
	// schema 違反 / NW エラー) を ErrInvalidProblem に詰め替えて retryable 化する。
	// ErrUnauthorized / ErrCostExceeded は bare のままで即 dead 経路へ。
	draft, err := h.generator.Generate(ctx, category, difficulty)
	if err != nil {
		return classifyHandlerError(err)
	}
	slog.InfoContext(ctx, "problem.generate: llm done",
		"job_id", j.ID,
		"title", draft.Title,
		"cost_usd", draft.GeneratedBy.CostUSD,
		"input_tokens", draft.GeneratedBy.InputTokens,
		"output_tokens", draft.GeneratedBy.OutputTokens,
	)

	// 2. サンドボックス検証
	// verifyInSandbox は内部で大半を ErrInvalidProblem wrap 済みだが、
	// Docker daemon 由来の bare error を ErrInvalidProblem に詰め替える。
	if err := h.verifyInSandbox(ctx, draft); err != nil {
		return classifyHandlerError(err)
	}

	// 3. judge 評価
	// classifyHandlerError: judge LLM の transient error を retryable に倒す。
	judgeRes, err := h.evaluateQuality(ctx, draft, category, difficulty)
	if err != nil {
		return classifyHandlerError(err)
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
	// store.InsertProblemAndCompleteRequest: problems INSERT と
	// generation_requests UPDATE を 1 トランザクションで閉じる
	// (ADR 0046 冪等性契約: problems だけ残って requests が pending な
	// 中間状態を作らない)。本番実装は pgGenerationStore (db.WithTx ベース)、
	// テストは in-memory fake で同等の挙動をエミュレートする。
	created, txErr := h.store.InsertProblemAndCompleteRequest(ctx, draft, category, difficulty, scores, requestID)
	if txErr != nil {
		if errors.Is(txErr, ErrGenerationRequestAlreadyFinalized) {
			// 別 worker が先に完了済 (at-least-once 重複)。本ジョブは成功扱いで
			// orchestrator に MarkSucceeded を打たせる。
			slog.InfoContext(ctx, "problem.generate: lost race to another worker, marking succeeded",
				"job_id", j.ID,
				"generation_request_id", requestID,
			)
			return nil
		}
		return txErr
	}
	slog.InfoContext(ctx, "problem.generate: completed",
		"job_id", j.ID,
		"problem_id", created.ID,
		"judge_total", judgeRes.Total,
	)
	return nil
}

// verifyInSandbox: reference_solution + 自動生成 spec を Vitest 実行する。
//
// テスト不合格・タイムアウトはここで ErrInvalidProblem を wrap して返す。
// Docker daemon 由来の bare error はそのまま返し、呼び出し側 (Handle) の
// classifyHandlerError で ErrInvalidProblem に詰め替えられて retryable になる
// (transient な docker daemon hang を MaxAttempts まで retry させるため)。
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
		// Docker daemon の一過性ハング等は呼び出し側で transient と分類されて
		// MaxAttempts まで retry される (classifyHandlerError で wrap)。
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
