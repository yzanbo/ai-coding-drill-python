// 採点 Worker のエントリポイント (R1-3 で問題生成 consume ループを結線した版)。
//
// 現状の実装:
//   - internal/config で環境変数 + llm.yaml を読み込む
//   - internal/db で pgxpool を初期化
//   - internal/llm/google を Register して llm.New で Provider を取得
//   - internal/grading の Orchestrator を起動 (claim/dispatch/reclaim)
//   - problem.generate ハンドラは LLM 生成 → sandbox 検証 → judge 評価 →
//     problems INSERT
//
// R1〜R6 は本 Worker が問題生成も兼務する (ADR 0040)。R7 以降に
// apps/workers/generation/ に切り出す予定。
//
// 配置・パッケージ規約は ../../../../.claude/rules/worker.md を参照。
package main

import (
	"context"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"sync"
	"syscall"
	"time"

	"github.com/joho/godotenv"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/config"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/db"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/grading"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/judge"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/llm"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/llm/google"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/sandbox"
)

func main() {
	// signal.NotifyContext: Ctrl+C (SIGINT) と SIGTERM を受け取ると ctx を Done にする。
	// グレースフルシャットダウンの起点。
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	// .env をプロセス開始直後に load する (cwd の .env を見る、存在しなければ silent skip)。
	// production Docker 起動では .env が無く OS env / コンテナ env 経由で値が入る想定。
	// 既に設定済みの環境変数は上書きしないため、開発時の .env と prod の env が
	// 衝突しても prod が勝つ (godotenv.Load の仕様)。
	_ = godotenv.Load()

	// 設定読み込み: 失敗したら fail-fast で終了する。
	// DATABASE_URL 欠落 / llm.yaml 不在 / yaml 文法エラーがここで弾かれる。
	cfg, err := config.Load()
	if err != nil {
		logger.ErrorContext(ctx, "config load failed", "err", err.Error())
		os.Exit(1)
	}

	// WorkerID の hostname フォールバック: WORKER_ID が未設定なら os.Hostname() を当てる。
	// 未設定のままだと jobs.locked_by が空文字で書き込まれ、ジョブを誰が持っているか
	// 追跡不能になる。ホスト名取得失敗時は明示的にプレースホルダを置いて起動を続ける
	// (Worker 1 個ローカル開発時に Hostname() が空を返すケースに備える)。
	if cfg.WorkerID == "" {
		if hostname, hostErr := os.Hostname(); hostErr == nil && hostname != "" {
			cfg.WorkerID = hostname
		} else {
			cfg.WorkerID = "unknown-host"
		}
	}

	// 起動時に読まれた llm.yaml の絶対パスをログに残す。
	// 相対パスで起動された時にどのファイルが採用されたか operator が即時確認できる。
	// 失敗時は元の (相対の可能性がある) path をそのまま使う。
	llmConfigPath := cfg.LLMConfigPath
	if abs, absErr := filepath.Abs(llmConfigPath); absErr == nil {
		llmConfigPath = abs
	}

	// LLM プロバイダ抽象化レイヤの結線 (ADR 0007 / 0049):
	//   1. Register: google sub-package のファクトリを llm package の登録 map に入れる
	//   2. New: cfg.LLM.Generation.Provider の値で factory を引いて Provider を組み立てる
	// 循環インポート回避のため Register / New 分離 (internal/llm/new.go の registration pattern)。
	llm.Register(google.Name, google.New)
	provider, err := llm.New(buildLLMConfig(cfg))
	if err != nil {
		logger.ErrorContext(ctx, "llm provider init failed", "err", err.Error())
		os.Exit(1)
	}

	// DB プール: 業務 SQL (jobs / problems / generation_requests) で共有する。
	pool, err := db.NewPool(ctx, cfg.DatabaseURL)
	if err != nil {
		logger.ErrorContext(ctx, "db pool init failed", "err", err.Error())
		os.Exit(1)
	}
	defer pool.Close()

	// 問題生成 prompt YAML を読み込む。Worker 起動時に fail-fast。
	// パスは config.LLMConfigPath と同じディレクトリ規約 (cwd 基準 or 絶対パス)。
	// 本 PR では prompts/ 配置を固定 (R7 の generation worker 切り出しでパス変える)。
	genPrompt, err := grading.LoadGenerationPrompt(resolvePromptPath("prompts/generation/problem-gen.v1.yaml"))
	if err != nil {
		logger.ErrorContext(ctx, "generation prompt load failed", "err", err.Error())
		os.Exit(1)
	}
	judgePrompt, err := judge.LoadPrompt(resolvePromptPath("prompts/judge/quality.v1.yaml"))
	if err != nil {
		logger.ErrorContext(ctx, "judge prompt load failed", "err", err.Error())
		os.Exit(1)
	}

	// Sandbox runner: Docker daemon に接続できなければ fail-fast。
	// JobTimeoutSeconds はサンドボックス単発実行のタイムアウトとして適用する
	// (生成ジョブ全体 180 秒の内訳としては短い方の値)。
	sb, err := sandbox.NewRunner(sandbox.Options{
		Image:   cfg.SandboxImage,
		Timeout: time.Duration(cfg.JobTimeoutSeconds) * time.Second,
	})
	if err != nil {
		logger.ErrorContext(ctx, "sandbox runner init failed", "err", err.Error())
		os.Exit(1)
	}
	defer func() {
		if err := sb.Close(); err != nil {
			logger.WarnContext(ctx, "sandbox close", "err", err.Error())
		}
	}()

	// orchestrator: claim/dispatch/complete + reclaim を担う。
	orch, err := grading.New(ctx, grading.Deps{
		Pool:         pool,
		Generator:    grading.NewProblemGenerator(genPrompt, provider),
		Sandbox:      sb,
		Judge:        judge.New(judgePrompt, provider),
		WorkerID:     cfg.WorkerID,
		ReclaimAfter: time.Duration(cfg.ReclaimAfterMinutes) * time.Minute,
	})
	if err != nil {
		logger.ErrorContext(ctx, "orchestrator init failed", "err", err.Error())
		os.Exit(1)
	}
	defer func() {
		if err := orch.Close(); err != nil {
			logger.WarnContext(ctx, "orchestrator close", "err", err.Error())
		}
	}()

	logger.InfoContext(ctx, "grading worker started",
		"worker_id", cfg.WorkerID,
		"concurrency", cfg.Concurrency,
		"sandbox_image", cfg.SandboxImage,
		"llm_config_path", llmConfigPath,
		"llm_provider", provider.Name(),
		"llm_generation_model", cfg.LLM.Generation.Model,
		"llm_judge_model", cfg.LLM.Judge.Model,
		"generation_prompt", genPrompt.Path(),
		"generation_prompt_hash", genPrompt.Hash(),
		"judge_prompt", judgePrompt.Path(),
		"judge_prompt_hash", judgePrompt.Hash(),
	)

	// goroutine 群: Concurrency 本の claim ループ + 1 本の reclaim ループ。
	// 全 in-flight ジョブの完了を待ってから main を抜ける (グレースフルシャットダウン)。
	var wg sync.WaitGroup
	// for range int (Go 1.22+): i 変数が不要なため `i := 0; i < N; i++` を簡略化。
	for range cfg.Concurrency {
		wg.Add(1)
		go func() {
			defer wg.Done()
			orch.Run(ctx)
		}()
	}
	wg.Add(1)
	go func() {
		defer wg.Done()
		orch.RunReclaim(ctx)
	}()

	<-ctx.Done()
	logger.InfoContext(ctx, "grading worker shutting down, waiting in-flight jobs")
	wg.Wait()
	logger.InfoContext(ctx, "grading worker stopped")
}

