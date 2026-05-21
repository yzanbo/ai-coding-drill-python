// submission_grade_test.go: 採点ハンドラ (submissionGradeHandler) のユニットテスト。
//
// 2 系統:
//  1. classifySandboxOutcome: sandbox.Result → SubmissionResultPayload の純粋関数
//     (failure_kind 判定の境界値を網羅)
//  2. Handle / OnDead / Type: fake store + fake sandbox で振る舞いを pin する
//     (orchestrator は呼ばずに hander 内部だけを検証)
package grading

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/job"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/jobtypes"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/sandbox"
)

// ----------------------------------------------------------------------------
// classifySandboxOutcome: 失敗種別の判定境界
// ----------------------------------------------------------------------------

// TestClassifySandboxOutcome_AllPassed:
// vitest が全 pass の JSON を返した時、passed=true / failure_kind 無し /
// testResults 件数 = total となる。
func TestClassifySandboxOutcome_AllPassed(t *testing.T) {
	t.Parallel()
	res := &sandbox.Result{
		ExitCode: 0,
		Stdout:   `{"numTotalTests":3,"numPassedTests":3,"numFailedTests":0,"testResults":[]}`,
		Duration: 250 * time.Millisecond,
	}
	got := classifySandboxOutcome(res)
	assert.True(t, got.Passed)
	assert.Empty(t, got.FailureKind, "全 pass なら failure_kind は空")
	assert.Equal(t, 3, got.Score, "score は通過件数")
	assert.Equal(t, 250, got.DurationMs)
	require.Len(t, got.TestResults, 3, "testResults 件数 = total")
	for _, r := range got.TestResults {
		assert.True(t, r.Passed)
	}
}

// TestClassifySandboxOutcome_PartialFailure:
// 一部失敗時は failure_kind=test_failed / passed=false / 失敗詳細が含まれる。
func TestClassifySandboxOutcome_PartialFailure(t *testing.T) {
	t.Parallel()
	res := &sandbox.Result{
		ExitCode: 1,
		Stdout: `{
			"numTotalTests":3,
			"numPassedTests":1,
			"numFailedTests":2,
			"testResults":[{
				"assertionResults":[
					{"status":"failed","fullName":"case1","title":"case1","failureMessages":["AssertionError"]},
					{"status":"failed","fullName":"case2","title":"case2","failureMessages":["Expected 6"]}
				]
			}]
		}`,
		Duration: 100 * time.Millisecond,
	}
	got := classifySandboxOutcome(res)
	assert.False(t, got.Passed)
	assert.Equal(t, failureKindTestFailed, got.FailureKind)
	assert.Equal(t, 1, got.Score, "score は通過件数 = 1")
	assert.Len(t, got.TestResults, 3, "失敗 2 件 + 通過分埋め 1 件 = total 3")
}

// TestClassifySandboxOutcome_Timeout:
// TimedOut=true なら他のフィールドに依らず failure_kind=timeout。
func TestClassifySandboxOutcome_Timeout(t *testing.T) {
	t.Parallel()
	res := &sandbox.Result{
		TimedOut: true,
		ExitCode: 124,
		Duration: 5000 * time.Millisecond,
	}
	got := classifySandboxOutcome(res)
	assert.False(t, got.Passed)
	assert.Equal(t, failureKindTimeout, got.FailureKind)
	assert.Equal(t, 0, got.Score)
	assert.Empty(t, got.TestResults)
}

// TestClassifySandboxOutcome_OOM:
// ExitCode=137 (SIGKILL 由来) なら failure_kind=oom (Inspect 失敗時の fallback)。
func TestClassifySandboxOutcome_OOM(t *testing.T) {
	t.Parallel()
	res := &sandbox.Result{
		ExitCode: 137,
		Duration: 800 * time.Millisecond,
	}
	got := classifySandboxOutcome(res)
	assert.False(t, got.Passed)
	assert.Equal(t, failureKindOOM, got.FailureKind)
	assert.Equal(t, 0, got.Score)
}

// TestClassifySandboxOutcome_OOMKilledFlag:
// Docker daemon の OOMKilled signal が true なら ExitCode に関係なく failure_kind=oom。
// (cgroup によっては exit code が 137 にならないケースもあるため、公式 signal を優先する。)
func TestClassifySandboxOutcome_OOMKilledFlag(t *testing.T) {
	t.Parallel()
	res := &sandbox.Result{
		ExitCode:  1,
		OOMKilled: true,
		Duration:  500 * time.Millisecond,
	}
	got := classifySandboxOutcome(res)
	assert.False(t, got.Passed)
	assert.Equal(t, failureKindOOM, got.FailureKind)
	assert.Equal(t, 0, got.Score)
}

