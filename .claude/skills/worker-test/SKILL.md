---
name: worker-test
description: 要件 .md に基づいて Go Worker のテストを生成・実行する
argument-hint: "[<name>] (例: grading, problem-generation)"
---

# 要件ベースの Worker テスト

引数 `$ARGUMENTS` を機能名として解釈する。

## 手順

### 1. 要件と実装の読み込み

- `docs/requirements/4-features/$ARGUMENTS.md` を読み込む
- [.claude/rules/worker.md](../../rules/worker.md) のテスト規約を確認する
- 対象パッケージの実装コード（`apps/workers/<name>/internal/<area>/`）を読み込む

### 2. テスト方針の提示

以下をユーザーに提示し、承認を得てから次の手順に進む：

- テスト対象のパッケージ・関数一覧
- テストケースの概要（正常系・異常系・境界値）
- 単体テスト（標準 `testing`）と統合テスト（testcontainers-go）の使い分け
- 生成するファイルの一覧

### 3. 要件 vs 実装 vs テストの事前判断（観測対象の整合を取る）

手順 2 の方針提示で確定した観測対象について、要件・実装・テストの 3 者間にズレがあれば、**どれを変えるべきかを工数を無視して純粋なメリット観点から判断**する。「要件 .md 更新ありき」では進めない。判断軸は backend-test と同じ（要件 / 実装 / テスト方針のうち業務として正しいものを残し、他を直す）。

反映対象例（要件側を直す場合）：

- 機能要件 .md の**受け入れ条件**節（観測可能な境界値・異常系・スタックジョブ回収条件等の追加）、必要なら**バリデーション**節（業務上の理由があるルール）にも追記
- 機械的検証は Pydantic / quicktype 生成 Go struct 側が SSoT のため要件 .md には書かない（→ `_template.md` 冒頭の長期運用原則）
- 実装側を直す場合は**後方互換 NG**で最新状態に修正（旧ジョブタイプ・旧結果スキーマの併存禁止、→ CLAUDE.md「後方互換性について」）

判断結果を反映してから手順 4 のテスト生成に進む。

### 4. 単体テストの生成

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

### 5. 統合テストの生成

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

### 6. テストケースのカバレッジ目安

各機能に対して：

- **claim（ジョブ取得）**：キュー空、競合（複数ワーカー）、SKIP LOCKED 動作
- **process（実行）**：正常完了、タイムアウト、コンテナ作成失敗、stderr あり、テスト失敗
- **complete / fail**：state 遷移、result の正しい書き込み、submissions の更新
- **reclaim（スタック回収）**：5 分以上 running、attempts 加算、最大超過で dead
- **listener（LISTEN/NOTIFY）**：通知受信、コネクション切断時の再接続

### 7. テスト実行

```bash
# 単体テスト（Go 直接、apps/workers/grading の例）
cd apps/workers/grading
go test ./...

# 詳細表示
go test -v ./...

# カバレッジ
go test -cover ./...

# 統合テスト（Docker・DB が必要）
go test -tags=integration -v ./...
```

または mise 経由：

```bash
mise run worker:grading:test     # 採点 Worker
mise run worker:generation:test  # 問題生成 Worker（着手後）
mise run worker:test             # 全 Worker 横断
```

### 8. golangci-lint との併用

```bash
mise run worker:grading:lint     # 採点 Worker（apps/workers/grading）
mise run worker:lint             # 全 Worker 横断
```

リント警告も即時修正する（→ [.claude/rules/worker.md](../../rules/worker.md)）。

### 9. 要件 vs 実装 vs テストの事後判断（テストが暴いた差分を整える）

テスト生成・実行中に明らかになった差分は、**結果報告の前に**「要件 / 実装 / テスト のどれを直すか」を**工数を無視して純粋なメリット観点から判断**して解消する。テスト失敗を要件追従で機械的に丸めない。

判断軸（工数は度外視）：

- 実装の振る舞いが業務として正しい → 要件 .md を更新（受け入れ条件 / バリデーション節）
- 要件の記述が業務として正しい / 実装が要件から外れている → 実装を直す（**後方互換 NG**、最新状態に合わせて修正、→ CLAUDE.md「後方互換性について」）
- テスト自身が観測対象を取り違えていた → テスト側を直す

確認対象の差分例：

- **新たに見つかった観測可能な振る舞い**：境界値・異常系・スタックジョブ回収条件・LISTEN/NOTIFY 再接続挙動 等
- **業務上の制約として発見されたバリデーション**：「バリデーション」節候補（機械的検証は対象外）

軽微な追従はこのスキル内で直接更新してよい。差分の規模が大きい場合は `/update-requirements` で対話的に進める。

#### テスト・実装中のコミット粒度

- **適切な粒度で適宜コミット**する（このスキルの実行自体がユーザの明示指示として `git add` / `git commit` を許容する）。単体テスト / 結合テスト / fixture / 実装修正 / 要件更新は別コミットで区切る
- コミットメッセージは CLAUDE.md「コミットメッセージ」の規約（`<type>(<scope>): <subject>`、本文必須）。AI 生成文言（`Co-Authored-By` / `Generated with` 等）禁止
- `git push` / PR 作成はユーザの明示指示があるまで行わない

### 10. 結果報告

テスト結果をユーザーに報告する：

- パスしたテスト数 / 全テスト数
- カバレッジ率（`-cover` で取得）
- 該当する場合、要件の「ユニットテスト完了」「E2E テスト完了」ステータスをチェック（`_template.md` 準拠の項目のみ、追加・削除はしない）
