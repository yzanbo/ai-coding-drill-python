package google

// provider_test.go: ネットワークを叩かない helper の unit test。
// Gemini API 実呼び出しの integration test は将来 testcontainers 化 or
// 環境変数 GOOGLE_API_KEY 在のときだけ走る integration tag を別途用意する想定。

import (
	// context: mapError の deadline 判定テストで使う。
	// errors:  llm の sentinel との errors.Is 判定。
	// testing: 標準テストフレームワーク。
	// time:    context.WithTimeout / 即座に expire させる細工。
	"context"
	"errors"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	"google.golang.org/genai"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/llm"
)

func TestCalcCostUSD_KnownModel(t *testing.T) {
	t.Parallel()

	// gemini-3-flash: input $0.50 / output $3.00 per 1M tokens (ADR 0049)。
	// 1M / 1M トークンなら $0.50 + $3.00 = $3.50。
	got := calcCostUSD("gemini-3-flash", 1_000_000, 1_000_000)
	assert.InDelta(t, 3.50, got, 1e-9, "1M+1M tokens で $3.50 になるべき")

	// 100K / 50K トークン: $0.50 * 0.1 + $3.00 * 0.05 = $0.05 + $0.15 = $0.20。
	got2 := calcCostUSD("gemini-3-flash", 100_000, 50_000)
	assert.InDelta(t, 0.20, got2, 1e-9, "100K+50K tokens で $0.20 になるべき")
}

func TestCalcCostUSD_UnknownModelReturnsZero(t *testing.T) {
	t.Parallel()

	// 単価表に無いモデル ID は 0 を返す: 観測ログで「USD 0.00 が連続」と並ぶことで
	// 「pricingTable に追記漏れがある」と検出できる設計 (silent 推測しない)。
	got := calcCostUSD("nonexistent-model-id", 1_000_000, 1_000_000)
	assert.InDelta(t, 0.0, got, 1e-9, "未知モデルは 0 を返すべき")
}

func TestExtractSystemMessage(t *testing.T) {
	t.Parallel()

	// 単一 system: そのまま返る
	got := extractSystemMessage([]llm.Message{
		{Role: "system", Content: "あなたは TypeScript の出題者です"},
		{Role: "user", Content: "easy 問題を 1 問生成して"},
	})
	assert.Equal(t, "あなたは TypeScript の出題者です", got)

	// 複数 system: 改行で連結 (Gemini は system instruction を 1 つしか持たない)
	got2 := extractSystemMessage([]llm.Message{
		{Role: "system", Content: "rule1"},
		{Role: "user", Content: "..."},
		{Role: "system", Content: "rule2"},
	})
	assert.Equal(t, "rule1\nrule2", got2)

	// system 無し: 空文字
	got3 := extractSystemMessage([]llm.Message{
		{Role: "user", Content: "no system"},
	})
	assert.Equal(t, "", got3)
}

func TestBuildContents_SkipsSystem(t *testing.T) {
	t.Parallel()

	// system は SystemInstruction に回るので Contents から除外される。
	got := buildContents([]llm.Message{
		{Role: "system", Content: "system msg"},
		{Role: "user", Content: "user msg"},
		{Role: "assistant", Content: "assistant msg"},
	})
	require.Len(t, got, 2, "system は contents から除外、user + assistant の 2 件")
	assert.Equal(t, genai.RoleUser, got[0].Role)
	assert.Equal(t, genai.RoleModel, got[1].Role, "assistant は genai.RoleModel に変換")
}

func TestBuildGenAIConfig_AppliesOptions(t *testing.T) {
	t.Parallel()

	temp := 0.7
	opts := llm.Options{
		Role:        llm.RoleGeneration,
		Temperature: &temp,
		MaxTokens:   1024,
		JSONMode:    true,
		Timeout:     30 * time.Second,
	}
	cfg, err := buildGenAIConfig([]llm.Message{{Role: "system", Content: "be brief"}}, opts)
	require.NoError(t, err)
	require.NotNil(t, cfg.Temperature)
	assert.InDelta(t, 0.7, float64(*cfg.Temperature), 1e-6)
	assert.Equal(t, int32(1024), cfg.MaxOutputTokens)
	assert.Equal(t, "application/json", cfg.ResponseMIMEType, "JSONMode 時に MIME type が application/json")
	require.NotNil(t, cfg.SystemInstruction, "system message があれば SystemInstruction が立つ")
}

func TestBuildGenAIConfig_JSONSchemaImpliesJSONMode(t *testing.T) {
	t.Parallel()

	// JSONSchema 指定だけで JSONMode が暗黙 ON になることを確認 (Gemini 仕様)。
	opts := llm.Options{
		Role:       llm.RoleJudge,
		JSONMode:   false,
		JSONSchema: []byte(`{"type":"object","properties":{"score":{"type":"integer"}}}`),
	}
	cfg, err := buildGenAIConfig(nil, opts)
	require.NoError(t, err)
	assert.Equal(t, "application/json", cfg.ResponseMIMEType,
		"JSONSchema のみ指定でも application/json を強制すべき")
	assert.NotNil(t, cfg.ResponseJsonSchema, "JSONSchema を unmarshal して詰めるべき")
}