// TestClassifySandboxOutcome_Syntax:
// JSON parse 失敗 + stderr に SyntaxError 文字列 → failure_kind=syntax。
func TestClassifySandboxOutcome_Syntax(t *testing.T) {
	t.Parallel()
	res := &sandbox.Result{
		ExitCode: 1,
		Stdout:   "", // JSON 出ない
		Stderr:   "SyntaxError: Unexpected token '}'",
		Duration: 50 * time.Millisecond,
	}
	got := classifySandboxOutcome(res)
	assert.False(t, got.Passed)
	assert.Equal(t, failureKindSyntax, got.FailureKind)
}

// TestClassifySandboxOutcome_Runtime:
// JSON parse 失敗 + stderr に SyntaxError 文字列なし → failure_kind=runtime。
func TestClassifySandboxOutcome_Runtime(t *testing.T) {
	t.Parallel()
	res := &sandbox.Result{
		ExitCode: 1,
		Stdout:   "",
		Stderr:   "TypeError: Cannot read property 'x' of undefined",
		Duration: 80 * time.Millisecond,
	}
	got := classifySandboxOutcome(res)
	assert.False(t, got.Passed)
	assert.Equal(t, failureKindRuntime, got.FailureKind)
}

// ----------------------------------------------------------------------------
// fake store + Handle 経路
// ----------------------------------------------------------------------------

// fakeGradingStore: gradingStore を in-memory で実装する。
//
// 各メソッドが返す値・error を仕込み、呼び出し回数 / 引数を観測する。
type fakeGradingStore struct {
	// GetProblemForGrading が返す値。
	getProblemCases    []TestCase
	getProblemCategory string
	getProblemErr      error
	getProblemCalls    int

	// UpdateSubmissionGraded の制御。
	updateGradedErr   error
	updateGradedCalls int
	lastGradedScore   int
	lastGradedResult  []byte

	// UpdateSubmissionFailed の制御。
	updateFailedErr   error
	updateFailedCalls int
	lastFailedID      uuid.UUID
}

func (s *fakeGradingStore) GetProblemForGrading(_ context.Context, _ uuid.UUID) ([]TestCase, string, error) {
	s.getProblemCalls++
	if s.getProblemErr != nil {
		return nil, "", s.getProblemErr
	}
	return s.getProblemCases, s.getProblemCategory, nil
}

func (s *fakeGradingStore) UpdateSubmissionGraded(_ context.Context, _ uuid.UUID, score int, result []byte) error {
	s.updateGradedCalls++
	s.lastGradedScore = score
	s.lastGradedResult = result
	return s.updateGradedErr
}

func (s *fakeGradingStore) UpdateSubmissionFailed(_ context.Context, submissionID uuid.UUID) error {
	s.updateFailedCalls++
	s.lastFailedID = submissionID
	return s.updateFailedErr
}

// makeGradingJob: 有効な GradingJobPayload を持つ *job.Job を作る helper。
func makeGradingJob(t *testing.T, submissionID, problemID uuid.UUID, code string) *job.Job {
	t.Helper()
	payload, err := json.Marshal(jobtypes.GradingJobPayload{
		SubmissionID: submissionID.String(),
		UserID:       uuid.NewString(),
		ProblemID:    problemID.String(),
		Code:         code,
	})
	require.NoError(t, err)
	return &job.Job{
		ID:       1,
		Queue:    job.GradingQueue,
		Type:     job.TypeSubmissionGrade,
		Payload:  payload,
		Attempts: 1,
	}
}

// newGradingHandlerForTest: fake store + fake sandbox から採点ハンドラを組み立てる。
func newGradingHandlerForTest(store *fakeGradingStore, sb *fakeSandbox) *submissionGradeHandler {
	return &submissionGradeHandler{
		// pool は OnDead 系で使うが、Handle / 単体テストでは触らないため nil で良い
		// (OnDead は store.UpdateSubmissionFailed 経由で抽象化済み)。
		store:   store,
		sandbox: sb,
	}
}

// TestSubmissionGradeHandler_Type: dispatch のキー値を pin する。
func TestSubmissionGradeHandler_Type(t *testing.T) {
	t.Parallel()
	h := &submissionGradeHandler{}
	assert.Equal(t, "submission.grade", h.Type())
}

