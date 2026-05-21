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

// TestClassifyFailureReason: dead 確定時の最後の error から
// generation_requests.failure_reason に書くタグを決める分類規則を網羅する（R1-7）。
//
// 期待されるタグは 6 種（problem-generation.md §失敗理由タグ）。
// 順序は LLM 系（即 dead）→ retryable 具体タグ → 分類不能フォールバックの順で
// 評価される（classifyFailureReason 本体の switch と一致）。
func TestClassifyFailureReason(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name string
		in   error
		want string
	}{
		{
			name: "nil は max_attempts_exceeded（防御、本来到達しない）",
			in:   nil,
			want: "max_attempts_exceeded",
		},
		{
			name: "llm.ErrUnauthorized は llm_unauthorized（即 dead）",
			in:   fmt.Errorf("provider: %w", llm.ErrUnauthorized),
			want: "llm_unauthorized",
		},
		{
			name: "llm.ErrCostExceeded は llm_cost_exceeded（即 dead）",
			in:   fmt.Errorf("provider: %w", llm.ErrCostExceeded),
			want: "llm_cost_exceeded",
		},
		{
			name: "ErrJudgeBelowThreshold + ErrInvalidProblem は judge_below_threshold",
			in:   fmt.Errorf("%w: %w: judge score 60 below threshold 70", ErrInvalidProblem, ErrJudgeBelowThreshold),
			want: "judge_below_threshold",
		},
		{
			name: "ErrSandboxFailed + ErrInvalidProblem は sandbox_failed",
			in:   fmt.Errorf("%w: %w: 3/10 tests failed", ErrInvalidProblem, ErrSandboxFailed),
			want: "sandbox_failed",
		},
		{
			name: "ErrLLMInvalidOutput + ErrInvalidProblem は llm_invalid_output",
			in:   fmt.Errorf("%w: %w: json unmarshal", ErrInvalidProblem, ErrLLMInvalidOutput),
			want: "llm_invalid_output",
		},
		{
			name: "llm.ErrRateLimit (transient 累積) は llm_rate_limit に分類",
			in:   fmt.Errorf("%w: transient external error: %w", ErrInvalidProblem, llm.ErrRateLimit),
			want: "llm_rate_limit",
		},
		{
			name: "llm.ErrTimeout (transient 累積) は llm_timeout に分類",
			in:   fmt.Errorf("%w: transient external error: %w", ErrInvalidProblem, llm.ErrTimeout),
			want: "llm_timeout",
		},
		{
			name: "llm.ErrInvalidSchema (transient 累積) は llm_schema_invalid に分類",
			in:   fmt.Errorf("%w: transient external error: %w", ErrInvalidProblem, llm.ErrInvalidSchema),
			want: "llm_schema_invalid",
		},
		{
			name: "ErrSandboxInfra (Docker daemon / image 不在) は sandbox_infrastructure に分類",
			in:   fmt.Errorf("%w: transient external error: %w", ErrInvalidProblem, fmt.Errorf("%w: %w", ErrSandboxInfra, errors.New("docker daemon connection refused"))),
			want: "sandbox_infrastructure",
		},
		{
			name: "真に未知の bare error は max_attempts_exceeded fallback",
			in:   errors.New("something unexpected happened"),
			want: "max_attempts_exceeded",
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := classifyFailureReason(tc.in)
			assert.Equal(t, tc.want, got)
		})
	}
}

// --- Handle 経路を pin するための fake / helper 群 ---

