// orchestrator.go: ジョブ消費ループの本体。
//
// 役割:
//   - LISTEN/NOTIFY + 30 秒ポーリングのハイブリッドで claim を試行
//   - job.Type に応じてハンドラを dispatch (現状 "problem.generate" のみ)
//   - ハンドラの結果に応じて MarkSucceeded / MarkFailed / MarkDead
//   - 定期的に ReclaimStuck を呼んでスタックジョブを回収
//
// 並列性:
//   - 上位 (cmd/grading/main.go) が Concurrency 個の goroutine から Run を
//     並列起動する。Postgres 側で SELECT FOR UPDATE SKIP LOCKED により
//     ジョブの取り合いは安全に解決される
//   - reclaim ループは別 goroutine 1 本だけ走る (Orchestrator.RunReclaim)
package grading

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/job"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/judge"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/sandbox"
)

// Deps: Orchestrator が必要とする依存を 1 個の struct で受け取る (DI)。
type Deps struct {
	Pool      *pgxpool.Pool
	Generator *ProblemGenerator
	Sandbox   *sandbox.Runner
	Judge     *judge.Judge
	WorkerID  string
	// Queue: 取得対象の論理キュー名 (job.GenerationQueue)。
	Queue string
	// PollInterval: 取りこぼし対策のポーリング間隔 (既定 30s)。
	PollInterval time.Duration
	// ReclaimInterval: スタックジョブ回収の頻度 (既定 1 分)。
	ReclaimInterval time.Duration
	// ReclaimAfter: locked_at がこの時間より古いものを reclaim 対象に。
	ReclaimAfter time.Duration
}

// Orchestrator: ジョブ消費ループの本体。
type Orchestrator struct {
	deps     Deps
	handler  *problemGenerateHandler
	listener *job.Listener
}

// New: Deps から Orchestrator を組み立てる。
// listener は内部で確立する (Deps.Pool が必要)。
func New(ctx context.Context, deps Deps) (*Orchestrator, error) {
	if deps.PollInterval <= 0 {
		deps.PollInterval = 30 * time.Second
	}
	if deps.ReclaimInterval <= 0 {
		deps.ReclaimInterval = 1 * time.Minute
	}
	if deps.ReclaimAfter <= 0 {
		deps.ReclaimAfter = 5 * time.Minute
	}
	if deps.Queue == "" {
		deps.Queue = job.GenerationQueue
	}
	listener, err := job.NewListener(ctx, deps.Pool)
	if err != nil {
		return nil, err
	}
	return &Orchestrator{
		deps: deps,
		handler: &problemGenerateHandler{
			pool:      deps.Pool,
			generator: deps.Generator,
			sandbox:   deps.Sandbox,
			judge:     deps.Judge,
		},
		listener: listener,
	}, nil
}

// Close: listener 接続を閉じる。
func (o *Orchestrator) Close() error {
	return o.listener.Close()
}

// Run: 1 goroutine 分の claim ループ。ctx.Done() で抜ける。
//
// 通知 / poll tick が来るたびに ClaimNext を試行し、取れたら処理 → 結果書き戻し。
// 取れなかった場合は次の通知 or poll を待つ。
func (o *Orchestrator) Run(ctx context.Context) {
	poll := time.NewTicker(o.deps.PollInterval)
	defer poll.Stop()

	for {
		select {
		case <-ctx.Done():
			slog.InfoContext(ctx, "orchestrator: shutting down")
			return
		case <-o.listener.Channel():
			// NOTIFY 受信
		case <-poll.C:
			// 30 秒ポーリング (取りこぼし対策)
		}

		o.tryProcessOne(ctx)
	}
}

// tryProcessOne: 1 件 claim を試みて、取れたら処理 → 結果書き戻し。
//
// ClaimNext が ErrNoJob なら no-op (次の通知 / poll を待つ)。
// それ以外のエラーはログのみで継続 (transient DB エラー等は次の poll で再試行)。
func (o *Orchestrator) tryProcessOne(ctx context.Context) {
	j, err := job.ClaimNext(ctx, o.deps.Pool, o.deps.Queue, o.deps.WorkerID)
	if err != nil {
		if errors.Is(err, job.ErrNoJob) {
			return
		}
		slog.ErrorContext(ctx, "orchestrator: claim failed", "err", err.Error())
		return
	}

	if err := o.dispatch(ctx, j); err != nil {
		o.handleHandlerError(ctx, j, err)
		return
	}
	if err := job.MarkSucceeded(ctx, o.deps.Pool, j.ID, nil); err != nil {
		slog.ErrorContext(ctx, "orchestrator: mark succeeded failed", "job_id", j.ID, "err", err.Error())
	}
}

