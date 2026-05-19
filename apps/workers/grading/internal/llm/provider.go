// Package llm は LLM プロバイダ抽象化レイヤ（ADR 0007）。
//
// 各プロバイダ（Anthropic / Google / OpenAI / OpenRouter 等）の差分を
// この package の Provider interface で吸収し、呼び出し側（generation /
// judge）はベンダー固有 SDK に依存しない。
//
// R1-2 では interface と共通型のみ定義する。各プロバイダの実装は
// internal/llm/<provider>/ サブ package に分けて R1-2 後半 / R2 以降で
// 追加する。
//
// 関連:
//   - 設計判断:           ../../../../docs/adr/0007-llm-provider-abstraction.md
//   - Worker 集約:        ../../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md
//   - 役割別パラメータ:    ../../../../docs/requirements/2-foundation/03-llm-pipeline.md (構造化出力)
//   - 業務側タイムアウト:  ../../../../docs/requirements/4-features/problem-generation.md (ビジネスルール)
package llm

import (
	// context: 呼び出し元から渡される deadline / cancel を尊重するため。
	//          単発タイムアウトとは別に「ジョブ全体の累積 deadline」を伝える経路。
	// time:    単発呼び出しのタイムアウト既定値 30 秒を表すため。
	"context"
	"time"
)

// Role: LLM 呼び出しの「用途」。役割ごとに temperature / max_tokens /
// JSON mode の既定値が異なる（03-llm-pipeline.md「構造化出力」）。
// YAML 設定では providers.<Role>: { provider, model } の形でモデルを切替える。
type Role string

const (
	// RoleGeneration: 問題本文・テスト・模範解答を最初に生成する用途。
	// 多様性確保のため temperature は高め (0.7) を既定とする。
	RoleGeneration Role = "generation"

	// RoleRegeneration: 既存問題の上位モデル再生成 (再試行) 用途。
	// 既定値は generation と同じだが、別ロールにすることで運用上モデルを
	// 上位に差し替えやすくする（コスト最適化、03-llm-pipeline.md）。
	RoleRegeneration Role = "regeneration"

	// RoleJudge: LLM-as-a-Judge による問題品質評価用途。
	// 評価のブレを抑えるため temperature=0.0 を既定とする。
	RoleJudge Role = "judge"
)

// SingleCallTimeoutDefault: LLM 単発呼び出しの既定タイムアウト。
// 業務側 SSoT は problem-generation.md「ビジネスルール」の 30 秒。
// 累積タイムアウト (ジョブ全体 180 秒) は呼び出し元が context.Context の
// deadline でこの interface に伝える。
const SingleCallTimeoutDefault = 30 * time.Second

// Message: LLM に投げる 1 メッセージ。role は "system" / "user" / "assistant"
// を想定。プロバイダ固有のフォーマット差分は各 sub-package が吸収する。
type Message struct {
	Role    string
	Content string
}

// Options: 1 回の Generate 呼び出しのパラメータ。
// 既定値は DefaultOptions(Role) で生成され、YAML や呼び出し側で必要な
// フィールドだけ上書きする想定。
type Options struct {
	// Role: この呼び出しのロール (generation / regeneration / judge)。
	// DefaultOptions(role) が必ずセットする。Provider 実装はこの値を
	// 観測ログ (OTel span 属性 / 構造化ログ) に乗せ、Config.RoleConfigFor
	// で (provider, model) を引く際の鍵にもする。
	// DefaultOptions 適用後に値を書き換えるのは禁止 (temperature 等の
	// 役割別既定値との整合性が崩れるため)。
	Role Role

	// Temperature: サンプリング温度。nil の場合は role 既定を採用。
	// 役割別既定: generation/regeneration=0.7, judge=0.0。
	Temperature *float64

	// MaxTokens: 出力上限トークン数。0 はプロバイダ既定に委ねる。
	MaxTokens int

	// JSONMode: 構造化出力モード。問題生成・judge とも true を強制する
	// (03-llm-pipeline.md「構造化出力」)。プロバイダの tool_use /
	// function calling / response_format=json_object のいずれかで実現。
	JSONMode bool

	// JSONSchema: JSON 出力に強制する schema (raw JSON Schema バイト列)。
	// nil なら JSONMode のみ有効化して構造は呼び出し側でパース。
	JSONSchema []byte

	// Timeout: 単発呼び出しのタイムアウト。ゼロ値なら
	// SingleCallTimeoutDefault (30 秒) を使う。
	Timeout time.Duration

	// PromptVersion: 観測ログに記録するプロンプトのバージョン
	// (例: "judge.v1")。実装側でメトリクス・スパン属性に乗せる。
	PromptVersion string
}

// Usage: 1 回の呼び出しのトークン消費とコスト換算結果。
// 観測ログ DoD (problem-generation.md) で input_tokens / output_tokens /
// cost_usd の記録が必須となるため、Response に必ず添えて返す。
type Usage struct {
	InputTokens  int
	OutputTokens int
	// CostUSD: モデル単価 × トークン数の換算結果。
	// 単価表は実装側で持ち、ADR 0049 (初期モデル選定 ADR) に対応する。
	CostUSD float64
}

// Response: Generate の戻り値。観測ログ・コスト集計に必要な属性を
// すべて含めて返し、呼び出し側はこれだけ見ればトレースに乗せられる。
type Response struct {
	// Content: LLM が生成した本文 (JSONMode なら JSON 文字列)。
	Content string

	// Usage: トークン消費とコスト換算結果。
	Usage Usage

	// Provider: "anthropic" / "google" / "openai" / "openrouter" 等の識別子。
	Provider string

	// Model: 実際に呼び出されたモデル ID (例: "claude-haiku-4-5-20251001")。
	Model string

	// CacheHit: プロバイダ側のプロンプトキャッシュにヒットしたか。
	// Anthropic Prompt Caching / Gemini Context Caching 等で参照。
	CacheHit bool

	// FinishReason: 終了理由 (stop / length / content_filter / tool_use 等)。
	// プロバイダ間の表記差は sub-package で正規化する。
	FinishReason string
}

// Provider: 各 LLM プロバイダ実装が満たす interface。
// internal/llm/<provider>/ がこれを実装し、呼び出し側 (orchestrator や
// judge) はこの interface 越しにしか LLM を触れない。
type Provider interface {
	// Generate: LLM にメッセージ列を送り、構造化された Response を返す。
	// opts.Timeout 経過 / ctx.Done() のいずれか先に発火した方で打ち切る。
	Generate(ctx context.Context, messages []Message, opts Options) (Response, error)

	// Name: プロバイダ識別子 ("anthropic" 等)。観測ログ・メトリクスに使う。
	Name() string
}

// DefaultOptions: 役割ごとの推奨既定 Options を返す。
// SSoT は 03-llm-pipeline.md「構造化出力」、YAML で上書き可能 (ADR 0007)。
func DefaultOptions(role Role) Options {
	floatPtr := func(v float64) *float64 { return &v }
	switch role {
	case RoleJudge:
		return Options{
			Role:        role,
			Temperature: floatPtr(0.0),
			JSONMode:    true,
			Timeout:     SingleCallTimeoutDefault,
		}
	case RoleGeneration, RoleRegeneration:
		return Options{
			Role:        role,
			Temperature: floatPtr(0.7),
			JSONMode:    true,
			Timeout:     SingleCallTimeoutDefault,
		}
	default:
		return Options{
			Role:    role,
			Timeout: SingleCallTimeoutDefault,
		}
	}
}
