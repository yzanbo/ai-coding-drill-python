// 問題生成 Worker のエントリポイント（R0-8 で配置した skeleton）。
//
// 現状は jobs polling loop の最小骨格のみ。実際のジョブ取得
// （SELECT FOR UPDATE SKIP LOCKED + LISTEN/NOTIFY）/ 生成 LLM 呼び出し /
// 模範解答 sandbox 検証 / judge 評価は R7（問題生成 Worker 機能実装）で実装する。
// 配置・パッケージ規約は ../../../../../.claude/rules/worker.md を参照。
package main

import (
	// context: ループのキャンセル・タイムアウトを伝える仕組み。SIGTERM 受信時に
	//          走行中のジョブを途中で打ち切るために使う。
	// log/slog: 標準の構造化ログ（JSON 出力）。R4 で trace_id を自動付与する想定。
	// os: SIGINT / SIGTERM を受け取るためのプロセス制御。
	// os/signal: シグナルを context に紐付ける signal.NotifyContext を使う。
	// syscall: SIGINT / SIGTERM の定数を取り出すため。
	// time: ポーリング間隔の指定に使う time.Ticker。
	"context"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"
)

func main() {
	// signal.NotifyContext: Ctrl+C（SIGINT）と SIGTERM を受け取ると ctx を Done にする。
	// グレースフルシャットダウンの起点。
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	logger.InfoContext(ctx, "generation worker started (skeleton)")

	// 最小 polling ループ。実ジョブ取得は未実装で 30 秒ごとに heartbeat ログだけ出す。
	// R7 で claim → generate → validate → judge → complete の本実装に差し替える。
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			logger.InfoContext(ctx, "generation worker shutting down")
			return
		case <-ticker.C:
			// TODO(R7): claimNextJob + generateProblem + validateInSandbox + judgeQuality + complete
			logger.InfoContext(ctx, "tick (no jobs yet)")
		}
	}
}
