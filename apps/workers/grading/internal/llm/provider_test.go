package llm

// provider_test.go: interface の最小契約 + DefaultOptions の役割別既定値 +
// Register / New の登録パターンの動作を検証する。
// 実プロバイダ (google 等) の API 呼び出しテストは各 sub-package の
// *_test.go で行い、本ファイルでは llm package 内に閉じる。

import (
	// context: fakeProvider が Generate(ctx, ...) を受けるため。
	// errors:  ErrUnknownProvider との一致判定 (errors.Is) に使う。
	// testing: 標準テストフレームワーク。
	// time:    SingleCallTimeoutDefault の検証用。
	"context"
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
	assert.Equal(t, RoleJudge, opts.Role, "Options.Role に呼び出しロールが乗るべき (観測ログ用)")
	require.NotNil(t, opts.Temperature, "judge の temperature は明示既定値を返すべき")
	assert.InDelta(t, 0.0, *opts.Temperature, 1e-9, "judge は temperature=0.0 (03-llm-pipeline.md)")
	assert.True(t, opts.JSONMode, "judge は JSON mode 強制")
	assert.Equal(t, 30*time.Second, opts.Timeout, "単発タイムアウトは 30s (problem-generation.md)")
}

func TestDefaultOptions_GenerationIsDiverse(t *testing.T) {
	t.Parallel()

	for _, role := range []Role{RoleGeneration, RoleRegeneration} {
		opts := DefaultOptions(role)
		assert.Equal(t, role, opts.Role, "Options.Role に呼び出しロールが乗るべき (観測ログ用)")
		require.NotNil(t, opts.Temperature, "%s の temperature は既定値を返すべき", role)
		assert.InDelta(t, 0.7, *opts.Temperature, 1e-9, "%s は多様性確保のため temperature=0.7", role)
		assert.True(t, opts.JSONMode, "%s は JSON mode 強制", role)
		assert.Equal(t, 30*time.Second, opts.Timeout, "単発タイムアウトは 30s")
	}
}

func TestNew_EmptyProviderReturnsUnknown(t *testing.T) {
	t.Parallel()

	// Config.Generation.Provider が空のままだと「llm.yaml の typo or
	// 読み込み漏れ」のサインなので即 ErrUnknownProvider を返す。
	p, err := New(Config{})
	assert.Nil(t, p)
	assert.True(t, errors.Is(err, ErrUnknownProvider),
		"空 Provider 名は ErrUnknownProvider を wrap して返すべき: got %v", err)
}

func TestNew_UnregisteredProviderReturnsUnknown(t *testing.T) {
	t.Parallel()

	cfg := Config{Generation: RoleConfig{Provider: "definitely-not-registered"}}
	p, err := New(cfg)
	assert.Nil(t, p)
	assert.True(t, errors.Is(err, ErrUnknownProvider),
		"未登録 provider は ErrUnknownProvider を wrap して返すべき: got %v", err)
}

func TestNew_RegisteredProviderIsCalled(t *testing.T) {
	// Register は global state を mutate するため t.Parallel しない。
	// テスト用に専用名 (本番では使わない) を register し、Cleanup で消す。
	const name = "fake-provider-for-unit-test"

	Register(name, func(_ Config) (Provider, error) {
		return &fakeProvider{}, nil
	})
	t.Cleanup(func() {
		providerMu.Lock()
		defer providerMu.Unlock()
		delete(providerFactories, name)
	})

	cfg := Config{Generation: RoleConfig{Provider: name}}
	p, err := New(cfg)
	require.NoError(t, err)
	require.NotNil(t, p)
	assert.Equal(t, "fake", p.Name())
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
}

func TestRoleConfigFor_PanicsOnUnknownRole(t *testing.T) {
	t.Parallel()

	// 未知ロールはプログラマエラー (switch 追従漏れ / 不正キャスト) として
	// panic させ、silent な空 RoleConfig 返却で後段の「API キーなし」エラーに
	// 化けるのを防ぐ。
	cfg := Config{}
	assert.PanicsWithValue(t,
		"llm: unknown role: unknown",
		func() { _ = cfg.RoleConfigFor(Role("unknown")) },
		"未知ロールは panic すべき",
	)
}

// fakeProvider: Register / New の動作確認用ダミー実装。
type fakeProvider struct{}

func (f *fakeProvider) Generate(_ context.Context, _ []Message, _ Options) (Response, error) {
	return Response{}, nil
}

func (f *fakeProvider) Name() string { return "fake" }
