package sandbox

import (
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestParseVitest_AllPassed(t *testing.T) {
	t.Parallel()

	stdout := `{
"numTotalTests": 3,
"numPassedTests": 3,
"numFailedTests": 0,
"testResults": [{
  "assertionResults": [
    {"status": "passed", "fullName": "solve 1"},
    {"status": "passed", "fullName": "solve 2"},
    {"status": "passed", "fullName": "solve 3"}
  ]
}]
}`
	s, err := ParseVitest(stdout)
	require.NoError(t, err)
	assert.True(t, s.AllPassed())
	assert.Equal(t, 3, s.Total)
	assert.Empty(t, s.Failures)
}

func TestParseVitest_FailuresTruncatedTo5(t *testing.T) {
	t.Parallel()

	stdout := `{
"numTotalTests": 7,
"numPassedTests": 0,
"numFailedTests": 7,
"testResults": [{
  "assertionResults": [
    {"status": "failed", "fullName": "t1", "failureMessages": ["AssertionError: expected 1 to equal 2"]},
    {"status": "failed", "fullName": "t2", "failureMessages": ["err2"]},
    {"status": "failed", "fullName": "t3", "failureMessages": ["err3"]},
    {"status": "failed", "fullName": "t4", "failureMessages": ["err4"]},
    {"status": "failed", "fullName": "t5", "failureMessages": ["err5"]},
    {"status": "failed", "fullName": "t6", "failureMessages": ["err6"]},
    {"status": "failed", "fullName": "t7", "failureMessages": ["err7"]}
  ]
}]
}`
	s, err := ParseVitest(stdout)
	require.NoError(t, err)
	assert.False(t, s.AllPassed())
	assert.Equal(t, 7, s.Total)
	assert.Equal(t, 7, s.Failed)
	assert.Len(t, s.Failures, 5, "失敗詳細は最大 5 件に短縮")
	assert.Equal(t, "t1", s.Failures[0].Name)
	assert.Contains(t, s.Failures[0].Snippet, "AssertionError")
}

func TestParseVitest_NoiseBeforeJSON(t *testing.T) {
	t.Parallel()

	// vitest 起動時の warning 行が前置されているケース。
	stdout := `Vitest is starting...
Some warning line
{
"numTotalTests": 1,
"numPassedTests": 1,
"numFailedTests": 0,
"testResults": []
}`
	s, err := ParseVitest(stdout)
	require.NoError(t, err)
	assert.True(t, s.AllPassed())
}

func TestParseVitest_EmptyStdout(t *testing.T) {
	t.Parallel()

	_, err := ParseVitest("")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "empty vitest stdout")
}

func TestParseVitest_NoJSONInStdout(t *testing.T) {
	t.Parallel()

	_, err := ParseVitest("only text, no braces here")
	require.Error(t, err)
	assert.Contains(t, err.Error(), "no JSON object")
}

func TestExtractLastJSONObject(t *testing.T) {
	t.Parallel()

	in := `prefix {"a": 1, "b": {"c": 2}} suffix {"x": 3}`
	got := extractLastJSONObject(in)
	assert.Equal(t, `{"x": 3}`, got)
}
