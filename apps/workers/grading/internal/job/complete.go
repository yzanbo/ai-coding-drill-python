// complete.go: ジョブ処理結果を jobs テーブルに書き戻す。
//
// 3 つの遷移を扱う:
//   - MarkSucceeded: state='succeeded' + result (任意の JSONB) を書き込む
//   - MarkFailed   : リトライ可能な失敗。attempts < MaxAttempts なら
//     state='queued' + run_at を未来時刻 (バックオフ) に
//     押し戻す。MaxAttempts 到達なら state='dead' に落とす
//   - MarkDead     : リトライ不可能なエラー (LLM unauthorized / コード
//     の compile error 等) を即 dead に落とす
//
// バックオフスケジュール: ADR 0046 の「10s → 60s」を踏襲。
// attempts=1 失敗 → 10s 後再実行、attempts=2 失敗 → 60s 後再実行、
// attempts=3 で MaxAttempts に到達したら dead。
package job

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// backoffSchedule: attempts → 次回 run_at までの待ち時間。
// インデックスは「失敗時点の attempts」を 0-origin で参照する想定:
//
//	attempts=1 失敗 → backoffSchedule[0] = 10s
//	attempts=2 失敗 → backoffSchedule[1] = 60s
//
// MaxAttempts (=3) を超える index は使わない (= dead 落とし)。
var backoffSchedule = []time.Duration{
	10 * time.Second,
	60 * time.Second,
}

// backoffFor: 失敗後の attempts 値から次回 run_at までの待ち時間を返す。
// インデックスが範囲外 (= MaxAttempts 到達) なら 0 を返すが、呼び出し側で
// MaxAttempts 超過判定して MarkDead 経路に流すため本来呼ばれない。
func backoffFor(attempts int) time.Duration {
	idx := attempts - 1
	if idx < 0 {
		idx = 0
	}
	if idx >= len(backoffSchedule) {
		return backoffSchedule[len(backoffSchedule)-1]
	}
	return backoffSchedule[idx]
}

// MarkSucceeded: ジョブを done として完了させる。
//
// result は orchestrator 側で「produced_problem_id 等の任意 JSONB」を
// 詰める想定。nil なら空 JSON (`null`) が書かれる。
func MarkSucceeded(ctx context.Context, pool *pgxpool.Pool, jobID int64, result any) error {
	resultJSON, err := json.Marshal(result)
	if err != nil {
		return fmt.Errorf("job: marshal result: %w", err)
	}
	_, err = pool.Exec(ctx, `
UPDATE jobs SET
  state = 'succeeded',
  locked_at = NULL,
  locked_by = NULL,
  last_error = NULL,
  result = $2::jsonb,
  updated_at = NOW()
WHERE id = $1;
`, jobID, resultJSON)
	if err != nil {
		return fmt.Errorf("job: mark succeeded: %w", err)
	}
	return nil
}

// AttemptError: jobs.attempt_errors JSONB array の 1 要素（R1-7-3）。
// 各試行（MarkFailed / MarkDead）のたびに 1 件 append される。
// failureReason は呼び出し側が分類したタグ（ハンドラ固有の classifyFailureReason
// 経由、e.g. grading の "llm_rate_limit" / "sandbox_failed"）。
// 試行ごとに「何が原因で失敗したか」を残し、UI でユーザーがデバッグできるようにする。
type AttemptError struct {
	Attempt       int       `json:"attempt"`
	FailureReason string    `json:"failureReason"`
	Message       string    `json:"message"`
	FailedAt      time.Time `json:"failedAt"`
}

// attemptErrorMaxMessageLen: message フィールドの長さ上限（バイト）。
// スタックトレースや LLM 応答本文が混入した時に DB / API レスポンスを膨らませない
// ための安全弁。超過分は ASCII truncation で切る。
const attemptErrorMaxMessageLen = 1000

