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

// generationStore: Handle / OnDead が generation_requests / problems テーブルに
// 対して行う読み書きを集約する。本番は pgGenerationStore (pool 直叩き)、
// テストは in-memory fake に差し替え。
type generationStore interface {
	// SelectStatus: 行が無い場合 pgx.ErrNoRows を返す (handler 側で短絡しない)。
	SelectStatus(ctx context.Context, requestID uuid.UUID) (status string, producedProblemID *uuid.UUID, err error)
	// InsertProblemAndCompleteRequest: problems INSERT + generation_requests を
	// 1 tx で completed に遷移。先に finalized 済みなら
	// ErrGenerationRequestAlreadyFinalized を返す (handler 側で nil 扱いに変換)。
	InsertProblemAndCompleteRequest(ctx context.Context, draft *ProblemDraft, category, difficulty string, scores JudgeScoresPayload, requestID uuid.UUID) (*CreatedProblem, error)
	// UpdateProgressStep: pending 行の現在ステップを書く (R1-7-2)。
	// 失敗は handler 側で警告ログのみで握り潰す (本筋を止めない)。
	UpdateProgressStep(ctx context.Context, requestID uuid.UUID, step string) error
	// MarkFailed: dead 確定時に generation_requests を failed に遷移する。
	// OnDead から呼ぶ。行が物理削除されていた場合は ErrGenerationRequestVanished を
	// wrap して返し、呼び出し側で INFO 扱いに倒せるようにする（issue #83）。
	MarkFailed(ctx context.Context, requestID uuid.UUID, reason string) error
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
//
// generation_requests への書き込みは Handle / OnDead とも store interface 経由に
// 揃える（pool 直叩きの導線は廃止、issue #83 の refactor）。
type problemGenerateHandler struct {
	store     generationStore
	generator generatorIface
	sandbox   sandboxIface
	judge     judgeIface
}

// Type: jobHandler 実装。本ハンドラが受け持つ job.Type を返す。
func (h *problemGenerateHandler) Type() string {
	return job.TypeProblemGenerate
}

// ClassifyFailureReason: jobHandler 実装。本パッケージの classifyFailureReason
// （10 タグの分類器）に委譲する。orchestrator が attempt_errors の各要素 +
// generation_requests.failure_reason のタグ判定に使う。
func (h *problemGenerateHandler) ClassifyFailureReason(err error) string {
	return classifyFailureReason(err)
}

// OnDead: ジョブが dead 確定した時の後処理。
//
// jobs テーブル側は orchestrator が既に MarkDead 済み。本関数では
// generation_requests を failed に遷移させて、UI 側のステータス画面が
// 「永続失敗」と判定できるようにする (problem-generation.md §採点フロー)。
//
// lastErr: dead を引き起こした最後の Handle エラー。classifyFailureReason で
// 具体タグ（judge_below_threshold / sandbox_failed / llm_invalid_output /
// llm_unauthorized / llm_cost_exceeded / max_attempts_exceeded）に分類し、
// generation_requests.failure_reason に書く（ops が DB から SELECT して原因分析）。
//
// payload parse 失敗 / DB UPDATE 失敗は警告ログのみで握り潰す
// (jobs.last_error に残っているので運用追跡可能)。
func (h *problemGenerateHandler) OnDead(ctx context.Context, j *job.Job, lastErr error) {
	var payload struct {
		GenerationRequestID string `json:"generationRequestId"`
	}
	if err := jsonUnmarshal(j.Payload, &payload); err != nil {
		slog.WarnContext(ctx, "problem.generate: cannot parse payload to fail generation_request",
			"job_id", j.ID, "err", err.Error())
		return
	}
	reqID, err := parseUUID(payload.GenerationRequestID)
	if err != nil {
		slog.WarnContext(ctx, "problem.generate: bad generation_request_id",
			"job_id", j.ID, "id", payload.GenerationRequestID)
		return
	}
	reason := classifyFailureReason(lastErr)
	if err := h.store.MarkFailed(ctx, reqID, reason); err != nil {
		// 行が物理削除されていた場合（E2E reset レース / 将来の管理画面削除 等、
		// issue #83）は WARN を出さず INFO に倒す。リクエスタ側が既に結果を
		// 待っていないため「キャンセル相当の正常イベント」として扱う。
		if errors.Is(err, ErrGenerationRequestVanished) {
			slog.InfoContext(ctx, "problem.generate: generation_request vanished, skipping failed transition",
				"job_id", j.ID, "generation_request_id", reqID)
			return
		}
		slog.WarnContext(ctx, "problem.generate: failed to mark generation_request failed",
			"job_id", j.ID, "reason", reason, "err", err.Error())
	}
}

// classifyFailureReason: dead 確定の最後の error を generation_requests.failure_reason
// に書くタグに分類する。
//
// 即 dead 経路：
//   - llm.ErrUnauthorized: "llm_unauthorized" (API キー不正・権限不足)
//   - llm.ErrCostExceeded: "llm_cost_exceeded" (1 ジョブのコスト上限超過)
//
// retry 累積で dead に到達する経路（具体カテゴリ）：
//   - ErrJudgeBelowThreshold: "judge_below_threshold" (judge スコア閾値未満)
//   - ErrSandboxFailed: "sandbox_failed" (sandbox 検証で失敗：vitest 不合格 / timeout)
//   - ErrSandboxInfra: "sandbox_infrastructure" (Docker daemon / image / コンテナ作成)
//   - ErrLLMInvalidOutput: "llm_invalid_output" (LLM 出力 schema 違反)
//   - llm.ErrRateLimit: "llm_rate_limit" (provider 429 が累積)
//   - llm.ErrTimeout: "llm_timeout" (LLM 応答タイムアウトが累積)
//   - llm.ErrInvalidSchema: "llm_schema_invalid" (provider 応答が JSON schema 違反)
//
// 上記いずれも背負わない fallback：
//   - "max_attempts_exceeded" (真に未知。後段の last_error を見て調査する)
//
// 順序：先に「即 dead 経路」、次に「retry 累積の具体カテゴリ」（具体性が高い順）、
// 最後に「LLM transient 種別」（classifyHandlerError で ErrInvalidProblem +
// 元エラーが %w で 2 重 wrap されているため errors.Is で chain を辿れる）。
func classifyFailureReason(err error) string {
	switch {
	case err == nil:
		// 防御。本来 OnDead は handlerErr 非 nil の場合にしか呼ばれないが、
		// 将来 reclaim 経由で dead に落ちる導線が増えた時の保険。
		return "max_attempts_exceeded"
	case errors.Is(err, llm.ErrUnauthorized):
		return "llm_unauthorized"
	case errors.Is(err, llm.ErrCostExceeded):
		return "llm_cost_exceeded"
	case errors.Is(err, ErrJudgeBelowThreshold):
		return "judge_below_threshold"
	case errors.Is(err, ErrSandboxFailed):
		return "sandbox_failed"
	case errors.Is(err, ErrSandboxInfra):
		return "sandbox_infrastructure"
	case errors.Is(err, ErrLLMInvalidOutput):
		return "llm_invalid_output"
	case errors.Is(err, llm.ErrRateLimit):
		return "llm_rate_limit"
	case errors.Is(err, llm.ErrTimeout):
		return "llm_timeout"
	case errors.Is(err, llm.ErrInvalidSchema):
		return "llm_schema_invalid"
	default:
		return "max_attempts_exceeded"
	}
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
	//
	//    行不在 (pgx.ErrNoRows) も「キャンセル相当の正常イベント」として
	//    INFO + nil 返却で短絡する（issue #83）。E2E /_test/reset のレース /
	//    将来の管理画面 / GDPR 削除等で対応 row が消えるケースで、LLM 呼び出し
	//    以降の高コスト処理を回さず即 succeeded に倒す。
	status, producedProblemID, statusErr := h.store.SelectStatus(ctx, requestID)
	if statusErr != nil {
		if errors.Is(statusErr, pgx.ErrNoRows) {
			slog.InfoContext(ctx, "problem.generate: generation_request vanished before processing, marking succeeded",
				"job_id", j.ID,
				"generation_request_id", requestID,
			)
			return nil
		}
		return fmt.Errorf("grading: lookup generation_request before processing: %w", statusErr)
	}
	if status != "pending" {
		slog.InfoContext(ctx, "problem.generate: short-circuit (already finalized)",
			"job_id", j.ID,
			"generation_request_id", requestID,
			"status", status,
			"produced_problem_id", producedProblemID,
		)
		return nil
	}

	// 各ステップ開始時に generation_requests.progress_step を UPDATE する。
	// 失敗時はログのみで握り潰す（観測性向上のための best-effort で、
	// step 書き込みエラーで本筋を止めない）。
	updateStep := func(step string) {
		if err := h.store.UpdateProgressStep(ctx, requestID, step); err != nil {
			slog.WarnContext(ctx, "problem.generate: update progress_step failed",
				"job_id", j.ID, "step", step, "err", err.Error())
		}
	}

	// 1. LLM 生成
	// classifyHandlerError: provider 由来の transient error (429 / timeout /
	// schema 違反 / NW エラー) を ErrInvalidProblem に詰め替えて retryable 化する。
	// ErrUnauthorized / ErrCostExceeded は bare のままで即 dead 経路へ。
	updateStep("llm_generating")
	draft, err := h.generator.Generate(ctx, category, difficulty)
	if err != nil {
		return classifyHandlerError(err)
	}
	// 観測ログ必須フィールド (04-observability.md「LLM 呼び出し時の追加フィールド」):
	//   provider / model / prompt_version / input_tokens / output_tokens /
	//   cost_usd / cache_hit / 所要時間。R1 から全フィールドを記録する
	//   (後追加だと過去ログの集計が不可能になるため)。
	slog.InfoContext(ctx, "problem.generate: llm done",
		"job_id", j.ID,
		"title", draft.Title,
		"provider", draft.GeneratedBy.Provider,
		"model", draft.GeneratedBy.Model,
		"prompt_version", draft.GeneratedBy.PromptVersion,
		"cost_usd", draft.GeneratedBy.CostUSD,
		"input_tokens", draft.GeneratedBy.InputTokens,
		"output_tokens", draft.GeneratedBy.OutputTokens,
		"cache_hit", draft.GeneratedBy.CacheHit,
		"latency_ms", draft.GeneratedBy.LatencyMs,
	)

	// 2. サンドボックス検証
	// verifyInSandbox は内部で大半を ErrInvalidProblem wrap 済みだが、
	// Docker daemon 由来の bare error を ErrInvalidProblem に詰め替える。
	updateStep("sandbox_verifying")
	if err := h.verifyInSandbox(ctx, draft); err != nil {
		return classifyHandlerError(err)
	}

	// 3. judge 評価
	// classifyHandlerError: judge LLM の transient error を retryable に倒す。
	updateStep("judging")
	judgeRes, err := h.evaluateQuality(ctx, draft, category, difficulty)
	if err != nil {
		return classifyHandlerError(err)
	}
	if !judgeRes.Passed() {
		return fmt.Errorf("%w: %w: judge score %d below threshold %d", ErrInvalidProblem, ErrJudgeBelowThreshold, judgeRes.Total, judgeRes.Threshold)
	}

	// 4. 永続化（problems INSERT + generation_requests completed を 1 tx で閉じる）
	updateStep("persisting")
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
		if errors.Is(txErr, ErrGenerationRequestVanished) {
			// 処理中に generation_requests 行が物理削除された（E2E /_test/reset
			// レース / 将来の管理画面削除 等、issue #83）。LLM コストは既に発生
			// 済みだがリクエスタが結果を待っていない以上 problems INSERT は
			// 巻き戻され、ジョブ自体は正常終了扱いに倒す（WARN 抑止）。
			slog.InfoContext(ctx, "problem.generate: generation_request vanished mid-processing, marking succeeded",
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
	// 「LLM が生成した問題が sandbox 検証で落ちる」系の error は ErrSandboxFailed を
	// 2 重 wrap。Docker daemon 由来の bare error だけは sentinel を付けず、
	// classifyHandlerError で transient 化 → 累積で max_attempts_exceeded に倒す。
	specBody, err := buildSpecFile(draft)
	if err != nil {
		return fmt.Errorf("%w: %w: build spec: %v", ErrInvalidProblem, ErrSandboxFailed, err)
	}
	res, err := h.sandbox.Run(ctx, []sandbox.FileSource{
		{Name: SolutionFileName, Content: draft.ReferenceSolution},
		{Name: SpecFileName, Content: specBody},
	}, vitestCmd)
	if err != nil {
		// Docker daemon ハング / image 不在 / コンテナ作成失敗等は ErrSandboxInfra
		// 経由で failure_reason="sandbox_infrastructure" に倒す。
		// classifyHandlerError で ErrInvalidProblem も被せて retryable 化する
		// （複数 %w で sentinel が両方残る）。
		return fmt.Errorf("%w: %w", ErrSandboxInfra, err)
	}
	if res.TimedOut {
		return fmt.Errorf("%w: %w: sandbox timed out", ErrInvalidProblem, ErrSandboxFailed)
	}
	if res.ExitCode != 0 {
		// テスト失敗 (exit code 1) と vitest 起動失敗の区別は stdout の JSON
		// 有無で見る: JSON が出ていれば「テスト失敗」、出ていなければ
		// 「環境エラー」扱い。
		summary, parseErr := sandbox.ParseVitest(res.Stdout)
		if parseErr != nil {
			return fmt.Errorf("%w: %w: vitest run failed (exit=%d, stderr=%s)", ErrInvalidProblem, ErrSandboxFailed, res.ExitCode, truncate(res.Stderr, 200))
		}
		if !summary.AllPassed() {
			return fmt.Errorf("%w: %w: %d/%d tests failed", ErrInvalidProblem, ErrSandboxFailed, summary.Failed, summary.Total)
		}
	}
	// ExitCode 0 でも本当に走ったか確認 (テスト 0 件は不合格扱い)。
	summary, parseErr := sandbox.ParseVitest(res.Stdout)
	if parseErr != nil {
		return fmt.Errorf("%w: %w: parse vitest output: %v", ErrInvalidProblem, ErrSandboxFailed, parseErr)
	}
	if !summary.AllPassed() {
		return fmt.Errorf("%w: %w: vitest reported %d/%d", ErrInvalidProblem, ErrSandboxFailed, summary.Failed, summary.Total)
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
