// orchestrator.go: ジョブ消費ループの本体。
//
// 役割:
//   - LISTEN/NOTIFY + 30 秒ポーリングのハイブリッドで claim を試行
//   - job.Type に応じてハンドラを dispatch (problem.generate / submission.grade)
//   - ハンドラの結果に応じて MarkSucceeded / MarkFailed / MarkDead
//   - 定期的に ReclaimStuck を呼んでスタックジョブを回収
//
// 並列性:
//   - 上位 (cmd/grading/main.go) が Concurrency 個の goroutine から Run を
//     並列起動する。Postgres 側で SELECT FOR UPDATE SKIP LOCKED により
//     ジョブの取り合いは安全に解決される
//   - reclaim ループは別 goroutine 1 本だけ走る (Orchestrator.RunReclaim)
//
// 1 Orchestrator = 1 queue = 1 種類のジョブを処理する (R1-5 で確定)。
// generation 用と grading 用は main.go から別インスタンスとして並行起動する
// (ADR 0040、R7 で generation を別 Worker に切り出す時に main.go から外す
// だけで済むよう構造的に分離してある)。
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
//
// Generator / Judge は問題生成 Orchestrator でしか使わないため optional
// (R1-5 で採点側 Orchestrator は nil で渡せる、ADR 0040 / 採点フローは
// sandbox + DB だけで完結する)。
type Deps struct {
	Pool      *pgxpool.Pool
	Generator *ProblemGenerator
	Sandbox   *sandbox.Runner
	Judge     *judge.Judge
	WorkerID  string
	// Queue: 取得対象の論理キュー名 (job.GenerationQueue / job.GradingQueue)。
	Queue string
	// PollInterval: 取りこぼし対策のポーリング間隔 (既定 30s)。
	PollInterval time.Duration
	// ReclaimInterval: スタックジョブ回収の頻度 (既定 1 分)。
	ReclaimInterval time.Duration
	// ReclaimAfter: locked_at がこの時間より古いものを reclaim 対象に。
	ReclaimAfter time.Duration
}

// jobHandler: Orchestrator が dispatch する 1 ジョブ種別あたりのハンドラ interface。
//
//   - Type:   このハンドラが受け持つ job.Type 値 (dispatch のキー)。
//   - Handle: ジョブ 1 件の本処理。成功なら nil、失敗なら error を返す
//     (orchestrator が MarkFailed / MarkDead に振り分ける)。
//   - OnDead: MaxAttempts 到達 or 不可逆エラーで dead 確定した時に呼ばれる。
//     関連ドメイン行 (generation_requests / submissions) を failed に
//     遷移させる責務をハンドラ側に持たせる (orchestrator は generic に保つ)。
//     lastErr は dead を引き起こした最後の Handle エラー。ハンドラ側で
//     failure_reason 分類等に使う（採点側のように使わない場合は無視してよい）。
type jobHandler interface {
	Type() string
	Handle(ctx context.Context, j *job.Job) error
	OnDead(ctx context.Context, j *job.Job, lastErr error)
}

// Orchestrator: ジョブ消費ループの本体。
type Orchestrator struct {
	deps     Deps
	handler  jobHandler
	listener *job.Listener
}

// New: 問題生成 (problem.generate) 用の Orchestrator を組み立てる。
// 採点用は NewForGrading を使う。
func New(ctx context.Context, deps Deps) (*Orchestrator, error) {
	handler := &problemGenerateHandler{
		pool:      deps.Pool,
		store:     newPgGenerationStore(deps.Pool),
		generator: deps.Generator,
		sandbox:   deps.Sandbox,
		judge:     deps.Judge,
	}
	if deps.Queue == "" {
		deps.Queue = job.GenerationQueue
	}
	return newWithHandler(ctx, deps, handler)
}

// NewForGrading: 採点 (submission.grade) 用の Orchestrator を組み立てる (R1-5)。
//
// Generator / Judge は採点フローでは使わないため Deps.Generator / Deps.Judge は
// 無視して良い (採点は sandbox + DB だけで完結する、grading.md)。
func NewForGrading(ctx context.Context, deps Deps) (*Orchestrator, error) {
	handler := &submissionGradeHandler{
		pool:    deps.Pool,
		store:   newPgGradingStore(deps.Pool),
		sandbox: deps.Sandbox,
	}
	if deps.Queue == "" {
		deps.Queue = job.GradingQueue
	}
	return newWithHandler(ctx, deps, handler)
}

// newWithHandler: 任意の jobHandler を差し込める内部 ctor。
// 本番経路は New / NewForGrading、テストでは fake handler を渡して
// orchestrator の retry/dead 経路を検証する。
func newWithHandler(ctx context.Context, deps Deps, handler jobHandler) (*Orchestrator, error) {
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
		deps:     deps,
		handler:  handler,
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
			slog.InfoContext(ctx, "orchestrator: shutting down", "queue", o.deps.Queue)
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
		slog.ErrorContext(ctx, "orchestrator: claim failed", "queue", o.deps.Queue, "err", err.Error())
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

// dispatch: job.Type がハンドラの受け持ち値と一致するかを確認して Handle を呼ぶ。
// 一致しなければ MarkDead 相当 (リトライしても直らない) として error を返す。
//
// 1 Orchestrator = 1 queue = 1 type の運用なので、本来 queue で絞れているはずだが、
// 運用事故 (Backend 側 _JOB_QUEUE と _JOB_TYPE の対応が壊れる等) で別 type が混入した
// 時に retry し続けるのを防ぐため明示的に検査する。
func (o *Orchestrator) dispatch(ctx context.Context, j *job.Job) error {
	if j.Type == o.handler.Type() {
		return o.handler.Handle(ctx, j)
	}
	return fmt.Errorf("orchestrator: unexpected job type %q (queue=%s, handler expects %q)", j.Type, o.deps.Queue, o.handler.Type())
}

// handleHandlerError: ハンドラ失敗時の MarkFailed / MarkDead 振り分け。
//
// 判定:
//   - ErrInvalidProblem を wrap している: リトライ可能。MarkFailed で
//     run_at バックオフ。MaxAttempts 到達なら自動 MarkDead + 関連ドメイン行を failed に。
//   - それ以外 (DB / LLM unauthorized / 未知 type 等): リトライ不要なので即 MarkDead。
//
// 関連ドメイン行 (generation_requests / submissions) の failed 遷移は
// ハンドラ側の OnDead に委譲する (Orchestrator は generic に保つ)。
func (o *Orchestrator) handleHandlerError(ctx context.Context, j *job.Job, handlerErr error) {
	logger := slog.With(
		"job_id", j.ID,
		"queue", o.deps.Queue,
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
		// ハンドラ固有の dead 時処理 (generation_requests / submissions を failed に)。
		// handlerErr は dead を引き起こした最後の error。問題生成側は
		// classifyFailureReason で具体タグに分類して DB に書く。
		// 失敗は本質的でないため警告ログのみで継続 (jobs テーブルに記録は残る)。
		o.handler.OnDead(ctx, j, handlerErr)
		return
	}

	logger.WarnContext(ctx, "orchestrator: marking job failed for retry")
	if err := job.MarkFailed(ctx, o.deps.Pool, j.ID, j.Attempts, handlerErr.Error()); err != nil {
		logger.ErrorContext(ctx, "orchestrator: mark failed failed", "err2", err.Error())
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
