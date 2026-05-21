// submission_grade.go: type="submission.grade" ジョブのハンドラ (R1-5)。
//
// フロー (docs/requirements/4-features/grading.md §採点フロー):
//  1. payload を GradingJobPayload に Unmarshal (submissionId / problemId / code)
//  2. store.GetProblemForGrading で problems.test_cases を取得
//     (soft delete 済 / 存在しない問題は ErrProblemNotFound → 即 dead)
//  3. sandbox に渡す 2 ファイルを組み立てる:
//     - solution.ts      = payload.Code (ユーザー提出)
//     - solution.spec.ts = problems.test_cases を埋め込んだ Vitest harness
//  4. sandbox.Run → sandbox.ParseVitest で結果取得
//  5. 失敗種別を判定 (test_failed / timeout / oom / syntax / runtime / passed)
//  6. submissions UPDATE (status='graded'、score / result / graded_at 書き込み)
//
// 「インフラ起因の障害」(DB 切断 / docker daemon ハング) と「ユーザーコード起因の
// 失敗」(timeout / oom / 構文エラー / 実行時例外) を区別する:
//   - 前者は orchestrator の retry/dead 経路に乗る (ErrInvalidProblem wrap 経由で
//     transient 化、MaxAttempts 到達で dead → OnDead で status='failed')
//   - 後者は採点として「正常終了」扱い (status='graded' + failureKind を埋めて
//     ユーザーに表示する)
package grading

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/job"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/jobtypes"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/sandbox"
)

// gradingStore: 採点ハンドラが触る業務テーブル (problems / submissions) の
// 抽象境界。本番では *pgGradingStore (repository.go)、テストは in-memory fake。
type gradingStore interface {
	GetProblemForGrading(ctx context.Context, problemID uuid.UUID) ([]TestCase, error)
	UpdateSubmissionGraded(ctx context.Context, submissionID uuid.UUID, score int, result []byte) error
	UpdateSubmissionFailed(ctx context.Context, submissionID uuid.UUID) error
}

// submissionGradeHandler: 採点ジョブハンドラ本体。
// 採点フローは LLM を使わないため Generator / Judge は持たない (ADR 0040)。
type submissionGradeHandler struct {
	pool    *pgxpool.Pool
	store   gradingStore
	sandbox sandboxIface
}

// Type: jobHandler 実装。本ハンドラが受け持つ job.Type を返す。
func (h *submissionGradeHandler) Type() string {
	return job.TypeSubmissionGrade
}

// OnDead: ジョブが dead 確定した時の後処理。
//
// jobs テーブル側は orchestrator が既に MarkDead 済み。本関数では submissions を
// status='failed' に遷移させて、ユーザー画面に「採点不能」を表示できるようにする
// (grading.md §採点結果表示「一時的なシステムエラー」)。
//
// lastErr は submissions.failure_reason 列を持たないため使わない（採点側は
// ユーザーに「採点不能」とだけ伝え、詳細は jobs.last_error に残る）。
// 引数は jobHandler interface 整合のため受ける。
//
// payload parse 失敗 / DB UPDATE 失敗は警告ログのみで握り潰す
// (jobs.last_error に残っているので運用追跡可能)。
func (h *submissionGradeHandler) OnDead(ctx context.Context, j *job.Job, _ error) {
	var payload struct {
		SubmissionID string `json:"submissionId"`
	}
	if err := jsonUnmarshal(j.Payload, &payload); err != nil {
		slog.WarnContext(ctx, "submission.grade: cannot parse payload to fail submission",
			"job_id", j.ID, "err", err.Error())
		return
	}
	subID, err := parseUUID(payload.SubmissionID)
	if err != nil {
		slog.WarnContext(ctx, "submission.grade: bad submission_id",
			"job_id", j.ID, "id", payload.SubmissionID)
		return
	}
	if err := h.store.UpdateSubmissionFailed(ctx, subID); err != nil {
		slog.WarnContext(ctx, "submission.grade: failed to mark submission failed",
			"job_id", j.ID, "err", err.Error())
	}
}