// fakeStore: generationStore を in-memory で実装する。
// 既存 status と Insert 結果を仕込めるようにする。
type fakeStore struct {
	// selectStatus: SelectStatus が返す値。default は "pending"
	//   （= 行存在 / 初回処理待ち、本処理に進むケース）。
	//   "completed" / "failed" を入れると冪等性ガードで短絡。
	//   行不在（vanished、issue #83）を模擬したい時は selectErr に pgx.ErrNoRows を入れる。
	selectStatus       string
	selectProducedID   *uuid.UUID
	selectErr          error
	insertReturnedID   uuid.UUID
	insertErr          error
	selectCalls        int
	insertCalls        int
	lastInsertRequest  uuid.UUID
	lastInsertCategory string
	// progressSteps: UpdateProgressStep が呼ばれた順に step 文字列を記録。
	//   Handle が "llm_generating" → "sandbox_verifying" → "judging" → "persisting"
	//   の順序でステップ遷移を書いていることを確認する用。
	progressSteps []string
	// markFailedErr: MarkFailed が返す error。OnDead の分岐確認用。
	//   ErrGenerationRequestVanished を仕込むと「dead 確定後に行が消えていた」
	//   レアケースを模擬できる（issue #83）。
	markFailedErr    error
	markFailedCalls  int
	lastMarkedReqID  uuid.UUID
	lastMarkedReason string
}

