//go:build integration

package google

// provider_integration_test.go: 実 Gemini API を叩く統合テスト。
//
// 通常の `go test ./...` では走らない (build tag `integration` で隔離)。
// 走らせる時は GOOGLE_API_KEY を環境変数で渡し、明示的に tag を有効化する:
//
//   GOOGLE_API_KEY=xxxxx go test -tags=integration ./internal/llm/google/...
//
// CI ではコスト / 鍵管理の都合上、本テストは走らせない (デフォルトの build から除外)。
// 主要パス (Generate の正常系 1 件) を最小コストで検証する位置づけで、ロール別
// 既定値 / プロンプト品質 / エラー正規化等は unit test (provider_test.go) 側で
// 担保する。

import (
	// context: 単発呼び出しの deadline を渡す。
	// os:      GOOGLE_API_KEY の有無で skip 判定。
	// strings: 応答 JSON の最低限の中身チェック。
	// testing: 標準テストフレームワーク。
	// time:    呼び出しタイムアウト指定。
	"context"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/llm"
)

// TestGenerate_Integration_HappyPath: 実 Gemini API に最小プロンプトを投げ
// JSONMode で構造化応答が返ってくることを確認する。
//
// API キー未設定なら t.Skip で抜ける (ローカル開発者全員が GOOGLE_API_KEY を
// 持っているとは限らないため、tag を有効化しただけで落ちるのを避ける)。
func TestGenerate_Integration_HappyPath(t *testing.T) {
	apiKey := os.Getenv("GOOGLE_API_KEY")
	if apiKey == "" {
		t.Skip("GOOGLE_API_KEY 未設定のため skip (integration tag 有効化時のみ実行可)")
	}

	cfg := llm.Config{
		Generation:   llm.RoleConfig{Provider: Name, Model: "gemini-3.5-flash"},
		Regeneration: llm.RoleConfig{Provider: Name, Model: "gemini-3.5-flash"},
		Judge:        llm.RoleConfig{Provider: Name, Model: "gemini-3.5-flash"},
		APIKeys:      map[string]string{Name: apiKey},
	}
	provider, err := New(cfg)
	require.NoError(t, err, "実 API キーで New が成功するべき")
	require.NotNil(t, provider)

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	opts := llm.DefaultOptions(llm.RoleGeneration)
	// JSONMode + 最小プロンプト: 1+1 の答えを JSON で返してもらう。
	// gemini-3.5-flash は thinking モデルで、推論トークンを内部的に消費する。
	// MaxTokens を厳しく絞ると thinking で全部使われて応答が途切れるため
	// (thinking + JSON 応答の余裕として) 1024 を割り当てる。
	// それでも数百トークン以内に収まり、無料枠 / 課金抑制の観点で十分安価。
	opts.MaxTokens = 1024
	opts.JSONSchema = []byte(`{"type":"object","required":["answer"],"properties":{"answer":{"type":"integer"}}}`)

	resp, err := provider.Generate(ctx, []llm.Message{
		{Role: "system", Content: "出力は JSON のみ。"},
		{Role: "user", Content: "1+1 の答えを {\"answer\": <整数>} の形で返してください。"},
	}, opts)
	require.NoError(t, err, "正常系の Generate は成功するべき: got %v", err)

	assert.Equal(t, Name, resp.Provider)
	assert.Equal(t, "gemini-3.5-flash", resp.Model)
	assert.NotEmpty(t, resp.Content, "応答テキストは空でないべき")
	assert.True(t, strings.Contains(resp.Content, "answer"),
		"JSONSchema の required フィールドが応答に含まれるべき: got %q", resp.Content)
	assert.Greater(t, resp.Usage.InputTokens, 0, "input トークン数 > 0")
	assert.Greater(t, resp.Usage.OutputTokens, 0, "output トークン数 > 0")
	assert.Greater(t, resp.Usage.CostUSD, 0.0, "cost > 0 (pricingTable で gemini-3.5-flash がヒット)")
	assert.NotEqual(t, "", resp.FinishReason, "FinishReason は埋まるべき")
}
