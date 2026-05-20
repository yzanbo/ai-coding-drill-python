// Package db: Postgres 接続のインフラ層。
//
// 役割:
//   - pgxpool.Pool を作って配る (NewPool)
//   - トランザクションヘルパ (WithTx) を提供
//
// 業務 SQL (jobs テーブル取得 / problems INSERT 等) は本 package に書かない。
// それぞれ internal/job/ と internal/grading/ の責務。
// 詳細: ../README.md (Layer 0 制約) と .claude/rules/worker.md。
package db

import (
	// context: 接続の deadline / cancel を伝える。
	// fmt:     エラー wrap に使う。
	// time:    プール接続の health check / max lifetime に使う。
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// NewPool: DSN から pgxpool.Pool を組み立てて返す。
//
// 設計:
//   - 接続数の上限は pgxpool 既定 (max 4) を超える設定は本 PR では入れない:
//     Worker 1 プロセスの concurrency 4 + 短時間トランザクション運用前提なので、
//     上限を明示で増やす理由が今は無い。必要になったら ParseConfig 後に
//     MaxConns を上書きする
//   - HealthCheckPeriod: pgxpool 既定 1 分。Worker は長時間 LISTEN を貼るので、
//     アイドル接続が dead にならないよう既定で十分
//
// 戻り値:
//   - *pgxpool.Pool: 成功時。呼び出し側は defer pool.Close() を必ず行う
//   - error: DSN parse 失敗 / 初回 ping 失敗
func NewPool(ctx context.Context, databaseURL string) (*pgxpool.Pool, error) {
	cfg, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, fmt.Errorf("db: parse DATABASE_URL: %w", err)
	}

	// MaxConnLifetime: 1 時間で接続を破棄して作り直す。
	// クラウド DB (RDS / Cloud SQL) のフェイルオーバ / メンテナンス時に
	// 古い接続が掴みっぱなしになるのを防ぐ。
	cfg.MaxConnLifetime = 1 * time.Hour

	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, fmt.Errorf("db: new pool: %w", err)
	}

	// 起動直後に Ping して接続が確立できることを確認する。
	// 失敗時は pool を閉じてエラーを返す (Caller が defer Close を貼る前に
	// 漏らさないため)。
	pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	if err := pool.Ping(pingCtx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("db: initial ping failed: %w", err)
	}
	return pool, nil
}

// WithTx: トランザクション境界を 1 関数に閉じる helper。
//
// fn が nil を返せば Commit、エラーを返せば Rollback。
// fn の中で panic が起きても defer で Rollback を確実に行う。
//
// Worker 側で頻出する「ジョブを claim → 1 トランザクション内で
// state='running' に UPDATE → SELECT 結果を返す」のような短時間
// トランザクションを記述しやすくするための共通形。
func WithTx(ctx context.Context, pool *pgxpool.Pool, fn func(tx pgx.Tx) error) (err error) {
	tx, err := pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("db: begin tx: %w", err)
	}
	defer func() {
		// fn が成功して Commit 済みなら Rollback は no-op (pgx は ErrTxClosed を返す)。
		// panic / error 時に確実に Rollback するための保険。
		if rbErr := tx.Rollback(ctx); rbErr != nil && err == nil {
			// Commit 済みでない時のみ rollback エラーを表面化する。
			if !isTxClosedErr(rbErr) {
				err = fmt.Errorf("db: rollback: %w", rbErr)
			}
		}
	}()
	if err := fn(tx); err != nil {
		return err
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("db: commit: %w", err)
	}
	return nil
}

// isTxClosedErr: pgx.ErrTxClosed と等価判定。
// Rollback が「既に Commit/Rollback 済み」で返すエラーを no-op 扱いするため。
func isTxClosedErr(err error) bool {
	return err != nil && err.Error() == pgx.ErrTxClosed.Error()
}
