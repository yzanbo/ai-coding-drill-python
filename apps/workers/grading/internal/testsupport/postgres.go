// Package testsupport: Worker integration テスト用の共通基盤。
//
// 役割:
//   - testcontainers-go で Postgres を起動する helper (StartPostgres)
//   - schema.sql で必要テーブルを作成
//   - DSN と *pgxpool.Pool を返す
//
// 制約:
//   - integration build tag が立っていないと使われない
//     (本 package を import する test ファイルはすべて //go:build integration を持つ)
//   - schema.sql は apps/api/alembic/versions/ と二重管理になっており、
//     Alembic 側変更を手で追随する必要がある (schema.sql 冒頭に明記)
package testsupport

import (
	"context"
	_ "embed"
	"fmt"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/stretchr/testify/require"
	"github.com/testcontainers/testcontainers-go"
	"github.com/testcontainers/testcontainers-go/modules/postgres"
	"github.com/testcontainers/testcontainers-go/wait"
)

//go:embed schema.sql
var schemaSQL string

// SchemaSQL: schema.sql の内容を返す。
// 他テストファイルが追加 DDL を実行したい場合の起点として公開する。
func SchemaSQL() string { return schemaSQL }

// StartPostgres: testcontainers-go で Postgres を起動し pool を返す。
//
// 振る舞い:
//   - postgres:16-alpine を pull して起動
//   - schema.sql を init script として渡し、起動直後に CREATE TABLE 等を実行
//   - 起動準備完了を pg_isready で待つ (testcontainers の WaitStrategy)
//   - t.Cleanup で container と pool を破棄
//
// 戻り値: pgxpool.Pool。同じ container 内では複数テスト間で行レベルの
// 衝突が起きるため、各テストは自分のテーブル領域 (queue name や user_id) を
// 分離するか、テスト前後で DELETE で掃除する。
func StartPostgres(t *testing.T) *pgxpool.Pool {
	t.Helper()
	ctx := context.Background()

	container, err := postgres.Run(ctx,
		"postgres:16-alpine",
		postgres.WithDatabase("worker_test"),
		postgres.WithUsername("worker_test"),
		postgres.WithPassword("worker_test"),
		postgres.WithInitScripts(),
		// pg_isready ベースの 2 回確認: 1 回目で起動、2 回目でロール準備完了。
		testcontainers.WithWaitStrategy(
			wait.ForLog("database system is ready to accept connections").
				WithOccurrence(2).
				WithStartupTimeout(60*time.Second),
		),
	)
	require.NoError(t, err, "postgres container 起動失敗 (Docker daemon が動いているか確認)")
	t.Cleanup(func() {
		// 失敗時のログを残しつつ確実に Terminate する。
		stopCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		_ = container.Terminate(stopCtx)
	})

	dsn, err := container.ConnectionString(ctx, "sslmode=disable")
	require.NoError(t, err)

	pool, err := pgxpool.New(ctx, dsn)
	require.NoError(t, err)
	t.Cleanup(pool.Close)

	// schema.sql 適用。WithInitScripts は file path 必須だが、本 package では
	// embed で SQL 文字列を持っているため、起動後に Exec する方が schema.sql
	// 配置パス問題に巻き込まれずに済む (testcontainers がファイルを
	// container 内に copy する都合)。
	pingCtx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	require.NoError(t, pool.Ping(pingCtx))
	if _, err := pool.Exec(ctx, schemaSQL); err != nil {
		t.Fatalf("schema.sql 適用失敗: %v", err)
	}

	return pool
}

// InsertTestUser: テスト用の users 行を 1 件 INSERT して id を返す。
// generation_requests.user_id の FK を満たすために使う。
func InsertTestUser(t *testing.T, pool *pgxpool.Pool) string {
	t.Helper()
	var id string
	err := pool.QueryRow(context.Background(),
		`INSERT INTO users (display_name, email) VALUES ($1, $2) RETURNING id`,
		"test-user", fmt.Sprintf("test-%d@example.com", time.Now().UnixNano()),
	).Scan(&id)
	require.NoError(t, err)
	return id
}
