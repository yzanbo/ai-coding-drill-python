package job

import (
	"testing"
	"time"

	"github.com/stretchr/testify/assert"
)

// TestBackoffFor: attempts 値ごとのバックオフ秒数を検証。
// ADR 0046 の「10s → 60s」スケジュールに沿っていること。
func TestBackoffFor(t *testing.T) {
	t.Parallel()

	// attempts=1 失敗 → 10s
	assert.Equal(t, 10*time.Second, backoffFor(1))
	// attempts=2 失敗 → 60s
	assert.Equal(t, 60*time.Second, backoffFor(2))
	// attempts=0 (理論上来ない) は 0-index 補正で先頭値 10s
	assert.Equal(t, 10*time.Second, backoffFor(0))
	// attempts > MaxAttempts (本来は MarkDead 経路) は末尾値で clamp
	assert.Equal(t, 60*time.Second, backoffFor(99))
}
