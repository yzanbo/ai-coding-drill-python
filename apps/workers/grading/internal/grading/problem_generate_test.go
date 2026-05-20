// problem_generate_test.go: handler のエラー分類ロジックを単体テストする。
//
// 2 系統のテスト:
//  1. classifyHandlerError: 純粋関数の分類規則 (8 ケース)
//  2. Handle: 各 step (store / generator / sandbox / judge) が返したエラーが
//     classifyHandlerError を経由して正しく retryable / 永続に分類されるか
//
// (2) は handler 内の各 step で `return classifyHandlerError(err)` が
// 正しく呼ばれていることを保証する regression test 群。リファクタで
// classify を被せ忘れると attempts=1 dead 落ちが復活するため、step 単位で pin する。
package grading

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/job"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/jobtypes"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/judge"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/llm"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/sandbox"
)

// TestClassifyHandlerError: 分類規則を 1 ケース 1 行で網羅する。
//
// 期待される結果は「ErrInvalidProblem を背負うか否か」の 2 値判定。
// orchestrator.handleHandlerError は errors.Is(err, ErrInvalidProblem) で
// retry か即 dead かを決めるため、ここで真偽が一致すれば orchestrator 側の
// 振る舞いも自動的に決まる (orchestrator 側の重複テストは不要)。
func TestClassifyHandlerError(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name        string
		in          error
		wantInvalid bool // 期待: ErrInvalidProblem を errors.Is で検出できるか
	}{
		{
			name:        "nil はそのまま nil",
			in:          nil,
			wantInvalid: false,
		},
		{
			name:        "既に ErrInvalidProblem wrap 済みなら二重 wrap しない",
			in:          fmt.Errorf("%w: judge score below threshold", ErrInvalidProblem),
			wantInvalid: true,
		},
		{
			name:        "llm.ErrUnauthorized は bare のまま (= 即 dead)",
			in:          fmt.Errorf("provider: %w", llm.ErrUnauthorized),
			wantInvalid: false,
		},
		{
			name:        "llm.ErrCostExceeded は bare のまま (= 即 dead、業務上の打ち切り)",
			in:          fmt.Errorf("provider: %w", llm.ErrCostExceeded),
			wantInvalid: false,
		},
		{
			name:        "llm.ErrRateLimit は ErrInvalidProblem wrap (= retry、provider 内 3 回 retry 後も残ったケース)",
			in:          fmt.Errorf("provider: %w", llm.ErrRateLimit),
			wantInvalid: true,
		},
		{
			name:        "llm.ErrTimeout は ErrInvalidProblem wrap (= retry)",
			in:          fmt.Errorf("provider: %w", llm.ErrTimeout),
			wantInvalid: true,
		},
		{
			name:        "llm.ErrInvalidSchema は ErrInvalidProblem wrap (= retry、LLM 出力の品質起因)",
			in:          fmt.Errorf("provider: %w", llm.ErrInvalidSchema),
			wantInvalid: true,
		},
		{
			name:        "未知の bare error (docker daemon hang 想定) は ErrInvalidProblem wrap で retry",
			in:          errors.New("sandbox: docker daemon connection refused"),
			wantInvalid: true,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := classifyHandlerError(tc.in)
			if tc.in == nil {
				assert.NoError(t, got)
				return
			}
			assert.Equal(t, tc.wantInvalid, errors.Is(got, ErrInvalidProblem))
			// 元エラーを失わない (errors.Is で原因に辿れる) ことも検証。
			assert.True(t, errors.Is(got, tc.in) || got == tc.in, //nolint:errorlint,err113 // unwrap chain の同一性は errors.Is で十分
				"original error must remain reachable via errors.Is")
		})
	}
}

// --- Handle 経路を pin するための fake / helper 群 ---

// fakeStore: generationStore を in-memory で実装する。
// 既存 status と Insert 結果を仕込めるようにする。
type fakeStore struct {
	// selectStatus: SelectStatus が返す値。default は ErrNoRows (= 初回処理扱い)。
	selectStatus       string
	selectProducedID   *uuid.UUID
	selectErr          error
	insertReturnedID   uuid.UUID
	insertErr          error
	selectCalls        int
	insertCalls        int
	lastInsertRequest  uuid.UUID
	lastInsertCategory string
}

func (s *fakeStore) SelectStatus(_ context.Context, _ uuid.UUID) (string, *uuid.UUID, error) {
	s.selectCalls++
	if s.selectErr != nil {
		return "", nil, s.selectErr
	}
	if s.selectStatus == "" {
		// default: 行が無い扱い (handler は ErrNoRows を pending 同等として扱う)
		return "", nil, pgx.ErrNoRows
	}
	return s.selectStatus, s.selectProducedID, nil
}

func (s *fakeStore) InsertProblemAndCompleteRequest(_ context.Context, _ *ProblemDraft, category, _ string, _ JudgeScoresPayload, requestID uuid.UUID) (*CreatedProblem, error) {
	s.insertCalls++
	s.lastInsertRequest = requestID
	s.lastInsertCategory = category
	if s.insertErr != nil {
		return nil, s.insertErr
	}
	return &CreatedProblem{ID: s.insertReturnedID}, nil
}