// resolvePromptPath: prompt の相対パスを cwd 基準で解決する。
// 既に絶対パスならそのまま返す。
func resolvePromptPath(rel string) string {
	if filepath.IsAbs(rel) {
		return rel
	}
	abs, err := filepath.Abs(rel)
	if err != nil {
		return rel
	}
	return abs
}

// buildLLMConfig: config.Config から llm.Config に詰め直す。
//
// internal/config は worker.md Layer 0 制約で llm package を import できないため、
// LLM 設定は config 側で「ロール別 RoleProvider + provider 別 API キー」の
// 中立 struct で保持し、cmd 層 (本 main) でここに変換する。
func buildLLMConfig(cfg *config.Config) llm.Config {
	return llm.Config{
		Generation: llm.RoleConfig{
			Provider: cfg.LLM.Generation.Provider,
			Model:    cfg.LLM.Generation.Model,
		},
		Regeneration: llm.RoleConfig{
			Provider: cfg.LLM.Regeneration.Provider,
			Model:    cfg.LLM.Regeneration.Model,
		},
		Judge: llm.RoleConfig{
			Provider: cfg.LLM.Judge.Provider,
			Model:    cfg.LLM.Judge.Model,
		},
		// APIKeys: provider 別 API キーを map に集約。
		// 空文字でも map には入れておく (provider 側で「空なら ErrUnauthorized」を返す)。
		APIKeys: map[string]string{
			"google":    cfg.GoogleAPIKey,
			"anthropic": cfg.AnthropicAPIKey,
			"openai":    cfg.OpenAIAPIKey,
		},
	}
}