// TestHandle_Grading_NormalFlow:
// 正常系: store.GetProblemForGrading → sandbox.Run → UpdateSubmissionGraded が
// この順に呼ばれて nil を返す。
func TestHandle_Grading_NormalFlow(t *testing.T) {
	t.Parallel()
	store := &fakeGradingStore{
		getProblemCases: []TestCase{{Input: []any{1}, Expected: 2}},
	}
	sb := &fakeSandbox{
		result: &sandbox.Result{
			ExitCode: 0,
			Stdout:   `{"numTotalTests":1,"numPassedTests":1,"numFailedTests":0,"testResults":[]}`,
			Duration: 120 * time.Millisecond,
		},
	}
	h := newGradingHandlerForTest(store, sb)
	j := makeGradingJob(t, uuid.New(), uuid.New(), "export const solve = (n) => n * 2;")

	err := h.Handle(context.Background(), j)

	require.NoError(t, err)
	assert.Equal(t, 1, store.getProblemCalls, "problem 取得が 1 回")
	assert.Equal(t, 1, sb.calls, "sandbox 実行が 1 回")
	assert.Equal(t, 1, store.updateGradedCalls, "UpdateSubmissionGraded が 1 回")
	assert.Equal(t, 1, store.lastGradedScore, "score = 通過件数 1")

	// result JSONB の中身 (camelCase キー / failureKind なし / passed=true)。
	var got map[string]any
	require.NoError(t, json.Unmarshal(store.lastGradedResult, &got))
	assert.Equal(t, true, got["passed"])
	assert.NotContains(t, got, "failureKind", "全 pass は failureKind を omitempty で除外")
	assert.Equal(t, float64(120), got["durationMs"])
}

// TestHandle_Grading_ProblemNotFound:
// store が ErrProblemNotFound を返したら、bare のまま返却される (orchestrator は dead 経路)。
// sandbox は呼ばれない / UpdateSubmissionGraded も呼ばれない。
func TestHandle_Grading_ProblemNotFound(t *testing.T) {
	t.Parallel()
	store := &fakeGradingStore{
		getProblemErr: fmt.Errorf("%w: id=xxx", ErrProblemNotFound),
	}
	sb := &fakeSandbox{}
	h := newGradingHandlerForTest(store, sb)
	j := makeGradingJob(t, uuid.New(), uuid.New(), "x")

	err := h.Handle(context.Background(), j)

	require.Error(t, err)
	assert.True(t, errors.Is(err, ErrProblemNotFound), "ErrProblemNotFound を背負っている")
	assert.False(t, errors.Is(err, ErrInvalidProblem), "retryable には倒さない (即 dead)")
	assert.Equal(t, 0, sb.calls, "sandbox は呼ばれない")
	assert.Equal(t, 0, store.updateGradedCalls)
}

// TestHandle_Grading_SandboxRunErrorIsRetryable:
// sandbox.Run が bare error を返したら、ErrInvalidProblem wrap で retryable に
// 倒されることを確認 (Docker daemon の一過性ハング相当)。
func TestHandle_Grading_SandboxRunErrorIsRetryable(t *testing.T) {
	t.Parallel()
	store := &fakeGradingStore{
		getProblemCases: []TestCase{{Input: []any{1}, Expected: 1}},
	}
	sb := &fakeSandbox{
		err: errors.New("docker daemon: connection refused"),
	}
	h := newGradingHandlerForTest(store, sb)
	j := makeGradingJob(t, uuid.New(), uuid.New(), "x")

	err := h.Handle(context.Background(), j)

	require.Error(t, err)
	assert.True(t, errors.Is(err, ErrInvalidProblem), "transient error は ErrInvalidProblem wrap で retryable に")
	assert.Equal(t, 0, store.updateGradedCalls, "UPDATE はしない")
}

// TestHandle_Grading_AlreadyFinalizedShortCircuits:
// UpdateSubmissionGraded が ErrSubmissionAlreadyFinalized を返したら、
// at-least-once 重複 (別 worker が先に書き込んだ) なので nil を返して終わる
// (orchestrator が MarkSucceeded を打って完了)。
func TestHandle_Grading_AlreadyFinalizedShortCircuits(t *testing.T) {
	t.Parallel()
	store := &fakeGradingStore{
		getProblemCases: []TestCase{{Input: []any{1}, Expected: 1}},
		updateGradedErr: fmt.Errorf("%w: id=xxx", ErrSubmissionAlreadyFinalized),
	}
	sb := &fakeSandbox{
		result: &sandbox.Result{
			ExitCode: 0,
			Stdout:   `{"numTotalTests":1,"numPassedTests":1,"numFailedTests":0,"testResults":[]}`,
		},
	}
	h := newGradingHandlerForTest(store, sb)
	j := makeGradingJob(t, uuid.New(), uuid.New(), "x")

	err := h.Handle(context.Background(), j)

	require.NoError(t, err, "ErrSubmissionAlreadyFinalized は nil 扱いで短絡")
}

