package judge

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/llm"
)

// fakeProvider: llm.Provider をテスト用に偽装。
// Content / err を固定で返す。
type fakeProvider struct {
	content string
	err     error
	called  int
	// lastOpts: 直近の Generate 呼び出しに渡された opts を検証用に保持。
	lastOpts llm.Options
}

func (f *fakeProvider) Name() string { return "fake" }

func (f *fakeProvider) Generate(_ context.Context, _ []llm.Message, opts llm.Options) (llm.Response, error) {
	f.called++
	f.lastOpts = opts
	if f.err != nil {
		return llm.Response{}, f.err
	}
	return llm.Response{
		Content:  f.content,
		Provider: "fake",
		Model:    "fake-model",
		Usage:    llm.Usage{CostUSD: 0.001},
	}, nil
}

// writeYAML: テスト用に temp ディレクトリへ prompt YAML を書き出す helper。
func writeYAML(t *testing.T, body string) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "p.yaml")
	require.NoError(t, os.WriteFile(path, []byte(body), 0o600))
	return path
}

func TestLoadPrompt_OK(t *testing.T) {
	t.Parallel()

	yaml := `
version: v1
system_prompt: "be an evaluator"
user_template: "evaluate {{problem_json}}"
evaluation:
  num_runs: 3
  threshold: 20
parameters:
  temperature: 0.3
  max_tokens: 2048
`
	p, err := LoadPrompt(writeYAML(t, yaml))
	require.NoError(t, err)
	assert.Equal(t, "v1", p.Version)
	assert.Contains(t, p.SystemPrompt, "evaluator")
	assert.Equal(t, 20, p.Evaluation.Threshold)
	assert.InDelta(t, 0.3, p.Parameters.Temperature, 1e-6)
	assert.NotEmpty(t, p.Hash(), "Hash() は SHA-256 hex を返すべき")
	assert.NotEmpty(t, p.Path())
}

func TestLoadPrompt_MissingRequiredFields(t *testing.T) {
	t.Parallel()

	// system_prompt 欠落
	_, err := LoadPrompt(writeYAML(t, `version: v1
user_template: "x"
`))
	require.Error(t, err)
	assert.Contains(t, err.Error(), "missing system_prompt")
}

func TestEvaluate_ParsesValidResponse(t *testing.T) {
	t.Parallel()

	p, err := LoadPrompt(writeYAML(t, `
version: v1
system_prompt: "s"
user_template: "u {{problem_json}}"
evaluation:
  num_runs: 1
  threshold: 20
parameters:
  temperature: 0.3
  max_tokens: 1024
`))
	require.NoError(t, err)

	fake := &fakeProvider{content: `{
"clarity": {"score": 4, "reason": "明確"},
"test_coverage": {"score": 5, "reason": "網羅"},
"difficulty_match": {"score": 4, "reason": "妥当"},
"educational_value": {"score": 5, "reason": "学べる"},
"originality": {"score": 4, "reason": "工夫あり"},
"total": 22
}`}
	j := New(p, fake)
	res, err := j.Evaluate(context.Background(), `{"title":"x"}`)
	require.NoError(t, err)
	assert.Equal(t, 22, res.Total)
	assert.Equal(t, 20, res.Threshold)
	assert.True(t, res.Passed(), "total 22 >= threshold 20 で Passed")
	assert.InDelta(t, 0.001, res.CostUSD, 1e-9)
	assert.Equal(t, llm.RoleJudge, fake.lastOpts.Role)
	assert.Equal(t, "judge.quality.v1", fake.lastOpts.PromptVersion)
	assert.True(t, fake.lastOpts.JSONMode)
}

func TestEvaluate_FallsBackToSummedTotalIfMissing(t *testing.T) {
	t.Parallel()

	p, err := LoadPrompt(writeYAML(t, `
version: v1
system_prompt: "s"
user_template: "u"
evaluation:
  threshold: 18
`))
	require.NoError(t, err)

	// total キーを返さない応答: 5 軸の合計で補完されるべき (3+3+3+3+3=15)。
	fake := &fakeProvider{content: `{
"clarity": {"score": 3, "reason": "x"},
"test_coverage": {"score": 3, "reason": "x"},
"difficulty_match": {"score": 3, "reason": "x"},
"educational_value": {"score": 3, "reason": "x"},
"originality": {"score": 3, "reason": "x"}
}`}
	res, err := New(p, fake).Evaluate(context.Background(), "{}")
	require.NoError(t, err)
	assert.Equal(t, 15, res.Total, "total 欠落時は 5 軸の合計で補完")
	assert.False(t, res.Passed(), "15 < 18 で Passed=false")
}

func TestEvaluate_InvalidJSONReturnsErrInvalidResponse(t *testing.T) {
	t.Parallel()

	p, err := LoadPrompt(writeYAML(t, `
version: v1
system_prompt: "s"
user_template: "u"
`))
	require.NoError(t, err)
	fake := &fakeProvider{content: "this is not json"}
	_, err = New(p, fake).Evaluate(context.Background(), "{}")
	require.Error(t, err)
	assert.True(t, errors.Is(err, ErrInvalidResponse),
		"JSON パース失敗は ErrInvalidResponse を wrap して返すべき: got %v", err)
}
