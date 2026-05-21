// Package job: Postgres jobs テーブルに対するキュー操作 (claim / listener /
// reclaim / complete) を集める。pgx を直接触るのは internal/db/、本 package
// は db.Pool を受け取って SQL を打つだけ。
//
// 4 ファイル構成:
//   - types.go    : Job struct / 共通定数 / sentinel エラー
//   - claim.go    : SELECT FOR UPDATE SKIP LOCKED で 1 件取り state='running' に
//   - listener.go : LISTEN new_job を貼って通知を channel に流す
//   - reclaim.go  : locked_at < now() - N min を queued に戻す
//   - complete.go : 成功 (done) / 失敗 (queued リトライ or dead) の遷移
//
// 配送保証契約 (at-least-once / 可視性タイムアウト 5 分 / 指数バックオフ /
// 最大試行超過で dead / handler 冪等性は Worker 責務) は ADR 0046 が SSoT。
// 本 package は実装、ADR が契約。
package job

import (
	// encoding/json: jobs.payload (JSONB) を json.RawMessage で受け取る。
	// errors: sentinel 定義。
	// time: jobs.locked_at / run_at の型に time.Time を使う。
	"encoding/json"
	"errors"
	"time"
)

// NotifyChannel: Backend が NOTIFY 発火する channel 名。
// apps/api/app/repositories/jobs.py の "NOTIFY new_job, :id" と一致させる必要がある。
const NotifyChannel = "new_job"

// GenerationQueue: 問題生成ジョブを投げ込む論理キュー名。
// apps/api/app/services/problem_generation.py の _JOB_QUEUE = "generation" と一致。
const GenerationQueue = "generation"

// GradingQueue: 採点ジョブを投げ込む論理キュー名 (R1-5)。
// apps/api/app/services/submissions.py の _JOB_QUEUE = "grading" と一致。
const GradingQueue = "grading"

// TypeProblemGenerate: 問題生成ジョブの type 値。
// apps/api/app/services/problem_generation.py の _JOB_TYPE = "problem.generate" と一致。
const TypeProblemGenerate = "problem.generate"

// TypeSubmissionGrade: 採点ジョブの type 値 (R1-5)。
// apps/api/app/services/submissions.py の _JOB_TYPE = "submission.grade" と一致。
const TypeSubmissionGrade = "submission.grade"

// MaxAttempts: 1 ジョブの最大試行回数。
// 業務側 SSoT は problem-generation.md「最大 3 回再生成」。
// attempts が本値に到達したら state='dead' に落とす (DLQ 相当)。
const MaxAttempts = 3

// ErrNoJob: ClaimNext で queued ジョブが 1 件も無い時に返す sentinel。
// 呼び出し側は errors.Is(err, job.ErrNoJob) で判定し、ポーリング待機に入る。
var ErrNoJob = errors.New("job: no job available")

// IsTerminalAttempt: 与えられた attempts 値が「これ以上リトライしない」
// 境界に到達しているかを返す。MaxAttempts と比較する箇所が複数あると
// 片方を変えた時にもう片方が陳腐化するため、ここに集約する
// (orchestrator の dead 判定 + complete.MarkFailed の内部 dead 落とし)。
func IsTerminalAttempt(attempts int) bool {
	return attempts >= MaxAttempts
}

// Job: jobs テーブル 1 行分のうち、Worker が処理に必要なカラムだけ抜粋した型。
// 全カラム (locked_at / locked_by / result 等) は claim 後の SQL で書き込むため
// 本 struct には保持しない。
type Job struct {
	// ID: jobs.id (BIGSERIAL)。NOTIFY ペイロードに乗る値と同じ。
	ID int64
	// Queue: 論理キュー名 ("generation" / "grading" / "default")。
	Queue string
	// Type: ジョブ種別 ("problem.generate" / "submission.grade" 等)。
	// orchestrator が dispatch のキーとして使う。
	Type string
	// Payload: JSONB を生バイト列で保持。type に応じた struct に Unmarshal するのは
	// orchestrator 側 (internal/jobtypes/ の quicktype 生成型を使う)。
	Payload json.RawMessage
	// Attempts: 本ジョブを処理しようとした回数 (claim 時に +1 した後の値)。
	// MaxAttempts と比較してリトライか dead 落としかを判断する。
	Attempts int
	// RunAt: 実行可能時刻。バックオフでリトライした場合は将来時刻が入る。
	RunAt time.Time
}