// fakeGenerator / fakeSandbox / fakeJudge: 各 interface を in-memory で実装。
// 「N 回目で err を返す」「draft / result を仕込む」が制御できる。

type fakeGenerator struct {
	draft *ProblemDraft
	err   error
	calls int
}

func (g *fakeGenerator) Generate(_ context.Context, _, _ string) (*ProblemDraft, error) {
	g.calls++
	if g.err != nil {
		return nil, g.err
	}
	return g.draft, nil
}

type fakeSandbox struct {
	result *sandbox.Result
	err    error
	calls  int
}

func (sb *fakeSandbox) Run(_ context.Context, _ []sandbox.FileSource, _ []string) (*sandbox.Result, error) {
	sb.calls++
	if sb.err != nil {
		return nil, sb.err
	}
	return sb.result, nil
}

type fakeJudge struct {
	result *judge.Result
	err    error
	calls  int
}

func (j *fakeJudge) Evaluate(_ context.Context, _ string) (*judge.Result, error) {
	j.calls++
	if j.err != nil {
		return nil, j.err
	}
	return j.result, nil
}

// validVitestStdout: ParseVitest が「全テスト pass」と読める最小の vitest JSON。
// sandbox の Run が成功した時の typical な出力を再現する。
const validVitestStdout = `{"numTotalTests":1,"numPassedTests":1,"numFailedTests":0,"testResults":[]}`

// validDraft: validate を通る最小の ProblemDraft。
func validDraft() *ProblemDraft {
	return &ProblemDraft{
		Title:             "テスト問題",
		Description:       "配列の合計を返す",
		Examples:          []Example{{Input: "[1,2,3]", Output: "6"}},
		TestCases:         []TestCase{{Input: []any{[]any{1, 2, 3}}, Expected: 6}},
		ReferenceSolution: "export function solve(a:number[]){return a.reduce((s,n)=>s+n,0);}",
	}
}

// validJudgeResult: 合格スコア (threshold=70、total=80) を返す judge.Result。
func validJudgeResult() *judge.Result {
	return &judge.Result{
		Clarity:          judge.AxisScore{Score: 16},
		TestCoverage:     judge.AxisScore{Score: 16},
		DifficultyMatch:  judge.AxisScore{Score: 16},
		EducationalValue: judge.AxisScore{Score: 16},
		Originality:      judge.AxisScore{Score: 16},
		Total:            80,
		Threshold:        70,
	}
}

// makeJob: 有効な payload を持つ *job.Job を作る helper。
func makeJob(t *testing.T) *job.Job {
	t.Helper()
	payload, err := json.Marshal(jobtypes.ProblemGenerationJobPayload{
		GenerationRequestID: uuid.NewString(),
		Category:            "array",
		Difficulty:          "easy",
	})
	require.NoError(t, err)
	return &job.Job{ID: 1, Queue: job.GenerationQueue, Type: job.TypeProblemGenerate, Payload: payload, Attempts: 1}
}

// newHandlerForTest: 4 つの fake から handler を組み立てる helper。
func newHandlerForTest(store *fakeStore, gen *fakeGenerator, sb *fakeSandbox, j *fakeJudge) *problemGenerateHandler {
	return &problemGenerateHandler{store: store, generator: gen, sandbox: sb, judge: j}
}