// dispatch: job.Type に応じたハンドラを呼ぶ。
// 未知 type は MarkDead 相当 (リトライしても直らない) として error を返す。
func (o *Orchestrator) dispatch(ctx context.Context, j *job.Job) error {
	switch j.Type {
	case job.TypeProblemGenerate:
		return o.handler.Handle(ctx, j)
	default:
		return fmt.Errorf("orchestrator: unknown job type %q", j.Type)
	}
}

// handleHandlerError: ハンドラ失敗時の MarkFailed / MarkDead 振り分け。
//
// 判定:
//   - ErrInvalidProblem を wrap している: リトライ可能。MarkFailed で
//     run_at バックオフ。MaxAttempts 到達なら自動 MarkDead + generation_requests
//     を failed に。
//   - それ以外 (DB / LLM unauthorized / 未知 type 等): 既にリトライ不要なので
//     即 MarkDead + generation_requests failed
func (o *Orchestrator) handleHandlerError(ctx context.Context, j *job.Job, handlerErr error) {
	logger := slog.With(
		"job_id", j.ID,
		"attempts", j.Attempts,
		"err", handlerErr.Error(),
	)

	retryable := errors.Is(handlerErr, ErrInvalidProblem)
	dead := !retryable || job.IsTerminalAttempt(j.Attempts)

	if dead {
		logger.WarnContext(ctx, "orchestrator: marking job dead")
		if err := job.MarkDead(ctx, o.deps.Pool, j.ID, handlerErr.Error()); err != nil {
			logger.ErrorContext(ctx, "orchestrator: mark dead failed", "err2", err.Error())
		}
		// generation_requests を failed に。payload から request_id を取り直す
		// 失敗は本質的でないため警告ログのみで継続 (request_id parse 失敗時)。
		o.failGenerationRequest(ctx, j)
		return
	}

	logger.WarnContext(ctx, "orchestrator: marking job failed for retry")
	if err := job.MarkFailed(ctx, o.deps.Pool, j.ID, j.Attempts, handlerErr.Error()); err != nil {
		logger.ErrorContext(ctx, "orchestrator: mark failed failed", "err2", err.Error())
	}
}

// failGenerationRequest: payload から request_id を抜き出して generation_requests を
// failed に遷移する。payload parse 失敗は警告ログのみで握り潰す (DLQ 側の jobs
// テーブルに残っているので運用追跡可能)。
func (o *Orchestrator) failGenerationRequest(ctx context.Context, j *job.Job) {
	if j.Type != job.TypeProblemGenerate {
		return
	}
	var payload struct {
		GenerationRequestID string `json:"generationRequestId"`
	}
	if err := jsonUnmarshal(j.Payload, &payload); err != nil {
		slog.WarnContext(ctx, "orchestrator: cannot parse payload to fail generation_request", "job_id", j.ID, "err", err.Error())
		return
	}
	reqID, err := parseUUID(payload.GenerationRequestID)
	if err != nil {
		slog.WarnContext(ctx, "orchestrator: bad generation_request_id", "job_id", j.ID, "id", payload.GenerationRequestID)
		return
	}
	if err := markGenerationRequestFailed(ctx, o.deps.Pool, reqID); err != nil {
		slog.WarnContext(ctx, "orchestrator: failed to mark generation_request failed", "job_id", j.ID, "err", err.Error())
	}
}

// RunReclaim: 1 goroutine 分の reclaim ループ。ctx.Done() で抜ける。
// 上位 (cmd/grading/main.go) が 1 本だけ起動する想定 (並列稼働の必要無し)。
func (o *Orchestrator) RunReclaim(ctx context.Context) {
	t := time.NewTicker(o.deps.ReclaimInterval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			ids, err := job.ReclaimStuck(ctx, o.deps.Pool, o.deps.ReclaimAfter)
			if err != nil {
				slog.ErrorContext(ctx, "orchestrator: reclaim failed", "err", err.Error())
				continue
			}
			if len(ids) > 0 {
				slog.InfoContext(ctx, "orchestrator: reclaimed stuck jobs", "count", len(ids), "ids", ids)
			}
		}
	}
}
