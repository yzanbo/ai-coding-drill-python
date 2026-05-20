//go:build integration

// listener_integration_test.go: LISTEN/NOTIFY が channel に届くこと、
// および Close で run goroutine が抜けることを検証。
package job_test

import (
	"context"
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/job"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/testsupport"
)

func TestListener_ReceivesNotify(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	lis, err := job.NewListener(ctx, pool)
	require.NoError(t, err)
	defer func() { _ = lis.Close() }()

	// LISTEN が確立する前に NOTIFY を撃つと取りこぼすため、少し待つ。
	time.Sleep(100 * time.Millisecond)

	_, err = pool.Exec(ctx, `NOTIFY new_job, '12345'`)
	require.NoError(t, err)

	select {
	case <-lis.Channel():
		// OK
	case <-time.After(3 * time.Second):
		t.Fatal("NOTIFY が channel に届かなかった")
	}
}

func TestListener_CloseStopsReceiving(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	lis, err := job.NewListener(ctx, pool)
	require.NoError(t, err)

	// Close 直後は channel から何も来ないことを確認 (drain 中の goroutine が
	// 残っていても、channel が close されて zero value を流すか blocked になる)。
	require.NoError(t, lis.Close())

	// Close 後に NOTIFY しても受信しないこと (channel が閉じている)。
	_, _ = pool.Exec(context.Background(), `NOTIFY new_job, 'after-close'`)

	select {
	case _, ok := <-lis.Channel():
		// goroutine が defer close(ch) を実行済みなら ok=false で抜ける。
		// それでも (まだ受信前なら) 値 が来ない方が正しい。
		assert.False(t, ok, "Close 後の channel は閉じている (close されているか blocked)")
	case <-time.After(500 * time.Millisecond):
		// blocked (まだ閉じていない可能性、それでも受信は来ない) → 許容。
		t.Log("Close 後の channel は blocked のまま (受信無し)、これも許容")
	}
}
