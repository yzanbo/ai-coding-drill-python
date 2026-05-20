// generation_prompt.go: 問題生成 prompt YAML 読み込み + テンプレ展開 +
// LLM 呼び出し + 応答パースを行う orchestrator 内 helper。
//
// 配置の理由 (worker.md):
//   - R1〜R6 は grading Worker が「問題生成」と「採点」を兼務 (ADR 0040)
//   - 生成 LLM 呼び出しは judge を介さない直接経路のため orchestrator
//     (= internal/grading/) が llm package を直接使う
//   - R7 で apps/workers/generation/ に切り出した時はこのファイル丸ごと
//     internal/generation/ に移動する想定
package grading

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"gopkg.in/yaml.v3"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/llm"
)

// ErrInvalidProblem: LLM 応答が ProblemDraft として parse できない or
// 必須フィールド (title / description / test_cases / reference_solution)
// が欠落している場合に返す。orchestrator はこれを「再生成」候補として扱う。
var ErrInvalidProblem = fmt.Errorf("grading: invalid problem response")

// GenerationPrompt: problem-gen.v<N>.yaml の Go 側表現。
type GenerationPrompt struct {
	Version      string `yaml:"version"`
	Language     string `yaml:"language"`
	SystemPrompt string `yaml:"system_prompt"`
	UserTemplate string `yaml:"user_template"`
	Parameters   struct {
		Temperature float64 `yaml:"temperature"`
		MaxTokens   int     `yaml:"max_tokens"`
	} `yaml:"parameters"`

	path string
	hash string
}

// LoadGenerationPrompt: prompt YAML を読み込んで返す。
// 必須キー欠落は起動時 fail-fast (main から呼ぶ前提)。
func LoadGenerationPrompt(path string) (*GenerationPrompt, error) {
	data, err := os.ReadFile(path) //nolint:gosec // path は main から渡す設定値、サンドボックス外で読む正規ファイル
	if err != nil {
		return nil, fmt.Errorf("grading: read generation prompt %s: %w", path, err)
	}
	var p GenerationPrompt
	if err := yaml.Unmarshal(data, &p); err != nil {
		return nil, fmt.Errorf("grading: unmarshal generation prompt %s: %w", path, err)
	}
	if p.SystemPrompt == "" || p.UserTemplate == "" {
		return nil, fmt.Errorf("grading: generation prompt %s missing system_prompt or user_template", path)
	}
	sum := sha256.Sum256(data)
	p.path = path
	p.hash = hex.EncodeToString(sum[:])
	return &p, nil
}

// Path / Hash: 観測ログ用。
func (p *GenerationPrompt) Path() string { return p.path }
func (p *GenerationPrompt) Hash() string { return p.hash }

// Example: 問題本文の入出力例。
type Example struct {
	Input       string `json:"input"`
	Output      string `json:"output"`
	Explanation string `json:"explanation,omitempty"`
}

// TestCase: Vitest で実行する 1 ケース。
// Input は呼び出し引数の配列、Expected は期待戻り値 (任意型)。
type TestCase struct {
	Input    []any `json:"input"`
	Expected any   `json:"expected"`
}

// ProblemDraft: LLM 応答を構造化した「未検証の問題」。
// サンドボックス + judge を通過したら problems テーブルに書き込まれる。
type ProblemDraft struct {
	Title             string     `json:"title"`
	Description       string     `json:"description"`
	Examples          []Example  `json:"examples"`
	TestCases         []TestCase `json:"test_cases"`
	ReferenceSolution string     `json:"reference_solution"`

	// 観測ログ / 後段で生成元を追跡するためのメタ。
	// 観測ログの必須フィールド (provider / model / prompt_version /
	// cache_hit / input_tokens / output_tokens / cost_usd / 所要時間) は
	// 04-observability.md「LLM 呼び出し時の追加フィールド」が SSoT。
	// 後追加すると過去ログを集計できないため R1 から全フィールドを揃える。
	GeneratedBy struct {
		Provider      string  `json:"-"`
		Model         string  `json:"-"`
		PromptVersion string  `json:"-"`
		PromptHash    string  `json:"-"`
		CostUSD       float64 `json:"-"`
		InputTokens   int     `json:"-"`
		OutputTokens  int     `json:"-"`
		// CacheHit: プロバイダ側プロンプトキャッシュにヒットしたかどうか。
		// Gemini Context Caching / Anthropic Prompt Caching の利用率を後で集計するため。
		CacheHit bool `json:"-"`
		// LatencyMs: provider.Generate の呼び出し開始〜応答受領までのミリ秒。
		// LLM API のレイテンシ分布を追うため。サンドボックス・judge を含まない LLM 単発のみ。
		LatencyMs int64 `json:"-"`
	} `json:"-"`
}