func TestBuildGenAIConfig_InvalidJSONSchemaReturnsError(t *testing.T) {
	t.Parallel()

	opts := llm.Options{
		Role:       llm.RoleJudge,
		JSONSchema: []byte(`{not valid json`),
	}
	_, err := buildGenAIConfig(nil, opts)
	require.Error(t, err)
	assert.Contains(t, err.Error(), "invalid JSONSchema bytes")
}

func TestMapError_DeadlineExceeded(t *testing.T) {
	t.Parallel()

	// 即座に expire する ctx を作って、err = nil でも callCtx 側で
	// timeout 判定されることを確認。
	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Nanosecond)
	defer cancel()
	time.Sleep(2 * time.Millisecond) // expire を確定させる

	mapped := mapError(errors.New("dummy"), ctx)
	assert.True(t, errors.Is(mapped, llm.ErrTimeout),
		"callCtx が DeadlineExceeded なら ErrTimeout に正規化されるべき: got %v", mapped)
}

func TestMapError_APIError429(t *testing.T) {
	t.Parallel()

	apiErr := genai.APIError{Code: 429, Message: "Resource exhausted"}
	mapped := mapError(apiErr, context.Background())
	assert.True(t, errors.Is(mapped, llm.ErrRateLimit),
		"HTTP 429 は ErrRateLimit に正規化されるべき: got %v", mapped)
}

func TestMapError_StatusResourceExhaustedWithoutCode(t *testing.T) {
	t.Parallel()

	// HTTP Code が 0 のまま Status のみ立っているケース (SDK 内部実装変更や
	// gRPC ライク応答想定) でも RESOURCE_EXHAUSTED は ErrRateLimit に正規化されるべき。
	apiErr := genai.APIError{Code: 0, Status: "RESOURCE_EXHAUSTED", Message: "quota exceeded"}
	mapped := mapError(apiErr, context.Background())
	assert.True(t, errors.Is(mapped, llm.ErrRateLimit),
		"Code=0 + Status=RESOURCE_EXHAUSTED は ErrRateLimit に正規化されるべき: got %v", mapped)
}

func TestMapError_StatusUnauthenticatedWithoutCode(t *testing.T) {
	t.Parallel()

	apiErr := genai.APIError{Code: 0, Status: "UNAUTHENTICATED", Message: "invalid api key"}
	mapped := mapError(apiErr, context.Background())
	assert.True(t, errors.Is(mapped, llm.ErrUnauthorized),
		"Code=0 + Status=UNAUTHENTICATED は ErrUnauthorized に正規化されるべき: got %v", mapped)
}

func TestMapError_APIError401Unauthorized(t *testing.T) {
	t.Parallel()

	apiErr := genai.APIError{Code: 401, Message: "Unauthorized"}
	mapped := mapError(apiErr, context.Background())
	assert.True(t, errors.Is(mapped, llm.ErrUnauthorized),
		"HTTP 401 は ErrUnauthorized に正規化されるべき: got %v", mapped)
}

func TestMapError_OtherErrorIsWrappedNotNormalized(t *testing.T) {
	t.Parallel()

	plain := errors.New("network glitch")
	mapped := mapError(plain, context.Background())
	// llm の sentinel には正規化されない
	assert.False(t, errors.Is(mapped, llm.ErrRateLimit))
	assert.False(t, errors.Is(mapped, llm.ErrUnauthorized))
	assert.False(t, errors.Is(mapped, llm.ErrTimeout))
	// 元のエラーは wrap されている (Unwrap で取り出せる)
	assert.ErrorIs(t, mapped, plain)
}

func TestNew_MissingAPIKey(t *testing.T) {
	t.Parallel()

	// APIKeys に "google" が無い場合は ErrUnauthorized を wrap して即返す
	// (起動時 fail-fast)。
	p, err := New(llm.Config{
		Generation: llm.RoleConfig{Provider: "google", Model: "gemini-3-flash"},
		APIKeys:    map[string]string{},
	})
	assert.Nil(t, p)
	assert.True(t, errors.Is(err, llm.ErrUnauthorized),
		"API キー欠落は ErrUnauthorized を wrap して返すべき: got %v", err)
}

func TestExtractFinishReason_NilResponse(t *testing.T) {
	t.Parallel()

	assert.Equal(t, "unknown", extractFinishReason(nil))
	assert.Equal(t, "unknown", extractFinishReason(&genai.GenerateContentResponse{}))
}

func TestExtractUsage_NilResponse(t *testing.T) {
	t.Parallel()

	got := extractUsage(nil, "gemini-3-flash")
	assert.Equal(t, llm.Usage{}, got)

	got2 := extractUsage(&genai.GenerateContentResponse{}, "gemini-3-flash")
	assert.Equal(t, llm.Usage{}, got2)
}
