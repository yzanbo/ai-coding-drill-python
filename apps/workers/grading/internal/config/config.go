// Package config は grading Worker の起動時設定を 1 箇所に集約する。
//
// 役割:
//   - 環境変数を 1 回だけ読み込む (caarlos0/env で Config 構造体に詰める)
//   - LLM プロバイダ設定 YAML (../llm.yaml) を読み込む
//   - 業務 package (internal/{job,sandbox,llm,judge,grading}) は *Config を
//     引数で受け取り、os.Getenv / os.ReadFile を直接呼ばない
//
// 注意点 (worker.md Layer 0 制約):
//   - 本 package は internal/* の他 package を import しない
//     (caarlos0/env + yaml.v3 + 標準ライブラリのみ)
//   - llm package も import しない: LLM 設定は本 package では汎用 struct で
//     保持し、main で llm.Config に詰め直す
package config

import (
	// errors: ErrLLMYAMLMissing の sentinel 定義。
	// fmt:    エラー wrap で path / 詳細を残す。
	// os:     llm.yaml の読み込み (os.ReadFile)。
	// path/filepath: WORKER_LLM_CONFIG_PATH の相対パス解決。
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"github.com/caarlos0/env/v11"
	"gopkg.in/yaml.v3"
)

// ErrLLMYAMLMissing: llm.yaml が指定パスに無い時に Load が返す。
// Worker 起動時に fail-fast させるための sentinel。
var ErrLLMYAMLMissing = errors.New("config: llm.yaml not found")

// RoleProvider: 1 ロール分の (provider, model) 設定。
// llm.RoleConfig と同じ構造だが、本 package は llm を import できないため
// 独立した型として持ち、main で llm.RoleConfig に詰め直す。
type RoleProvider struct {
	Provider string `yaml:"provider"`
	Model    string `yaml:"model"`
}

// LLMProviders: llm.yaml の providers: ブロックそのもの。
// generation / regeneration / judge の 3 ロール固定。
type LLMProviders struct {
	Generation   RoleProvider `yaml:"generation"`
	Regeneration RoleProvider `yaml:"regeneration"`
	Judge        RoleProvider `yaml:"judge"`
}

// llmYAMLFile: llm.yaml の最上位構造 (providers: の親)。
type llmYAMLFile struct {
	Providers LLMProviders `yaml:"providers"`
}

// Config: grading Worker の全環境変数 + llm.yaml の paste 結果。
//
// worker.md「環境変数」セクションが項目の SSoT。新規項目を追加する時は
// 同セクションも合わせて更新する。
type Config struct {
	// DatabaseURL: Postgres 接続文字列。必須 (起動失敗で fail-fast)。
	// notEmpty を使う理由: caarlos0/env の `required` は環境変数の有無のみ
	// 判定し、空文字 ("") は通してしまう。Worker は空 DSN で起動しても
	// 直後の pgx 接続で落ちるため、ここで空も拒否する方が原因究明が早い。
	DatabaseURL string `env:"DATABASE_URL,notEmpty"`

	// WorkerID: jobs.locked_by に書く識別子。
	// 空のまま Load を抜けた場合は cmd/grading/main.go 側で os.Hostname() に
	// フォールバックする (本 package は os.Hostname を読まず、cmd 層で詰める)。
	WorkerID string `env:"WORKER_ID"`

	// Concurrency: 並列 goroutine 数。worker.md 既定 4。
	Concurrency int `env:"WORKER_CONCURRENCY" envDefault:"4"`

	// SandboxImage: 採点コンテナの image タグ。両 Worker で同じ image を起動。
	SandboxImage string `env:"SANDBOX_IMAGE" envDefault:"ai-coding-drill-sandbox:latest"`

	// JobTimeoutSeconds: 1 ジョブの最大処理時間。grading 既定 5 秒
	// (sandbox 実行のみ)。LLM 呼び出しを含むジョブ (R1-2 以降の生成兼務) では
	// problem-generation.md の 180 秒を別途使う想定。
	JobTimeoutSeconds int `env:"JOB_TIMEOUT_SECONDS" envDefault:"5"`

	// ReclaimAfterMinutes: locked_at がこの分数を超えたジョブを queued に
	// 戻す閾値。worker.md 既定 5 分。
	ReclaimAfterMinutes int `env:"RECLAIM_AFTER_MINUTES" envDefault:"5"`

	// LLMConfigPath: llm.yaml のパス。相対なら現在 working dir 基準で解決。
	// Worker を docker run する場合は /app/llm.yaml 等を環境変数で渡す想定。
	LLMConfigPath string `env:"LLM_CONFIG_PATH" envDefault:"llm.yaml"`

	// LLM プロバイダ API キー (provider ごとに別環境変数)。
	// 空のままでも Load は成功する (実際に該当プロバイダを使わない構成もある)。
	// 起動時の必須チェックは llm.New / provider.New 側で行う。
	GoogleAPIKey    string `env:"GOOGLE_API_KEY"`
	AnthropicAPIKey string `env:"ANTHROPIC_API_KEY"`
	OpenAIAPIKey    string `env:"OPENAI_API_KEY"`

	// LLM: llm.yaml から読み込んだ providers: ブロック。
	// env タグは付かない (yaml 由来のため)。
	LLM LLMProviders
}

// Load: 環境変数と llm.yaml を読んで Config を返す。
//
// 失敗パターン (起動時 fail-fast):
//   - 必須環境変数 (DATABASE_URL) 欠落 -> caarlos0/env のエラー
//   - llm.yaml が見つからない -> ErrLLMYAMLMissing を wrap
//   - llm.yaml が壊れている -> yaml.Unmarshal のエラー
func Load() (*Config, error) {
	cfg := &Config{}
	if err := env.Parse(cfg); err != nil {
		return nil, fmt.Errorf("config: env parse failed: %w", err)
	}
	if err := loadLLMYAML(cfg); err != nil {
		return nil, err
	}
	return cfg, nil
}

// loadLLMYAML: cfg.LLMConfigPath を読み込んで cfg.LLM に詰める。
// パスが相対の場合は呼び出し時の working dir 基準で解決する。
func loadLLMYAML(cfg *Config) error {
	path := cfg.LLMConfigPath
	if !filepath.IsAbs(path) {
		// 絶対化しておくとログに残しやすい (どの llm.yaml を読んだか追える)。
		abs, err := filepath.Abs(path)
		if err == nil {
			path = abs
		}
	}
	data, err := os.ReadFile(path) //nolint:gosec // path は env から / 設定値、サンドボックス外で読む正規ファイル
	if err != nil {
		if os.IsNotExist(err) {
			return fmt.Errorf("%w: %s", ErrLLMYAMLMissing, path)
		}
		return fmt.Errorf("config: read llm.yaml at %s: %w", path, err)
	}
	var yf llmYAMLFile
	if err := yaml.Unmarshal(data, &yf); err != nil {
		return fmt.Errorf("config: unmarshal llm.yaml at %s: %w", path, err)
	}
	cfg.LLM = yf.Providers
	return nil
}
