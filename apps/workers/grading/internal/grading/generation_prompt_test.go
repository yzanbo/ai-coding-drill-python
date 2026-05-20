package grading

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

// fakeLLMProvider: llm.Provider のテスト用 fake。
type fakeLLMProvider struct {
	content string
	err     error
	called  int
	lastMsg []llm.Message
	lastOpt llm.Options
}

func (f *fakeLLMProvider) Name() string { return "fake" }

func (f *fakeLLMProvider) Generate(_ context.Context, msgs []llm.Message, opts llm.Options) (llm.Response, error) {
	f.called++
	f.lastMsg = msgs
	f.lastOpt = opts
	if f.err != nil {
		return llm.Response{}, f.err
	}
	return llm.Response{
		Content:  f.content,
		Provider: "fake",
		Model:    "fake-model",
		Usage:    llm.Usage{InputTokens: 100, OutputTokens: 200, CostUSD: 0.01},
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
	assert.Equal(t, "fake-model", draft.GeneratedBy.Model)
	assert.NotEmpty(t, draft.GeneratedBy.PromptHash)
	// user_template の変数置換が効いていること
	require.Len(t, fake.lastMsg, 2)
	assert.Contains(t, fake.lastMsg[1].Content, "category=array")
	assert.Contains(t, fake.lastMsg[1].Content, "difficulty=easy")
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