// Handle: 1 件の採点ジョブを処理する。
//
// 戻り値:
//   - nil: 採点が「正常終了」(全 pass / テスト失敗 / timeout / oom / syntax /
//     runtime いずれも submissions.status='graded' で確定)
//   - ErrInvalidProblem を wrap した error: インフラ起因の transient 障害
//     (Docker daemon の一過性ハング 等)。orchestrator は MarkFailed で retry。
//   - その他 error: リトライしても直らない永続失敗 (DB エラー / payload 形式不正 /
//     ErrProblemNotFound 等)。orchestrator は即 MarkDead + submissions を failed に。
func (h *submissionGradeHandler) Handle(ctx context.Context, j *job.Job) error {
	var payload jobtypes.GradingJobPayload
	if err := json.Unmarshal(j.Payload, &payload); err != nil {
		return fmt.Errorf("grading: unmarshal payload: %w", err)
	}
	submissionID, err := uuid.Parse(payload.SubmissionID)
	if err != nil {
		return fmt.Errorf("grading: parse submission_id %q: %w", payload.SubmissionID, err)
	}
	problemID, err := uuid.Parse(payload.ProblemID)
	if err != nil {
		return fmt.Errorf("grading: parse problem_id %q: %w", payload.ProblemID, err)
	}

	slog.InfoContext(ctx, "submission.grade: start",
		"job_id", j.ID,
		"attempts", j.Attempts,
		"submission_id", submissionID,
		"problem_id", problemID,
	)

	// 1. 問題の test_cases を取得 (problems.test_cases JSONB を [] TestCase に展開)。
	//    soft delete / 存在しない問題は ErrProblemNotFound → 永続失敗 (即 dead)。
	testCases, err := h.store.GetProblemForGrading(ctx, problemID)
	if err != nil {
		// ErrProblemNotFound は bare のまま返す (orchestrator が dead 経路に)。
		return err
	}

	// 2. solution.ts (ユーザー提出) + solution.spec.ts (自動生成 harness) を組み立てる。
	specBody, err := buildSpecFromCases(testCases)
	if err != nil {
		// test_cases の JSON シリアライズ失敗は通常起きないが、
		// 万一発生したら永続失敗扱い (リトライしても直らない)。
		return fmt.Errorf("grading: build spec for submission %s: %w", submissionID, err)
	}

	// 3. sandbox 実行。
	//    sandbox.Run 自体の error は docker daemon 由来の transient 障害なので
	//    classifyHandlerError で ErrInvalidProblem に詰め替えて retryable にする。
	res, err := h.sandbox.Run(ctx, []sandbox.FileSource{
		{Name: SolutionFileName, Content: payload.Code},
		{Name: SpecFileName, Content: specBody},
	}, vitestCmd)
	if err != nil {
		return classifyHandlerError(fmt.Errorf("grading: sandbox run: %w", err))
	}

	// 4. 結果を解釈して submissions.result JSONB に詰める形に整形する。
	//    classifySandboxOutcome で failure_kind / score / testResults を確定。
	resultPayload := classifySandboxOutcome(res)

	// 5. submissions UPDATE。score は通過テスト件数を入れる。
	//    UpdateSubmissionGraded は status='pending' の行のみを対象にする冪等契約
	//    (at-least-once 配送で 2 回流れてきても 2 回目は ErrSubmissionAlreadyFinalized)。
	resultJSON, err := json.Marshal(resultPayload)
	if err != nil {
		return fmt.Errorf("grading: marshal result for submission %s: %w", submissionID, err)
	}
	if err := h.store.UpdateSubmissionGraded(ctx, submissionID, resultPayload.Score, resultJSON); err != nil {
		if errors.Is(err, ErrSubmissionAlreadyFinalized) {
			slog.InfoContext(ctx, "submission.grade: lost race (already finalized)",
				"job_id", j.ID, "submission_id", submissionID)
			return nil
		}
		return err
	}

	slog.InfoContext(ctx, "submission.grade: completed",
		"job_id", j.ID,
		"submission_id", submissionID,
		"passed", resultPayload.Passed,
		"score", resultPayload.Score,
		"total", len(resultPayload.TestResults),
		"failure_kind", resultPayload.FailureKind,
		"duration_ms", resultPayload.DurationMs,
	)
	return nil
}

// SubmissionTestResultItem: submissions.result.testResults の 1 要素。
// HTTP 境界 (apps/api/app/schemas/submissions.py SubmissionTestResultItem) と
// 同じ camelCase キーで JSON 化する (Backend 側が Pydantic.model_validate で
// 読む契約、ADR 0006)。
type SubmissionTestResultItem struct {
	Name       string `json:"name"`
	Passed     bool   `json:"passed"`
	DurationMs int    `json:"durationMs"`
	Expected   string `json:"expected,omitempty"`
	Actual     string `json:"actual,omitempty"`
	Message    string `json:"message,omitempty"`
}