// TestOnDead_Grading: payload から submissionId を取り UpdateSubmissionFailed を呼ぶ。
func TestOnDead_Grading(t *testing.T) {
	t.Parallel()
	store := &fakeGradingStore{}
	h := newGradingHandlerForTest(store, &fakeSandbox{})
	subID := uuid.New()
	j := makeGradingJob(t, subID, uuid.New(), "x")

	h.OnDead(context.Background(), j, nil)

	assert.Equal(t, 1, store.updateFailedCalls, "UpdateSubmissionFailed が 1 回呼ばれる")
	assert.Equal(t, subID, store.lastFailedID, "payload の submissionId が渡る")
}

// TestOnDead_Grading_BadPayloadIsSwallowed:
// payload が parse できない / submissionId が UUID でない時は警告ログのみで握り潰す
// (jobs.last_error に残っているので運用追跡可能)。UpdateSubmissionFailed は呼ばれない。
func TestOnDead_Grading_BadPayloadIsSwallowed(t *testing.T) {
	t.Parallel()
	store := &fakeGradingStore{}
	h := newGradingHandlerForTest(store, &fakeSandbox{})
	j := &job.Job{
		ID:      99,
		Payload: []byte(`{"submissionId":"not-a-uuid"}`),
	}

	h.OnDead(context.Background(), j, nil)

	assert.Equal(t, 0, store.updateFailedCalls, "UUID parse 失敗時は UPDATE しない")
}

// ----------------------------------------------------------------------------
// classifyTscOutcome: 型パズル系カテゴリで tsc --noEmit を先に走らせた結果の分類
// (issue #79)
// ----------------------------------------------------------------------------

// TestClassifyTscOutcome_PassReturnsNil:
// tsc が ExitCode=0 で終わった (= 型 OK) なら nil を返して Vitest 経路へ続行させる。
func TestClassifyTscOutcome_PassReturnsNil(t *testing.T) {
	t.Parallel()
	res := &sandbox.Result{ExitCode: 0, Duration: 200 * time.Millisecond}
	got := classifyTscOutcome(res)
	assert.Nil(t, got, "型 OK は nil で短絡しないこと")
}

// TestClassifyTscOutcome_TypeErrorCarriesOutput:
// tsc が非ゼロ終了したら failureKind=type_error。tsc の stdout (TS2322 等の診断文) を
// 1 件の擬似テスト結果として testResults に詰めて UI に出せるようにする。
func TestClassifyTscOutcome_TypeErrorCarriesOutput(t *testing.T) {
	t.Parallel()
	res := &sandbox.Result{
		ExitCode: 1,
		Stdout:   "solution.ts(2,7): error TS2322: Type 'string' is not assignable to type 'number'.\n",
		Duration: 180 * time.Millisecond,
	}
	got := classifyTscOutcome(res)
	require.NotNil(t, got)
	assert.Equal(t, failureKindTypeError, got.FailureKind)
	assert.False(t, got.Passed)
	assert.Equal(t, 0, got.Score)
	assert.Equal(t, 180, got.DurationMs)
	require.Len(t, got.TestResults, 1, "tsc 出力 1 件を擬似テストとして詰める")
	assert.Equal(t, "tsc", got.TestResults[0].Name)
	assert.Contains(t, got.TestResults[0].Message, "TS2322")
}

// TestClassifyTscOutcome_TimeoutAndOOM:
// 型チェック自体が timeout / OOM になった場合は Vitest 経路と同じ分類を返す
// (採点不能として graded 確定させる)。
func TestClassifyTscOutcome_TimeoutAndOOM(t *testing.T) {
	t.Parallel()
	t.Run("timeout", func(t *testing.T) {
		t.Parallel()
		res := &sandbox.Result{TimedOut: true, ExitCode: -1}
		got := classifyTscOutcome(res)
		require.NotNil(t, got)
		assert.Equal(t, failureKindTimeout, got.FailureKind)
	})
	t.Run("oom", func(t *testing.T) {
		t.Parallel()
		res := &sandbox.Result{OOMKilled: true, ExitCode: 137}
		got := classifyTscOutcome(res)
		require.NotNil(t, got)
		assert.Equal(t, failureKindOOM, got.FailureKind)
	})
}