// buildAttemptError: append 用の 1 要素を組み立てる。failureReason が空文字なら
// "unclassified" にフォールバックする（呼び出し側のハンドラが分類関数を持たない
// ケース、e.g. submission.grade）。
func buildAttemptError(attempt int, failureReason, message string) AttemptError {
	if failureReason == "" {
		failureReason = "unclassified"
	}
	if len(message) > attemptErrorMaxMessageLen {
		message = message[:attemptErrorMaxMessageLen]
	}
	return AttemptError{
		Attempt:       attempt,
		FailureReason: failureReason,
		Message:       message,
		FailedAt:      time.Now().UTC(),
	}
}

// MarkFailed: リトライ可能な失敗を記録する。
//
// attempts < MaxAttempts なら state='queued' に戻し、run_at を
// backoffSchedule に従って未来に押し戻す。
// MaxAttempts 到達なら state='dead' に落とす (= 再取得不能、運用 DLQ 相当)。
//
// failureReason は呼び出し側ハンドラが分類したタグ（空文字なら "unclassified"）。
// attempt_errors JSONB array にこの試行のエラー詳細を append する。
//
// 呼び出し側は claim 時点の Job.Attempts を渡す (= claim で +1 された後の値)。
func MarkFailed(ctx context.Context, pool *pgxpool.Pool, jobID int64, attempts int, lastErr, failureReason string) error {
	entry := buildAttemptError(attempts, failureReason, lastErr)
	entryJSON, err := json.Marshal(entry)
	if err != nil {
		return fmt.Errorf("job: marshal attempt error: %w", err)
	}
	if IsTerminalAttempt(attempts) {
		return markDead(ctx, pool, jobID, lastErr, entryJSON)
	}
	backoff := backoffFor(attempts)
	_, err = pool.Exec(ctx, `
UPDATE jobs SET
  state = 'queued',
  locked_at = NULL,
  locked_by = NULL,
  last_error = $2,
  attempt_errors = attempt_errors || $4::jsonb,
  run_at = NOW() + $3::interval,
  updated_at = NOW()
WHERE id = $1;
`, jobID, lastErr, fmt.Sprintf("%d seconds", int64(backoff.Seconds())), entryJSON)
	if err != nil {
		return fmt.Errorf("job: mark failed (retry): %w", err)
	}
	return nil
}

// MarkDead: リトライ不可能なエラーを記録して即 dead に落とす。
// LLM unauthorized 等の「リトライしても直らない」エラー専用。
func MarkDead(ctx context.Context, pool *pgxpool.Pool, jobID int64, lastErr, failureReason string) error {
	// attempt 番号は呼び出し側で「最後の試行回」を渡せないため、便宜的に 0 を入れる。
	// 実用上 OnDead のテストでは即 dead 経路の attempt 数は jobs.attempts で別途
	// 観測できるので、要素単体の attempt は 0 で問題ない（UI 側は jobs.attempts と
	// 突き合わせて表示）。
	entry := buildAttemptError(0, failureReason, lastErr)
	entryJSON, err := json.Marshal(entry)
	if err != nil {
		return fmt.Errorf("job: marshal attempt error: %w", err)
	}
	return markDead(ctx, pool, jobID, lastErr, entryJSON)
}

// markDead: 内部実装。state='dead' に遷移 + locked_at をクリア + attempt_errors に append。
func markDead(ctx context.Context, pool *pgxpool.Pool, jobID int64, lastErr string, entryJSON []byte) error {
	_, err := pool.Exec(ctx, `
UPDATE jobs SET
  state = 'dead',
  locked_at = NULL,
  locked_by = NULL,
  last_error = $2,
  attempt_errors = attempt_errors || $3::jsonb,
  updated_at = NOW()
WHERE id = $1;
`, jobID, lastErr, entryJSON)
	if err != nil {
		return fmt.Errorf("job: mark dead: %w", err)
	}
	return nil
}
