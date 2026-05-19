package llm

// provider_test.go: skeleton 段階で interface の最小契約を確認するテスト。
// 実プロバイダ実装が増えたら、各 sub-package の *_test.go で
// Provider interface 充足を別途検証する。

import (
	// errors: ErrNotImplemented との一致判定に使う。
	// testing: 標準テストフレームワーク。
	// time:    SingleCallTimeoutDefault の検証用。
	"errors"
	"testing"
	"time"

	// require: 失敗即終了の assert (testify、worker.md 推奨)。
	// assert:  失敗してもテスト継続したい比較用。
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestDefaultOptions_JudgeIsDeterministic(t *testing.T) {
	t.Parallel()

	opts := DefaultOptions(RoleJudge)
	require.NotNil(t, opts.Temperature, "judge の temperature は明示既定値を返すべき")
	assert.InDelta(t, 0.0, *opts.Temperature, 1e-9, "judge は temperature=0.0 (03-llm-pipeline.md)")
	assert.True(t, opts.JSONMode, "judge は JSON mode 強制")
	assert.Equal(t, 30*time.Second, opts.Timeout, "単発タイムアウトは 30s (problem-generation.md)")
}

func TestDefaultOptions_GenerationIsDiverse(t *testing.T) {
	t.Parallel()

	for _, role := range []Role{RoleGeneration, RoleRegeneration} {
		opts := DefaultOptions(role)
		require.NotNil(t, opts.Temperature, "%s の temperature は既定値を返すべき", role)
		assert.InDelta(t, 0.7, *opts.Temperature, 1e-9, "%s は多様性確保のため temperature=0.7", role)
		assert.True(t, opts.JSONMode, "%s は JSON mode 強制", role)
		assert.Equal(t, 30*time.Second, opts.Timeout, "単発タイムアウトは 30s")
	}
}

func TestNew_ReturnsNotImplementedInSkeleton(t *testing.T) {
	t.Parallel()

	// R1-2 skeleton 時点では各プロバイダ実装が未配線のため、
	// New は必ず ErrNotImplemented を返す。
	// このテストは初期モデル選定 ADR 後に各プロバイダ実装が入った
	// 時点で削除 or 書き換える (skeleton 用 sentinel).
	p, err := New(Config{})
	assert.Nil(t, p)
	assert.True(t, errors.Is(err, ErrNotImplemented),
		"skeleton 段階の New は ErrNotImplemented を返す: got %v", err)
}

func TestRoleConfigFor_ReturnsMatchingRole(t *testing.T) {
	t.Parallel()

	cfg := Config{
		Generation:   RoleConfig{Provider: "anthropic", Model: "haiku"},
		Regeneration: RoleConfig{Provider: "anthropic", Model: "sonnet"},
		Judge:        RoleConfig{Provider: "google", Model: "gemini-pro"},
	}

	assert.Equal(t, "anthropic", cfg.RoleConfigFor(RoleGeneration).Provider)
	assert.Equal(t, "sonnet", cfg.RoleConfigFor(RoleRegeneration).Model)
	assert.Equal(t, "google", cfg.RoleConfigFor(RoleJudge).Provider)
	assert.Empty(t, cfg.RoleConfigFor(Role("unknown")).Provider, "未知ロールは空 struct")
}