func (s *fakeStore) SelectStatus(_ context.Context, _ uuid.UUID) (string, *uuid.UUID, error) {
	s.selectCalls++
	if s.selectErr != nil {
		return "", nil, s.selectErr
	}
	status := s.selectStatus
	if status == "" {
		// default: 行ありで pending（本処理に進む典型ケース）。
		status = "pending"
	}
	return status, s.selectProducedID, nil
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

// UpdateProgressStep: Worker が各ステップ開始時に呼ぶ progress_step UPDATE。
// テストでは呼ばれたステップ列を順番に記録して、Handle が想定順序で
// ステップ遷移を書いているかを後段で assertion できるようにする。
func (s *fakeStore) UpdateProgressStep(_ context.Context, _ uuid.UUID, step string) error {
	s.progressSteps = append(s.progressSteps, step)
	return nil
}

// MarkFailed: OnDead が呼ぶ failed 遷移。テストでは呼び出し回数 / 渡された
// reqID / reason を記録し、markFailedErr が仕込まれていればそれを返す。
func (s *fakeStore) MarkFailed(_ context.Context, requestID uuid.UUID, reason string) error {
	s.markFailedCalls++
	s.lastMarkedReqID = requestID
	s.lastMarkedReason = reason
	return s.markFailedErr
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
	// results: 連続呼び出しで返したい結果列。設定すると 1 回目に results[0]、
	// 2 回目に results[1]…を返す（issue #79 で type-puzzle 経路が tsc → vitest と
	// 2 回 Run するため）。未設定なら従来通り単一の result を毎回返す。
	results []*sandbox.Result
	err     error
	calls   int
}

func (sb *fakeSandbox) Run(_ context.Context, _ []sandbox.FileSource, _ []string) (*sandbox.Result, error) {
	sb.calls++
	if sb.err != nil {
		return nil, sb.err
	}
	if len(sb.results) > 0 {
		idx := sb.calls - 1
		if idx >= len(sb.results) {
			idx = len(sb.results) - 1
		}
		return sb.results[idx], nil
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

// TestHandle_VanishedAtEntry: 冒頭の SelectStatus が pgx.ErrNoRows を返す
// （= generation_requests 行が物理削除済み、E2E /_test/reset レース等）場合、
// LLM / sandbox / judge / Insert を一切呼ばずに nil 返却して MarkSucceeded に
// 倒すことを pin する（issue #83）。
func TestHandle_VanishedAtEntry(t *testing.T) {
	t.Parallel()

	// 行不在を明示的に模擬（pgx.ErrNoRows）。
	store := &fakeStore{selectErr: pgx.ErrNoRows}
	gen, sb, jd := &fakeGenerator{}, &fakeSandbox{}, &fakeJudge{}
	h := newHandlerForTest(store, gen, sb, jd)

	err := h.Handle(context.Background(), makeJob(t))
	require.NoError(t, err, "行不在は正常イベント扱いで nil 返却すべき")
	assert.Equal(t, 1, store.selectCalls)
	assert.Equal(t, 0, gen.calls, "行不在なら LLM を呼んではいけない")
	assert.Equal(t, 0, sb.calls)
	assert.Equal(t, 0, jd.calls)
	assert.Equal(t, 0, store.insertCalls)
}

// TestHandle_VanishedMidProcessing: LLM / sandbox / judge 通過後の
// InsertProblemAndCompleteRequest が ErrGenerationRequestVanished を返す場合
// （= 処理途中で行が削除された、稀な race）も nil 返却で MarkSucceeded に
// 倒すことを pin する。LLM コストは既に発生するが、orchestrator の WARN を
// 出さない方針（issue #83）。
func TestHandle_VanishedMidProcessing(t *testing.T) {
	t.Parallel()

	store := &fakeStore{
		// SelectStatus は pending を返す（行存在、handler は本処理に進む）。
		selectStatus: "pending",
		// InsertProblemAndCompleteRequest が呼ばれた時点で行が消えていた状況を模擬。
		insertErr: fmt.Errorf("%w: id=foo", ErrGenerationRequestVanished),
	}
	gen := &fakeGenerator{draft: validDraft()}
	sb := &fakeSandbox{result: &sandbox.Result{ExitCode: 0, Stdout: validVitestStdout}}
	jd := &fakeJudge{result: validJudgeResult()}
	h := newHandlerForTest(store, gen, sb, jd)

	err := h.Handle(context.Background(), makeJob(t))
	require.NoError(t, err, "処理途中での行消失も nil 返却で succeeded に倒すべき")
	assert.Equal(t, 1, store.insertCalls)
}

// TestOnDead_CallsMarkFailedWithClassifiedReason: lastErr から
// classifyFailureReason で導いたタグ付きで MarkFailed が呼ばれることを pin。
func TestOnDead_CallsMarkFailedWithClassifiedReason(t *testing.T) {
	t.Parallel()

	store := &fakeStore{}
	h := newHandlerForTest(store, &fakeGenerator{}, &fakeSandbox{}, &fakeJudge{})

	j := makeJob(t)
	lastErr := fmt.Errorf("%w: %w: judge below", ErrInvalidProblem, ErrJudgeBelowThreshold)
	h.OnDead(context.Background(), j, lastErr)

	assert.Equal(t, 1, store.markFailedCalls)
	assert.Equal(t, "judge_below_threshold", store.lastMarkedReason)
}

// TestOnDead_VanishedSwallowsAsInfo: MarkFailed が ErrGenerationRequestVanished を
// 返した場合（dead 確定後に行が消えていた race）に WARN を出さず INFO で
// 飲み込むことを pin する（issue #83）。
//
// OnDead は戻り値が無いため、副作用ベースで確認する：
//   - markFailedCalls=1（呼ばれたこと）
//   - panic / 例外が無いこと（vanished 分岐を通る）
//
// 戻り値ベースの assert ができないため、ログレベル切替の挙動は本テスト後の
// 手動 grep / 統合観測（pre-push hook の lefthook 出力 等）で確認する。
func TestOnDead_VanishedSwallowsAsInfo(t *testing.T) {
	t.Parallel()

	store := &fakeStore{
		markFailedErr: fmt.Errorf("%w: id=foo", ErrGenerationRequestVanished),
	}
	h := newHandlerForTest(store, &fakeGenerator{}, &fakeSandbox{}, &fakeJudge{})

	require.NotPanics(t, func() {
		h.OnDead(context.Background(), makeJob(t), errors.New("any handler err"))
	})
	assert.Equal(t, 1, store.markFailedCalls)
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
	// R1-7-2: 各ステップ開始時に progress_step が UPDATE される順序を pin。
	//   FE のステップインジケータがこの順序前提で描画されるので、Handle 内の
	//   updateStep 呼び出し順序が壊れたら即気付けるようにする。
	assert.Equal(
		t,
		[]string{"llm_generating", "sandbox_verifying", "judging", "persisting"},
		store.progressSteps,
		"progress_step が想定順序で UPDATE されるべき",
	)
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
