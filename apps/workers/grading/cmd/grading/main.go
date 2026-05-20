// 採点 Worker のエントリポイント (R0-8 で配置した skeleton + R1-2 で
// LLM プロバイダ抽象化レイヤを結線した版)。
//
// 現状の実装:
//   - internal/config で環境変数 + llm.yaml を読み込む
//   - internal/llm/google を Register して llm.New で Provider を取得
//   - 30 秒ごとに heartbeat ログを出すだけの polling loop
//
// 未実装 (R1-2 後半以降):
//   - jobs テーブルからの SELECT FOR UPDATE SKIP LOCKED でのジョブ取得
//   - LISTEN/NOTIFY 統合 / Docker サンドボックス起動 / 結果書き戻し
//   - judge LLM 呼び出し (orchestrator が provider を使う)
//
// 配置・パッケージ規約は ../../../../.claude/rules/worker.md を参照。
package main

import (
	// context: ループのキャンセル・タイムアウトを伝える仕組み。
	// log/slog: 標準の構造化ログ (JSON 出力)。
	// os: SIGINT / SIGTERM を受け取るためのプロセス制御。
	// os/signal: シグナルを context に紐付ける signal.NotifyContext を使う。
	// syscall: SIGINT / SIGTERM の定数を取り出すため。
	// time: ポーリング間隔の指定に使う time.Ticker。
	"context"
	"log/slog"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/joho/godotenv"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/config"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/llm"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/llm/google"
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

	logger.InfoContext(ctx, "grading worker started",
		"worker_id", cfg.WorkerID,
		"concurrency", cfg.Concurrency,
		"sandbox_image", cfg.SandboxImage,
		"llm_config_path", llmConfigPath,
		"llm_provider", provider.Name(),
		"llm_generation_model", cfg.LLM.Generation.Model,
		"llm_judge_model", cfg.LLM.Judge.Model,
	)

	// 最小 polling ループ。実ジョブ取得は未実装で 30 秒ごとに heartbeat ログだけ出す。
	// R1-2 後半 / R1-3 で claim -> process -> complete の本実装に差し替える。
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			logger.InfoContext(ctx, "grading worker shutting down")
			return
		case <-ticker.C:
			// TODO(R1-2 後半): claimNextJob + processJob + completeJob
			logger.InfoContext(ctx, "tick (no jobs yet)")
		}
	}
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
