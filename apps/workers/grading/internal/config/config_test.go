package config

// config_test.go: 環境変数 + llm.yaml の読み込み挙動を検証する。
// 環境変数は t.Setenv で test 単位に隔離するため t.Parallel を外す
// (caarlos0/env は os.Getenv を読むため並列実行で副作用が出る)。

import (
	// errors:  ErrLLMYAMLMissing との errors.Is 判定。
	// os:      tmp yaml ファイル作成 / Setenv 補助。
	// path/filepath: tmp file path 組み立て。
	// testing: 標準テストフレームワーク。
	"errors"
	"os"
	"path/filepath"
	"testing"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

const sampleYAML = `providers:
  generation:
    provider: google
    model: gemini-3.5-flash
  regeneration:
    provider: google
    model: gemini-3.5-flash
  judge:
    provider: google
    model: gemini-3.5-flash
`

func writeYAML(t *testing.T, content string) string {
	t.Helper()
	dir := t.TempDir()
	path := filepath.Join(dir, "llm.yaml")
	require.NoError(t, os.WriteFile(path, []byte(content), 0o600))
	return path
}

func TestLoad_HappyPath(t *testing.T) {
	yamlPath := writeYAML(t, sampleYAML)
	t.Setenv("DATABASE_URL", "postgres://test/test")
	t.Setenv("GOOGLE_API_KEY", "fake-key")
	t.Setenv("LLM_CONFIG_PATH", yamlPath)

	cfg, err := Load()
	require.NoError(t, err)
	require.NotNil(t, cfg)
	assert.Equal(t, "postgres://test/test", cfg.DatabaseURL)
	assert.Equal(t, "fake-key", cfg.GoogleAPIKey)
	assert.Equal(t, 4, cfg.Concurrency, "envDefault が効いて 4 になるべき")
	assert.Equal(t, "ai-coding-drill-sandbox:latest", cfg.SandboxImage)
	assert.Equal(t, "google", cfg.LLM.Generation.Provider)
	assert.Equal(t, "gemini-3.5-flash", cfg.LLM.Judge.Model)
}

func TestLoad_MissingDatabaseURL(t *testing.T) {
	yamlPath := writeYAML(t, sampleYAML)
	// DATABASE_URL を意図的に外す: caarlos0/env が required エラーを出す。
	t.Setenv("DATABASE_URL", "")
	t.Setenv("LLM_CONFIG_PATH", yamlPath)

	_, err := Load()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "DATABASE_URL", "required タグで欠落を指摘するメッセージが出るべき")
}

func TestLoad_LLMYAMLMissing(t *testing.T) {
	t.Setenv("DATABASE_URL", "postgres://test/test")
	t.Setenv("LLM_CONFIG_PATH", "/tmp/does-not-exist-llm-yaml.yaml")

	_, err := Load()
	require.Error(t, err)
	assert.True(t, errors.Is(err, ErrLLMYAMLMissing),
		"llm.yaml が無ければ ErrLLMYAMLMissing を wrap して返すべき: got %v", err)
}

func TestLoad_LLMYAMLInvalid(t *testing.T) {
	yamlPath := writeYAML(t, "not: valid: yaml: at: all: [unclosed")
	t.Setenv("DATABASE_URL", "postgres://test/test")
	t.Setenv("LLM_CONFIG_PATH", yamlPath)

	_, err := Load()
	require.Error(t, err)
	assert.Contains(t, err.Error(), "unmarshal")
}

func TestLoad_ConcurrencyZeroIsRejected(t *testing.T) {
	yamlPath := writeYAML(t, sampleYAML)
	t.Setenv("DATABASE_URL", "postgres://test/test")
	t.Setenv("LLM_CONFIG_PATH", yamlPath)
	t.Setenv("WORKER_CONCURRENCY", "0")

	_, err := Load()
	require.Error(t, err)
	assert.True(t, errors.Is(err, ErrInvalidRange),
		"WORKER_CONCURRENCY=0 は ErrInvalidRange で弾かれるべき: got %v", err)
	assert.Contains(t, err.Error(), "WORKER_CONCURRENCY")
}

func TestLoad_NegativeJobTimeoutIsRejected(t *testing.T) {
	yamlPath := writeYAML(t, sampleYAML)
	t.Setenv("DATABASE_URL", "postgres://test/test")
	t.Setenv("LLM_CONFIG_PATH", yamlPath)
	t.Setenv("JOB_TIMEOUT_SECONDS", "-1")

	_, err := Load()
	require.Error(t, err)
	assert.True(t, errors.Is(err, ErrInvalidRange),
		"JOB_TIMEOUT_SECONDS=-1 は ErrInvalidRange で弾かれるべき: got %v", err)
	assert.Contains(t, err.Error(), "JOB_TIMEOUT_SECONDS")
}

func TestLoad_NegativeReclaimMinutesIsRejected(t *testing.T) {
	yamlPath := writeYAML(t, sampleYAML)
	t.Setenv("DATABASE_URL", "postgres://test/test")
	t.Setenv("LLM_CONFIG_PATH", yamlPath)
	t.Setenv("RECLAIM_AFTER_MINUTES", "-5")

	_, err := Load()
	require.Error(t, err)
	assert.True(t, errors.Is(err, ErrInvalidRange),
		"RECLAIM_AFTER_MINUTES=-5 は ErrInvalidRange で弾かれるべき: got %v", err)
	assert.Contains(t, err.Error(), "RECLAIM_AFTER_MINUTES")
}

func TestLoad_EnvDefaultsOnlyDB(t *testing.T) {
	// 最小構成: DATABASE_URL のみ与えて他は envDefault に任せる。
	yamlPath := writeYAML(t, sampleYAML)
	t.Setenv("DATABASE_URL", "postgres://test/test")
	t.Setenv("LLM_CONFIG_PATH", yamlPath)

	cfg, err := Load()
	require.NoError(t, err)
	assert.Equal(t, 4, cfg.Concurrency)
	assert.Equal(t, 5, cfg.JobTimeoutSeconds)
	assert.Equal(t, 5, cfg.ReclaimAfterMinutes)
	assert.Equal(t, "ai-coding-drill-sandbox:latest", cfg.SandboxImage)
	assert.Equal(t, "", cfg.WorkerID, "WORKER_ID は既定値なし (main 側でホスト名フォールバック)")
}