// ----------------------------------------------------------------------------
// Handle: type-puzzle カテゴリ分岐 (issue #79)
// ----------------------------------------------------------------------------

// TestHandle_Grading_TypePuzzle_TscFailureShortCircuits:
// category="type-puzzle" の問題で tsc が型エラーを返したら、Vitest を走らせずに
// failureKind=type_error で submissions を確定する (sandbox 呼び出しは 1 回のみ)。
func TestHandle_Grading_TypePuzzle_TscFailureShortCircuits(t *testing.T) {
	t.Parallel()
	store := &fakeGradingStore{
		getProblemCases:    []TestCase{{Input: []any{1}, Expected: 2}},
		getProblemCategory: "type-puzzle",
	}
	sb := &fakeSandbox{
		// 1 回目 (tsc) で型エラー終了。Vitest 経路には進まないので results は 1 件で十分。
		result: &sandbox.Result{
			ExitCode: 1,
			Stdout:   "solution.ts(2,7): error TS2322: ...\n",
			Duration: 150 * time.Millisecond,
		},
	}
	h := newGradingHandlerForTest(store, sb)
	j := makeGradingJob(t, uuid.New(), uuid.New(), "export const solve = (n) => 'oops';")

	err := h.Handle(context.Background(), j)

	require.NoError(t, err)
	assert.Equal(t, 1, sb.calls, "tsc 1 回だけで Vitest は呼ばない")
	assert.Equal(t, 1, store.updateGradedCalls)
	assert.Equal(t, 0, store.lastGradedScore, "type_error は score=0")

	var got map[string]any
	require.NoError(t, json.Unmarshal(store.lastGradedResult, &got))
	assert.Equal(t, "type_error", got["failureKind"])
	assert.Equal(t, false, got["passed"])
}

// TestHandle_Grading_TypePuzzle_TscPassRunsVitest:
// category="type-puzzle" でも tsc が通れば Vitest 経路に進む。sandbox は tsc → vitest の
// 2 回呼ばれ、最終的に通常の passed=true 結果が書き戻される。
func TestHandle_Grading_TypePuzzle_TscPassRunsVitest(t *testing.T) {
	t.Parallel()
	store := &fakeGradingStore{
		getProblemCases:    []TestCase{{Input: []any{1}, Expected: 2}},
		getProblemCategory: "type-puzzle",
	}
	sb := &fakeSandbox{
		results: []*sandbox.Result{
			// 1 回目: tsc 成功
			{ExitCode: 0, Duration: 100 * time.Millisecond},
			// 2 回目: vitest 全 pass
			{
				ExitCode: 0,
				Stdout:   `{"numTotalTests":1,"numPassedTests":1,"numFailedTests":0,"testResults":[]}`,
				Duration: 200 * time.Millisecond,
			},
		},
	}
	h := newGradingHandlerForTest(store, sb)
	j := makeGradingJob(t, uuid.New(), uuid.New(), "export const solve = (n: number) => n * 2;")

	err := h.Handle(context.Background(), j)

	require.NoError(t, err)
	assert.Equal(t, 2, sb.calls, "tsc + vitest の 2 回 sandbox を実行")
	var got map[string]any
	require.NoError(t, json.Unmarshal(store.lastGradedResult, &got))
	assert.Equal(t, true, got["passed"])
}

// TestHandle_Grading_NonTypePuzzle_SkipsTsc:
// category が type-puzzle 以外 (例: "array") なら tsc 経路はスキップされ、
// sandbox は Vitest 1 回だけ呼ばれる (既存の挙動を回帰防止)。
func TestHandle_Grading_NonTypePuzzle_SkipsTsc(t *testing.T) {
	t.Parallel()
	store := &fakeGradingStore{
		getProblemCases:    []TestCase{{Input: []any{1}, Expected: 2}},
		getProblemCategory: "array",
	}
	sb := &fakeSandbox{
		result: &sandbox.Result{
			ExitCode: 0,
			Stdout:   `{"numTotalTests":1,"numPassedTests":1,"numFailedTests":0,"testResults":[]}`,
			Duration: 120 * time.Millisecond,
		},
	}
	h := newGradingHandlerForTest(store, sb)
	j := makeGradingJob(t, uuid.New(), uuid.New(), "x")

	err := h.Handle(context.Background(), j)
	require.NoError(t, err)
	assert.Equal(t, 1, sb.calls, "type-puzzle 以外は Vitest 1 回だけ")
}