// SubmissionResultPayload: submissions.result JSONB に書き込む形。
// HTTP 境界の SubmissionResultPayload と完全一致させる契約。
//
//   - Score: 通過テスト件数 (Backend 側で score カラムにも別途書く)。
//   - FailureKind: 失敗種別 (空文字なら null として omitempty で消える)。
type SubmissionResultPayload struct {
	Passed      bool                       `json:"passed"`
	DurationMs  int                        `json:"durationMs"`
	FailureKind string                     `json:"failureKind,omitempty"`
	TestResults []SubmissionTestResultItem `json:"testResults"`

	// Score: payload 内には乗らないが、UpdateSubmissionGraded の引数として
	// orchestrator に渡すため struct に保持する (JSON 化対象外、`json:"-"`)。
	Score int `json:"-"`
}

// 失敗種別の識別子 (Backend 側 SubmissionFailureKind と一致)。
const (
	failureKindTestFailed = "test_failed"
	failureKindTimeout    = "timeout"
	failureKindOOM        = "oom"
	failureKindSyntax     = "syntax"
	failureKindRuntime    = "runtime"
)

// classifySandboxOutcome: sandbox.Result を SubmissionResultPayload に整形する。
//
// 判定ルール:
//   - TimedOut=true                                 → timeout
//   - ExitCode が OOMKilled (137) を示す            → oom
//   - JSON parse 失敗 + stderr に SyntaxError 文字列 → syntax
//   - JSON parse 成功 + 全 pass                     → passed (failure_kind なし)
//   - JSON parse 成功 + 一部失敗                    → test_failed
//   - それ以外 (vitest 異常終了 / JSON 出ない 等)   → runtime
//
// 「インフラ起因」(docker daemon ハング 等) は sandbox.Run が error を返すため
// 本関数には到達しない (Handle 側で classifyHandlerError 経由で retry に流す)。
func classifySandboxOutcome(res *sandbox.Result) *SubmissionResultPayload {
	durationMs := int(res.Duration.Milliseconds())

	// timeout: 実行時間上限を超えて打ち切られた。
	if res.TimedOut {
		return &SubmissionResultPayload{
			Passed:      false,
			DurationMs:  durationMs,
			FailureKind: failureKindTimeout,
			TestResults: []SubmissionTestResultItem{},
			Score:       0,
		}
	}

	// oom: Docker daemon の State.OOMKilled (公式 signal) を最優先で見る。
	// ContainerInspect 失敗時は false で fallback されるが、その場合でも
	// SIGKILL 由来の exit 137 が残るため副次 sentinel として併用する
	// (ユーザコードからの kill -9 を OOM と誤分類するリスクは Inspect が
	// 成功している限り発生しない)。
	const exitOOMKilled = 137
	if res.OOMKilled || res.ExitCode == exitOOMKilled {
		return &SubmissionResultPayload{
			Passed:      false,
			DurationMs:  durationMs,
			FailureKind: failureKindOOM,
			TestResults: []SubmissionTestResultItem{},
			Score:       0,
		}
	}

	// vitest の JSON を試しに parse。JSON が出ていれば「テストは走った」、
	// 出ていなければ「コードが実行できなかった」(syntax / runtime) のどちらか。
	summary, parseErr := sandbox.ParseVitest(res.Stdout)
	if parseErr != nil {
		kind := failureKindRuntime
		// stderr に "SyntaxError" の文字が含まれていれば構文エラー扱いに格上げ。
		// vitest / tsx の出力規約。完全一致でなく substring 判定で十分。
		if strings.Contains(res.Stderr, "SyntaxError") {
			kind = failureKindSyntax
		}
		return &SubmissionResultPayload{
			Passed:      false,
			DurationMs:  durationMs,
			FailureKind: kind,
			TestResults: []SubmissionTestResultItem{},
			Score:       0,
		}
	}

	// JSON parse は成功 = テストは走った。AllPassed なら正解、それ以外は test_failed。
	items := make([]SubmissionTestResultItem, 0, summary.Total)
	for _, f := range summary.Failures {
		items = append(items, SubmissionTestResultItem{
			Name:    f.Name,
			Passed:  false,
			Message: f.Snippet,
		})
	}
	// 失敗以外 (= 通過分) は名前を持たないため疑似的に追加 (件数を Pydantic 側で
	// totalCount として参照するため、配列長 = total を満たす必要がある)。
	for i := len(items); i < summary.Total; i++ {
		items = append(items, SubmissionTestResultItem{
			Name:   fmt.Sprintf("case%d", i+1),
			Passed: true,
		})
	}

	if summary.AllPassed() {
		return &SubmissionResultPayload{
			Passed:      true,
			DurationMs:  durationMs,
			TestResults: items,
			Score:       summary.Passed,
		}
	}
	return &SubmissionResultPayload{
		Passed:      false,
		DurationMs:  durationMs,
		FailureKind: failureKindTestFailed,
		TestResults: items,
		Score:       summary.Passed,
	}
}
