// Package judge: LLM-as-a-Judge による問題品質評価。
//
// Worker は生成された問題本文 + テスト + 模範解答 を JSON にして本 package に
// 渡し、LLM (judge ロール) に「5 軸スコア」を返してもらう。スコアが閾値を
// 下回ったら orchestrator 側で「再生成 / dead 落とし」を判断する。
//
// 設計境界:
//   - prompt YAML は apps/workers/grading/prompts/judge/quality.v<N>.yaml が SSoT
//   - LLM 呼び出しは internal/llm.Provider interface 経由 (provider SDK 直叩き禁止)
//   - 結果パース失敗は ErrInvalidResponse を返す (orchestrator で再生成 or
//     dead 判定)
//
// MVP の制約 (R1-3):
//   - num_runs > 1 の多回実行・平均化は未実装 (R2 で結線、ADR 0008 / 0049)
//   - prompt YAML の num_runs / threshold は読み取って Result.Threshold に
//     乗せるだけ
//
// 関連:
//   - .claude/rules/prompts.md (YAML スキーマ)
//   - .claude/rules/worker.md  (Layer 1: judge は llm + jobtypes だけ import)
//   - ADR 0008 (LLM-as-a-Judge を自前実装)
//   - ADR 0040 (prompts/ の所在)
package judge

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"strings"

	"gopkg.in/yaml.v3"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/llm"
)

// ErrInvalidResponse: LLM 応答が judge result JSON として parse できなかった。
// orchestrator はこれを「リトライ可能 (= 再生成試行)」と扱う。
var ErrInvalidResponse = fmt.Errorf("judge: invalid response")

// Prompt: prompt YAML の Go 側表現。
// quality.v1.yaml の構造に対応。本 PR で使うフィールドだけ表現する
// (few_shot_examples / output_schema_ref / metadata 等は未使用なので省略)。
type Prompt struct {
	// Version: "v1" / "v2" 等。観測ログに乗せる識別子。
	Version string `yaml:"version"`
	// SystemPrompt: 評価者の役割定義 (system role)。
	SystemPrompt string `yaml:"system_prompt"`
	// UserTemplate: ユーザープロンプト雛形。{{problem_json}} を置換する。
	UserTemplate string `yaml:"user_template"`
	// Evaluation: 評価運用パラメータ。
	Evaluation struct {
		NumRuns   int `yaml:"num_runs"`
		Threshold int `yaml:"threshold"`
	} `yaml:"evaluation"`
	// Parameters: LLM 呼び出しパラメータ。
	Parameters struct {
		Temperature float64 `yaml:"temperature"`
		MaxTokens   int     `yaml:"max_tokens"`
	} `yaml:"parameters"`

	// path: YAML を読み込んだファイルパス (観測ログに乗せる)。
	path string
	// hash: YAML 内容の SHA-256 hex (キャッシュキー / トレーサビリティ)。
	hash string
}

// LoadPrompt: prompt YAML を読み込んで *Prompt を返す。
//
// 失敗パターン: ファイル不在 / YAML 構文エラー / 必須キー欠落。
// 起動時に main から呼ぶ前提で fail-fast (Worker 起動失敗で十分)。
func LoadPrompt(path string) (*Prompt, error) {
	data, err := os.ReadFile(path) //nolint:gosec // path は main から渡す設定値、サンドボックス外で読む正規ファイル
	if err != nil {
		return nil, fmt.Errorf("judge: read prompt %s: %w", path, err)
	}
	var p Prompt
	if err := yaml.Unmarshal(data, &p); err != nil {
		return nil, fmt.Errorf("judge: unmarshal prompt %s: %w", path, err)
	}
	if p.SystemPrompt == "" || p.UserTemplate == "" {
		return nil, fmt.Errorf("judge: prompt %s missing system_prompt or user_template", path)
	}
	sum := sha256.Sum256(data)
	p.path = path
	p.hash = hex.EncodeToString(sum[:])
	return &p, nil
}

// Path: 読み込み元 YAML パス (観測ログ用)。
func (p *Prompt) Path() string { return p.path }

// Hash: YAML 内容の SHA-256 hex (観測ログ用)。
func (p *Prompt) Hash() string { return p.hash }