// validate: 必須フィールドが揃っているかを確認する。
// LLM が一部だけ返す / 空文字を返すケースを早期に弾く。
func (p *ProblemDraft) validate() error {
	if strings.TrimSpace(p.Title) == "" {
		return fmt.Errorf("%w: title is empty", ErrInvalidProblem)
	}
	if strings.TrimSpace(p.Description) == "" {
		return fmt.Errorf("%w: description is empty", ErrInvalidProblem)
	}
	if len(p.TestCases) == 0 {
		return fmt.Errorf("%w: test_cases is empty", ErrInvalidProblem)
	}
	if strings.TrimSpace(p.ReferenceSolution) == "" {
		return fmt.Errorf("%w: reference_solution is empty", ErrInvalidProblem)
	}
	return nil
}

// ProblemGenerator: prompt + provider を保持し、Generate で 1 問作る。
type ProblemGenerator struct {
	prompt   *GenerationPrompt
	provider llm.Provider
}

// NewProblemGenerator: コンストラクタ。
func NewProblemGenerator(prompt *GenerationPrompt, provider llm.Provider) *ProblemGenerator {
	return &ProblemGenerator{prompt: prompt, provider: provider}
}

// Generate: category / difficulty を埋めて LLM を呼び、ProblemDraft を返す。
//
// 失敗パターン:
//   - LLM 呼び出し失敗 (provider 層エラー伝播)
//   - JSON パース失敗 / 必須フィールド欠落 -> ErrInvalidProblem を wrap
//
// upper: orchestrator は本関数失敗時、attempts < MaxAttempts なら job.MarkFailed
//
//	(指数バックオフでリトライ) / それ以外は MarkDead に流す。
func (g *ProblemGenerator) Generate(ctx context.Context, category, difficulty string) (*ProblemDraft, error) {
	user := g.prompt.UserTemplate
	user = strings.ReplaceAll(user, "{{category}}", category)
	user = strings.ReplaceAll(user, "{{difficulty}}", difficulty)

	opts := llm.DefaultOptions(llm.RoleGeneration)
	if g.prompt.Parameters.Temperature != 0 {
		t := g.prompt.Parameters.Temperature
		opts.Temperature = &t
	}
	if g.prompt.Parameters.MaxTokens > 0 {
		opts.MaxTokens = g.prompt.Parameters.MaxTokens
	}
	opts.JSONMode = true
	opts.PromptVersion = "generation.problem-gen." + g.prompt.Version

	// startedAt: LLM 単発呼び出しのレイテンシ計測起点。
	// provider 内のリトライ込みの「Generate 呼び出し全体」の所要時間を観測ログに記録する。
	startedAt := time.Now()
	resp, err := g.provider.Generate(ctx, []llm.Message{
		{Role: "system", Content: g.prompt.SystemPrompt},
		{Role: "user", Content: user},
	}, opts)
	if err != nil {
		return nil, fmt.Errorf("grading: generation provider: %w", err)
	}
	latencyMs := time.Since(startedAt).Milliseconds()

	var draft ProblemDraft
	if err := json.Unmarshal([]byte(resp.Content), &draft); err != nil {
		return nil, fmt.Errorf("%w: json unmarshal: %v (raw=%s)", ErrInvalidProblem, err, truncate(resp.Content, 200))
	}
	if err := draft.validate(); err != nil {
		return nil, err
	}
	draft.GeneratedBy.Provider = resp.Provider
	draft.GeneratedBy.Model = resp.Model
	draft.GeneratedBy.PromptVersion = opts.PromptVersion
	draft.GeneratedBy.PromptHash = g.prompt.hash
	draft.GeneratedBy.CostUSD = resp.Usage.CostUSD
	draft.GeneratedBy.InputTokens = resp.Usage.InputTokens
	draft.GeneratedBy.OutputTokens = resp.Usage.OutputTokens
	draft.GeneratedBy.CacheHit = resp.CacheHit
	draft.GeneratedBy.LatencyMs = latencyMs
	return &draft, nil
}

// truncate: error メッセージに LLM 応答を載せる時の文字数制限。
func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}
