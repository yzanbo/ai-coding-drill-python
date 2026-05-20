//go:build integration

// pool_integration_test.go: NewPool と WithTx の挙動を実 Postgres で検証する。
//
// integration build tag が無いと go test ./... では走らない。
// 走らせ方: go test -tags=integration ./internal/db/...
package db_test

import (
	"context"
	"errors"
	"testing"

	"github.com/jackc/pgx/v5"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/db"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/testsupport"
)

func TestNewPool_PingOK(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	// 既に testsupport 内で ping 済みだが、外部から呼んでも error が出ない事を確認。
	require.NoError(t, pool.Ping(context.Background()))
}

func TestWithTx_CommitOnSuccess(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	// テーブルを 1 個作って WithTx で INSERT、Commit されて見えることを確認。
	_, err := pool.Exec(ctx, `CREATE TEMP TABLE tx_test (id INT)`)
	require.NoError(t, err)

	err = db.WithTx(ctx, pool, func(tx pgx.Tx) error {
		_, err := tx.Exec(ctx, `INSERT INTO tx_test (id) VALUES (1)`)
		return err
	})
	require.NoError(t, err)

	// TEMP TABLE はセッション内のみ可視。pool は別接続を払い出すので、
	// クエリも同じ pool 経由で行う。
	// (実際は pgxpool が同じ接続を再利用するかは保証されないが、TEMP TABLE
	// セッションが先程の WithTx の接続上に残っていれば pool が同接続を返した
	// 時にだけ見える。確実に検証するため通常テーブルに変える。)
	_, err = pool.Exec(ctx, `DROP TABLE IF EXISTS tx_persist`)
	require.NoError(t, err)
	_, err = pool.Exec(ctx, `CREATE TABLE tx_persist (id INT)`)
	require.NoError(t, err)
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DROP TABLE IF EXISTS tx_persist`) })

	err = db.WithTx(ctx, pool, func(tx pgx.Tx) error {
		_, err := tx.Exec(ctx, `INSERT INTO tx_persist (id) VALUES (42)`)
		return err
	})
	require.NoError(t, err)

	var got int
	err = pool.QueryRow(ctx, `SELECT id FROM tx_persist WHERE id = 42`).Scan(&got)
	require.NoError(t, err)
	assert.Equal(t, 42, got, "WithTx 成功時は Commit されて行が見える")
}

func TestWithTx_RollbackOnError(t *testing.T) {
	pool := testsupport.StartPostgres(t)
	ctx := context.Background()

	_, err := pool.Exec(ctx, `CREATE TABLE tx_rollback (id INT)`)
	require.NoError(t, err)
	t.Cleanup(func() { _, _ = pool.Exec(ctx, `DROP TABLE IF EXISTS tx_rollback`) })

	sentinel := errors.New("intentional")
	err = db.WithTx(ctx, pool, func(tx pgx.Tx) error {
		_, _ = tx.Exec(ctx, `INSERT INTO tx_rollback (id) VALUES (99)`)
		return sentinel
	})
	require.ErrorIs(t, err, sentinel)

	// Rollback されているので 99 は存在しない。
	var count int
	err = pool.QueryRow(ctx, `SELECT COUNT(*) FROM tx_rollback WHERE id = 99`).Scan(&count)
	require.NoError(t, err)
	assert.Equal(t, 0, count, "WithTx の fn が error 返したら Rollback される")
}
