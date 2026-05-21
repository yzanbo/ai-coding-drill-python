package grading

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/llm"
)

// fakeLLMProvider: llm.Provider のテスト用 fake。
type fakeLLMProvider struct {
	content  string
	err      error
	called   int
	lastMsg  []llm.Message
	lastOpt  llm.Options
	cacheHit bool          // 観測ログ cache_hit 検証用 (省略可、既定 false)。
	sleep    time.Duration // 観測ログ latency_ms 検証用 (省略可、既定 0)。応答前にこの時間だけ消費する。
}

func (f *fakeLLMProvider) Name() string { return "fake" }

func (f *fakeLLMProvider) Generate(_ context.Context, msgs []llm.Message, opts llm.Options) (llm.Response, error) {
	f.called++
	f.lastMsg = msgs
	f.lastOpt = opts
	// sleep: 応答前に意図的に時間を消費して latency_ms が実時間を拾えていることを検証する。
	if f.sleep > 0 {
		time.Sleep(f.sleep)
	}
	if f.err != nil {
		return llm.Response{}, f.err
	}
	return llm.Response{
		Content:  f.content,
		Provider: "fake",
		Model:    "fake-model",
		Usage:    llm.Usage{InputTokens: 100, OutputTokens: 200, CostUSD: 0.01},
		CacheHit: f.cacheHit,
	}, nil
}

// writePromptYAML: tmp dir に prompt YAML を書き出す helper。
func writePromptYAML(t *testing.T, body string) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "gen.yaml")
	require.NoError(t, os.WriteFile(path, []byte(body), 0o600))
	return path
}

const minimalPromptYAML = `
version: v1
language: typescript
system_prompt: "you are an examiner"
user_template: "category={{category}} difficulty={{difficulty}}"
parameters:
  temperature: 0.7
  max_tokens: 4096
`

func TestLoadGenerationPrompt_OK(t *testing.T) {
	t.Parallel()

	p, err := LoadGenerationPrompt(writePromptYAML(t, minimalPromptYAML))
	require.NoError(t, err)
	assert.Equal(t, "v1", p.Version)
	assert.Equal(t, "typescript", p.Language)
	assert.InDelta(t, 0.7, p.Parameters.Temperature, 1e-6)
	assert.NotEmpty(t, p.Hash())
}

func TestGenerate_ParsesValidProblem(t *testing.T) {
	t.Parallel()

	p, err := LoadGenerationPrompt(writePromptYAML(t, minimalPromptYAML))
	require.NoError(t, err)

	fake := &fakeLLMProvider{content: `{
"title": "配列の合計",
"description": "数値配列を受け取り合計を返す",
"examples": [{"input": "[1,2,3]", "output": "6"}],
"test_cases": [
  {"input": [[1,2,3]], "expected": 6},
  {"input": [[]], "expected": 0}
],
"reference_solution": "export function solve(a: number[]) { return a.reduce((s,n)=>s+n,0); }"
}`}

	gen := NewProblemGenerator(p, fake)
	draft, err := gen.Generate(context.Background(), "array", "easy")
	require.NoError(t, err)
	assert.Equal(t, "配列の合計", draft.Title)
	assert.Len(t, draft.TestCases, 2)
	assert.Equal(t, llm.RoleGeneration, fake.lastOpt.Role)
	assert.Equal(t, "generation.problem-gen.v1", fake.lastOpt.PromptVersion)
	assert.True(t, fake.lastOpt.JSONMode)
	assert.InDelta(t, 0.01, draft.GeneratedBy.CostUSD, 1e-9)
	assert.Equal(t, "fake", draft.GeneratedBy.Provider)
	assert.Equal(t, "fake-model", draft.GeneratedBy.Model)
	assert.NotEmpty(t, draft.GeneratedBy.PromptHash)
	// user_template の変数置換が効いていること
	require.Len(t, fake.lastMsg, 2)
	assert.Contains(t, fake.lastMsg[1].Content, "category=array")
	assert.Contains(t, fake.lastMsg[1].Content, "difficulty=easy")
}

// TestGenerate_PropagatesObservabilityFields:
// 観測ログ必須フィールド (04-observability.md「LLM 呼び出し時の追加フィールド」) のうち、
// Response から拾う必要がある cache_hit / latency_ms が draft.GeneratedBy に正しく伝播することを検証する。
//
// 検証ポイント:
//   - cache_hit: true / false の両経路で値がそのまま伝わること (zero value 経由のバグ検出)
//   - latency_ms: provider 呼び出しに実時間が掛かっていること (sleep を意図的に挟む)
//     int64 + 単調クロックの性質上 0 以上は自明なので、Greater で「実時間が拾えていること」を検証する。
func TestGenerate_PropagatesObservabilityFields(t *testing.T) {
	t.Parallel()

	const validContent = `{
"title": "t",
"description": "d",
"test_cases": [{"input": [1], "expected": 1}],
"reference_solution": "export function solve(x: number) { return x; }"
}`

	// sleepMs: latency_ms が 0 でないことを安定して検出するための最小待ち時間。
	// CI のクロック粒度ばらつきを吸収するため数 ms 取る。
	const sleepMs = 5

	cases := []struct {
		name     string
		cacheHit bool
	}{
		{name: "cache hit", cacheHit: true},
		{name: "cache miss", cacheHit: false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			p, err := LoadGenerationPrompt(writePromptYAML(t, minimalPromptYAML))
			require.NoError(t, err)

			fake := &fakeLLMProvider{
				content:  validContent,
				cacheHit: tc.cacheHit,
				sleep:    sleepMs * time.Millisecond,
			}
			draft, err := NewProblemGenerator(p, fake).Generate(context.Background(), "array", "easy")
			require.NoError(t, err)

			assert.Equal(t, tc.cacheHit, draft.GeneratedBy.CacheHit)
			assert.Greater(t, draft.GeneratedBy.LatencyMs, int64(0), "latency_ms が provider 呼び出し時間を拾えていない")
		})
	}
}

func TestGenerate_InvalidJSON(t *testing.T) {
	t.Parallel()

	p, err := LoadGenerationPrompt(writePromptYAML(t, minimalPromptYAML))
	require.NoError(t, err)
	fake := &fakeLLMProvider{content: "not json"}
	_, err = NewProblemGenerator(p, fake).Generate(context.Background(), "array", "easy")
	require.Error(t, err)
	assert.True(t, errors.Is(err, ErrInvalidProblem))
}

func TestGenerate_MissingRequiredFields(t *testing.T) {
	t.Parallel()

	p, err := LoadGenerationPrompt(writePromptYAML(t, minimalPromptYAML))
	require.NoError(t, err)

	// test_cases が空配列
	fake := &fakeLLMProvider{content: `{
"title": "t",
"description": "d",
"test_cases": [],
"reference_solution": "export function solve() {}"
}`}
	_, err = NewProblemGenerator(p, fake).Generate(context.Background(), "array", "easy")
	require.Error(t, err)
	assert.True(t, errors.Is(err, ErrInvalidProblem))
	assert.Contains(t, err.Error(), "test_cases is empty")
}