// AxisScore: 1 評価軸のスコアと理由。
type AxisScore struct {
	Score  int    `json:"score"`
	Reason string `json:"reason"`
}

// Result: LLM が返した JSON を構造化した judge verdict。
// quality.v1.yaml の出力形式に対応。
type Result struct {
	Clarity          AxisScore `json:"clarity"`
	TestCoverage     AxisScore `json:"test_coverage"`
	DifficultyMatch  AxisScore `json:"difficulty_match"`
	EducationalValue AxisScore `json:"educational_value"`
	Originality      AxisScore `json:"originality"`
	Total            int       `json:"total"`

	// 以下は LLM 応答に含まれない実装側フィールド (観測 / 後段判定用)。

	// CostUSD: 本 judge 呼び出しで消費した推定コスト (Provider.Response.Usage 経由)。
	CostUSD float64 `json:"-"`
	// Threshold: prompt YAML の evaluation.threshold (合格ライン)。
	Threshold int `json:"-"`
}

// Passed: 合計スコアが prompt YAML の threshold 以上なら true。
// false なら orchestrator 側で「再生成」を判断する。
func (r *Result) Passed() bool {
	return r.Total >= r.Threshold
}

// Judge: prompt + LLM provider を保持し、Evaluate で 1 件評価する。
type Judge struct {
	prompt   *Prompt
	provider llm.Provider
}

// New: prompt + provider を束ねた Judge を作る。
func New(prompt *Prompt, provider llm.Provider) *Judge {
	return &Judge{prompt: prompt, provider: provider}
}

// Evaluate: 問題 JSON を judge LLM に投げて Result を返す。
//
// 引数:
//   - problemJSON: 評価対象の問題 (本文 + テスト + 模範解答 等) を JSON 文字列で。
//
// 戻り値:
//   - Result: 5 軸スコア + Total + CostUSD + Threshold が詰まる
//   - error : LLM 呼び出し失敗 / ErrInvalidResponse (JSON パース失敗)
//
// MVP では num_runs=1 として 1 回だけ呼ぶ (R2 で多回実行 + 平均化を結線)。
func (j *Judge) Evaluate(ctx context.Context, problemJSON string) (*Result, error) {
	// {{problem_json}} を実値に置換。文字列置換だがプロンプト管理ルール
	// (.claude/rules/prompts.md) 上はテンプレライブラリ使用を推奨。
	// MVP では変数が 1 つだけかつ生成は Worker 内に閉じる (= ユーザ入力が
	// テンプレに直接流れない) ためインジェクションリスクは低い。
	// R2 で cbroglie/mustache 等に置換する想定。
	user := strings.ReplaceAll(j.prompt.UserTemplate, "{{problem_json}}", problemJSON)

	temp := j.prompt.Parameters.Temperature
	opts := llm.DefaultOptions(llm.RoleJudge)
	if temp != 0 {
		opts.Temperature = &temp
	}
	if j.prompt.Parameters.MaxTokens > 0 {
		opts.MaxTokens = j.prompt.Parameters.MaxTokens
	}
	opts.PromptVersion = "judge.quality." + j.prompt.Version
	opts.JSONMode = true

	resp, err := j.provider.Generate(ctx, []llm.Message{
		{Role: "system", Content: j.prompt.SystemPrompt},
		{Role: "user", Content: user},
	}, opts)
	if err != nil {
		return nil, fmt.Errorf("judge: provider generate: %w", err)
	}

	var result Result
	if err := json.Unmarshal([]byte(resp.Content), &result); err != nil {
		return nil, fmt.Errorf("%w: %v (raw=%s)", ErrInvalidResponse, err, truncate(resp.Content, 200))
	}
	// total が LLM 出力に欠落していた場合は 5 軸の合計で補完する。
	if result.Total == 0 {
		result.Total = result.Clarity.Score + result.TestCoverage.Score +
			result.DifficultyMatch.Score + result.EducationalValue.Score +
			result.Originality.Score
	}
	result.CostUSD = resp.Usage.CostUSD
	result.Threshold = j.prompt.Evaluation.Threshold
	return &result, nil
}

// truncate: error メッセージに lengthy LLM 応答を載せると読みづらいので
// 先頭 N 文字に短縮する小道具。
func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}
