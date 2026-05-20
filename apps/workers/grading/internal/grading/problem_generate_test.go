// problem_generate_test.go: handler のエラー分類ロジックを単体テストする。
//
// classifyHandlerError は orchestrator の retry / dead 判定に直結する分岐で、
// 規則が崩れると「transient な docker daemon hang で一発 dead」「永続な
// API キー不正で MaxAttempts まで無駄に retry」のような事故が起きる。
// 各分類ルールを 1 ケースずつ pin する。
package grading

import (
	"errors"
	"fmt"
	"testing"

	"github.com/stretchr/testify/assert"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/llm"
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
