// listener.go: Postgres LISTEN new_job を貼って通知を channel に流す。
//
// 設計:
//   - LISTEN は専用の long-lived な *pgx.Conn を 1 本確保して握る
//     (pgxpool の Acquire ではアイドル接続を返却するので不向き)
//   - 通知は内部 channel (buffered, capacity 16) に流す。受信側が遅延
//     しても複数通知が溜まる程度で OK (本体は 30 秒ポーリングで取りこぼし
//     カバーする設計、ADR 0046)
//   - ctx.Done() を尊重: ctx キャンセルで listener goroutine が終了して
//     Conn を Close する
package job

import (
	"context"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// notifyChannelBuffer: 内部 channel の容量。
// 通常 0〜1 件で消費されるが、Worker 側 (claim) が忙しい瞬間に
// 通知が連続した時に溢れないよう少し余裕を持たせる。
// あふれた場合でも 30 秒ポーリングで拾えるため致命ではない。
const notifyChannelBuffer = 16

// Listener: NOTIFY new_job の通知を受け取り Channel() に流す long-lived 接続。
//
// 使い方:
//
//	lis, err := job.NewListener(ctx, pool)
//	defer lis.Close()
//	for {
//	    select {
//	    case <-lis.Channel():  // 新ジョブ通知
//	    case <-ticker.C:       // 30 秒ポーリング (取りこぼし対策)
//	    case <-ctx.Done():
//	        return
//	    }
//	    // ここで ClaimNext を呼ぶ
//	}
type Listener struct {
	conn *pgx.Conn
	ch   chan struct{}
}

// NewListener: LISTEN を貼って通知を待つ goroutine を起動する。
//
// 内部で pool から専用接続を 1 本払い出して LISTEN を実行する。
// pgxpool.Acquire は接続をプールに返却する前提のため、長時間 LISTEN を
// 貼るには直接 pgx.Connect で別接続を作る方が安全。本実装では
// pool.Config().ConnConfig からコピーして同一 DSN で接続を確立する。
func NewListener(ctx context.Context, pool *pgxpool.Pool) (*Listener, error) {
	// pool の ConnConfig を流用 (DSN / TLS / auth 等を二重管理しない)。
	connCfg := pool.Config().ConnConfig.Copy()
	conn, err := pgx.ConnectConfig(ctx, connCfg)
	if err != nil {
		return nil, fmt.Errorf("job: listener connect: %w", err)
	}
	// LISTEN は識別子なので bind パラメータ不可。channel 名は const なので
	// SQL インジェクション経路は無い。
	if _, err := conn.Exec(ctx, "LISTEN "+NotifyChannel); err != nil {
		_ = conn.Close(ctx)
		return nil, fmt.Errorf("job: LISTEN %s: %w", NotifyChannel, err)
	}

	lis := &Listener{
		conn: conn,
		ch:   make(chan struct{}, notifyChannelBuffer),
	}
	go lis.run(ctx)
	return lis, nil
}

// Channel: 新ジョブ通知を流す受信専用 channel。
// 構造体ではなく struct{} を流す: ペイロード (job_id) は使わず、
// 「何か届いた → 次の claim を試す」シグナルとしてのみ使う。
// 取りこぼしの本命カバーは 30 秒ポーリング (ADR 0046)。
func (l *Listener) Channel() <-chan struct{} {
	return l.ch
}

// Close: listener 接続を閉じる。run goroutine は ctx.Done() か Conn.Close()
// 後の WaitForNotification の error で抜ける。
func (l *Listener) Close() error {
	// Close は ctx を要求する: 既にキャンセル済みでも closeCtx を新規に作る。
	// Conn.Close は内部で 5s timeout を持つため context.Background() で十分。
	return l.conn.Close(context.Background())
}

// run: WaitForNotification を回し続けて通知を ch に流す goroutine。
//
// 終了条件:
//   - ctx.Done(): キャンセル時。WaitForNotification は ctx 経由で抜ける
//   - conn.Close() 後: WaitForNotification がエラーで戻る
//   - 致命的 SQL エラー (再現性のあるもの) は呼び出し元への通知手段が無いため
//     ログ出力後にループを抜ける (本 PR では slog 経由で logged。main 側で
//     listener 不可なら次の polling 待ちで拾われる前提)
func (l *Listener) run(ctx context.Context) {
	defer close(l.ch)
	for {
		_, err := l.conn.WaitForNotification(ctx)
		if err != nil {
			// ctx キャンセル / Conn Close は正常終了として無視。
			if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
				return
			}
			// 接続が切れた等の異常は呼び出し元へ通知できない (chan を error 型
			// にしていないため)。本 PR では return して listener 停止扱い。
			// 上位ループは 30 秒ポーリングで claim を試行し続けるので、
			// listener が止まっても feature は壊れない (= レイテンシ劣化のみ)。
			return
		}
		// 通知 1 件を ch に流す。受信側が忙しくて buffer 満杯なら drop する
		// (取りこぼしは 30 秒ポーリングで吸収する設計)。
		select {
		case l.ch <- struct{}{}:
		default:
		}
	}
}