// TestHandle_ClassifiesStepErrors: 各 step (generator / sandbox / judge) で
// fake が返したエラーが、Handle 戻り値で classifyHandlerError 経由の
// 分類規則に従っているかを step 単位で検証する。
//
// 検証意図: 「classifyHandlerError は単体テストで OK だが、Handle 内で
// `return classifyHandlerError(err)` を被せ忘れるとリグレッションする」
// を防ぐ。1 step につき transient (ErrInvalidProblem 期待) と
// permanent (bare のまま期待) の両方を回す。
func TestHandle_ClassifiesStepErrors(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name        string
		setup       func(*fakeStore, *fakeGenerator, *fakeSandbox, *fakeJudge)
		wantInvalid bool // ErrInvalidProblem を背負っているか
		wantBare    error
	}{
		{
			name: "generator が llm.ErrTimeout を返す → ErrInvalidProblem (retry)",
			setup: func(_ *fakeStore, g *fakeGenerator, _ *fakeSandbox, _ *fakeJudge) {
				g.err = fmt.Errorf("grading: generation provider: %w", llm.ErrTimeout)
			},
			wantInvalid: true,
		},
		{
			name: "generator が llm.ErrUnauthorized を返す → bare (即 dead)",
			setup: func(_ *fakeStore, g *fakeGenerator, _ *fakeSandbox, _ *fakeJudge) {
				g.err = fmt.Errorf("grading: generation provider: %w", llm.ErrUnauthorized)
			},
			wantInvalid: false,
			wantBare:    llm.ErrUnauthorized,
		},
		{
			name: "sandbox が docker bare error を返す → ErrInvalidProblem (retry)",
			setup: func(_ *fakeStore, g *fakeGenerator, sb *fakeSandbox, _ *fakeJudge) {
				g.draft = validDraft()
				sb.err = errors.New("docker daemon: connection refused")
			},
			wantInvalid: true,
		},
		{
			name: "judge が llm.ErrRateLimit を返す → ErrInvalidProblem (retry)",
			setup: func(_ *fakeStore, g *fakeGenerator, sb *fakeSandbox, j *fakeJudge) {
				g.draft = validDraft()
				sb.result = &sandbox.Result{ExitCode: 0, Stdout: validVitestStdout}
				j.err = fmt.Errorf("judge: provider generate: %w", llm.ErrRateLimit)
			},
			wantInvalid: true,
		},
		{
			name: "judge が llm.ErrCostExceeded を返す → bare (即 dead)",
			setup: func(_ *fakeStore, g *fakeGenerator, sb *fakeSandbox, j *fakeJudge) {
				g.draft = validDraft()
				sb.result = &sandbox.Result{ExitCode: 0, Stdout: validVitestStdout}
				j.err = fmt.Errorf("judge: provider generate: %w", llm.ErrCostExceeded)
			},
			wantInvalid: false,
			wantBare:    llm.ErrCostExceeded,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			store := &fakeStore{insertReturnedID: uuid.New()}
			gen, sb, jd := &fakeGenerator{}, &fakeSandbox{}, &fakeJudge{}
			tc.setup(store, gen, sb, jd)
			h := newHandlerForTest(store, gen, sb, jd)

			err := h.Handle(context.Background(), makeJob(t))
			require.Error(t, err)
			assert.Equal(t, tc.wantInvalid, errors.Is(err, ErrInvalidProblem),
				"ErrInvalidProblem detection mismatch (got=%v)", err)
			if tc.wantBare != nil {
				assert.True(t, errors.Is(err, tc.wantBare),
					"原因 sentinel が unwrap chain で見えない (got=%v)", err)
			}
		})
	}
}

// TestHandle_IdempotencyShortCircuit: SelectStatus が "completed" を返したら
// LLM / sandbox / judge / Insert を一切呼ばずに nil を返すことを検証。
// at-least-once 配送で同じ generation_request が 2 回流れた時に
// 高コスト処理を再実行しないという冪等性ガード (ADR 0046) の pin。
func TestHandle_IdempotencyShortCircuit(t *testing.T) {
	t.Parallel()

	store := &fakeStore{selectStatus: "completed"}
	gen, sb, jd := &fakeGenerator{}, &fakeSandbox{}, &fakeJudge{}
	h := newHandlerForTest(store, gen, sb, jd)

	err := h.Handle(context.Background(), makeJob(t))
	require.NoError(t, err)
	assert.Equal(t, 1, store.selectCalls)
	assert.Equal(t, 0, gen.calls, "generator は呼ばれてはいけない")
	assert.Equal(t, 0, sb.calls, "sandbox は呼ばれてはいけない")
	assert.Equal(t, 0, jd.calls, "judge は呼ばれてはいけない")
	assert.Equal(t, 0, store.insertCalls, "insert は呼ばれてはいけない")
}

// TestHandle_HappyPath: 全 step 成功時に Insert が 1 回呼ばれて nil 返却。
// (retry/dead 経路の boundary 確認: 成功時に classifyHandlerError が
//
//	邪魔しないことの保証)
func TestHandle_HappyPath(t *testing.T) {
	t.Parallel()

	store := &fakeStore{insertReturnedID: uuid.New()}
	gen := &fakeGenerator{draft: validDraft()}
	sb := &fakeSandbox{result: &sandbox.Result{ExitCode: 0, Stdout: validVitestStdout}}
	jd := &fakeJudge{result: validJudgeResult()}
	h := newHandlerForTest(store, gen, sb, jd)

	err := h.Handle(context.Background(), makeJob(t))
	require.NoError(t, err)
	assert.Equal(t, 1, store.insertCalls, "insert が 1 回呼ばれるべき")
}

// TestHandle_JudgeBelowThreshold: judge スコアが threshold 未満なら
// ErrInvalidProblem を返して retry 経路へ。Insert は呼ばれない。
func TestHandle_JudgeBelowThreshold(t *testing.T) {
	t.Parallel()

	failingJudge := &judge.Result{
		Clarity:          judge.AxisScore{Score: 5},
		TestCoverage:     judge.AxisScore{Score: 5},
		DifficultyMatch:  judge.AxisScore{Score: 5},
		EducationalValue: judge.AxisScore{Score: 5},
		Originality:      judge.AxisScore{Score: 5},
		Total:            25,
		Threshold:        70,
	}
	store := &fakeStore{}
	gen := &fakeGenerator{draft: validDraft()}
	sb := &fakeSandbox{result: &sandbox.Result{ExitCode: 0, Stdout: validVitestStdout}}
	jd := &fakeJudge{result: failingJudge}
	h := newHandlerForTest(store, gen, sb, jd)

	err := h.Handle(context.Background(), makeJob(t))
	require.Error(t, err)
	assert.True(t, errors.Is(err, ErrInvalidProblem))
	assert.Equal(t, 0, store.insertCalls)
}
