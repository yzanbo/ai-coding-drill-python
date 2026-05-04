---
name: worker-test
description: 要件 .md に基づいて Go 採点ワーカーのテストを生成・実行する
argument-hint: "[feature-name] (例: grading)"
---

# 要件ベースの採点ワーカーテスト

引数 `$ARGUMENTS` を機能名として解釈する。

## 手順

### 1. 要件と実装の読み込み

- `docs/requirements/4-features/$ARGUMENTS.md` を読み込む
- [.claude/rules/worker.md](../../rules/worker.md) のテスト規約を確認する
- 対象パッケージの実装コード（`apps/grading-worker/internal/<area>/`）を読み込む

### 2. テスト方針の提示

以下をユーザーに提示し、承認を得てから生成に着手する：

- テスト対象のパッケージ・関数一覧
- テストケースの概要（正常系・異常系・境界値）
- 単体テスト（標準 `testing`）と統合テスト（testcontainers-go）の使い分け
- 生成するファイルの一覧

### 3. 単体テストの生成

`*_test.go` を対象ファイルと同じパッケージに作成する。

#### テスト規約

- フレームワーク：標準 `testing` + `github.com/stretchr/testify`
- テスト名は日本語可：`TestClaimNextJob_正常系_キューが空ならnil`
- テーブル駆動テストを推奨

#### テスト構造例

```go
package job

import (
    "context"
    "testing"
    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/require"
)

func TestClaimNextJob(t *testing.T) {
    tests := []struct {
        name      string
        setup     func(t *testing.T) *Querier
        wantJob   bool
        wantError error
    }{
        {
            name: "正常系: キューにジョブがあれば取得する",
            setup: func(t *testing.T) *Querier {
                // mock setup
            },
            wantJob: true,
        },
        {
            name: "正常系: キューが空なら nil を返す",
            setup: func(t *testing.T) *Querier {
                // mock setup
            },
            wantJob: false,
        },
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            q := tt.setup(t)
            job, err := ClaimNextJob(context.Background(), q, "grading", "worker-1")
            if tt.wantError != nil {
                assert.ErrorIs(t, err, tt.wantError)
                return
            }
            require.NoError(t, err)
            if tt.wantJob {
                assert.NotNil(t, job)
            } else {
                assert.Nil(t, job)
            }
        })
    }
}
```

### 4. 統合テストの生成

DB / Docker を含む統合フローは testcontainers-go を使う：

```go
import (
    "github.com/testcontainers/testcontainers-go"
    "github.com/testcontainers/testcontainers-go/modules/postgres"
)

func setupTestDB(t *testing.T) *pgxpool.Pool {
    ctx := context.Background()
    pgContainer, err := postgres.Run(ctx,
        "postgres:16-alpine",
        postgres.WithDatabase("test"),
        postgres.WithUsername("test"),
        postgres.WithPassword("test"),
    )
    require.NoError(t, err)
    t.Cleanup(func() { pgContainer.Terminate(ctx) })
    // マイグレーション実行 → pool を返す
}
```

統合テストファイルは `*_integration_test.go` として、`-tags=integration` で分離する：

```go
//go:build integration
// +build integration

package job_test
// ...
```

### 5. テストケースのカバレッジ目安

各機能に対して：

- **claim（ジョブ取得）**：キュー空、競合（複数ワーカー）、SKIP LOCKED 動作
- **process（実行）**：正常完了、タイムアウト、コンテナ作成失敗、stderr あり、テスト失敗
- **complete / fail**：state 遷移、result の正しい書き込み、submissions の更新
- **reclaim（スタック回収）**：5 分以上 running、attempts 加算、最大超過で dead
- **listener（LISTEN/NOTIFY）**：通知受信、コネクション切断時の再接続

### 6. テスト実行

```bash
# 単体テスト
cd apps/grading-worker
go test ./...

# 詳細表示
go test -v ./...

# カバレッジ
go test -cover ./...

# 統合テスト（Docker・DB が必要）
go test -tags=integration -v ./...
```

または Turborepo 経由：

```bash
pnpm --filter @ai-coding-drill/grading-worker test
```

### 7. golangci-lint との併用

```bash
golangci-lint run apps/grading-worker/...
```

リント警告も即時修正する（→ [.claude/rules/worker.md](../../rules/worker.md)）。

### 8. 結果報告

テスト結果をユーザーに報告する：

- パスしたテスト数 / 全テスト数
- カバレッジ率（`-cover` で取得）
- 該当する場合、要件の「テスト完了」ステータスをチェック
