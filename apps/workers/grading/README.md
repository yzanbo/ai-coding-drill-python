# apps/workers/grading

採点（grading）Worker — 独立 Go module。Postgres ジョブキューから採点ジョブを取得し、使い捨て Docker サンドボックスで受験者の解答コードを test と一緒に実行し、LLM-as-a-Judge で品質評価を行って結果を DB に書き戻す。

詳細な選定理由・配置決定は [ADR 0016](../../../docs/adr/0016-go-for-grading-worker.md)（Go 採用）/ [ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)（Worker グルーピング）/ [worker.md](../../../docs/requirements/5-roadmap/r0-setup/worker.md)（環境構築）/ [worker-layers.md](../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)（ディレクトリ構成）を参照。

## ディレクトリ一覧

| パス | これは何か |
|---|---|
| [cmd/grading/](./cmd/grading/) | エントリポイント（`main.go`、internal を組み立てるだけ） |
| [internal/](./internal/) | 9 サブ package（Go の `internal/` 規約で外部 import 不可） |
| [internal/config/](./internal/config/) | 環境変数読み込み |
| [internal/observability/](./internal/observability/) | slog + OTel + (R4) Prometheus |
| [internal/db/](./internal/db/) | pgx pool + transaction helpers |
| [internal/job/](./internal/job/) | claim / listener / reclaim / complete |
| [internal/sandbox/](./internal/sandbox/) | Docker SDK ラッパ + 隔離設定 |
| [internal/llm/](./internal/llm/) | LLM プロバイダ抽象化（ADR 0007） |
| [internal/judge/](./internal/judge/) | LLM-as-a-Judge 整形 + パース |
| [internal/jobtypes/](./internal/jobtypes/) | quicktype 自動生成型（gitignore） |
| [internal/grading/](./internal/grading/) | **オーケストレーター**（採点フロー本体） |
| [prompts/judge/](./prompts/judge/) | judge プロンプト YAML（ADR 0040） |
| [sandbox/](./sandbox/) | サンドボックスイメージ Dockerfile（generation Worker も同 image を共有起動） |

## package 間の呼び出しの向き

```text
                       [jobs テーブル]
                            │
                            ▼
                      ┌────────────────┐
                      │ cmd/grading    │  main: 全 internal を組み立て
                      └─────┬──────────┘
                            │
                ┌───────────┴────────────┐
                ▼                        ▼
          ┌──────────────┐         ┌──────────────────┐
          │ internal     │         │ observability    │  起動時 1 回だけ初期化
          │ /grading     │         │ + config         │
          └──┬───────────┘         └──────────────────┘
             │ 採点フローのオーケストレーター
     ┌───────┼─────────┬────────────┬─────────┐
     ▼       ▼         ▼            ▼         ▼
 ┌─────┐ ┌─────┐ ┌─────┐ ┌─────────┐  ┌────────┐
 │ job │ │ db  │ │judge│ │ sandbox │  │jobtypes│  生成物・終端
 └──┬──┘ └─────┘ └──┬──┘ └─────────┘  └────────┘
    │               │
    ▼               ▼
  ┌────┐          ┌─────┐
  │ db │          │ llm │   provider 抽象化
  └────┘          └─────┘
```

**読み方**：

- `cmd/grading` が起動 → `internal/grading` が `job.Claim` でジョブ取得 → `judge`（解答評価 LLM）+ `sandbox`（test 実行）を呼ぶ → 結果を `db` 経由で書き戻し
- `jobtypes/` は **生成物のため終端**（手書きしない、終端を壊さない）
- `observability/` + `config/` は起動時 1 回だけ初期化（業務 package は context / 引数で受け取ったものだけを使う）
- 矢印の向きは [.claude/rules/worker.md](../../../.claude/rules/worker.md) の import 方向表と一致

## 採点 1 件のスパン構成（OpenTelemetry 計測）

```
[grade_job]
  ├─ [job.claim]                ジョブ取得 SQL
  ├─ [sandbox.create]           ContainerCreate
  ├─ [sandbox.run]              ContainerStart + Wait
  ├─ [sandbox.collect]          ログ取得
  ├─ [sandbox.cleanup]          Remove
  ├─ [judge.invoke]             judge LLM 呼び出し（ADR 0040）
  └─ [job.complete]             state='done' 更新
```

## やってはいけないこと

1. **`internal/llm/` → `internal/grading/` を import**（逆流、`§C`）
2. **`internal/judge/` → `internal/sandbox/` を import**（同 Layer 横断、orchestrator 経由にする）
3. **`internal/jobtypes/` を手書きで編集**（quicktype 再生成で消える、[ADR 0006](../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）
4. **`internal/` を別 Go module から import**（Go 規約違反 + generation worker から grading の `internal/` 不可）
5. **業務 package が `os.Getenv` を直接呼ぶ**（`internal/config/` に集約、main で DI）
6. **サンドボックスでホスト volume を生 mount**（tmpfs / read-only mount を使う、[ADR 0009](../../../docs/adr/0009-disposable-sandbox-container.md)）
7. **`SELECT ... FOR UPDATE` を `SKIP LOCKED` なしで書く**（[ADR 0004](../../../docs/adr/0004-postgres-as-job-queue.md)）
8. **LLM プロバイダを直接 import**（必ず `internal/llm.Provider` interface 経由、[ADR 0007](../../../docs/adr/0007-llm-provider-abstraction.md)）

## 起動

```bash
mise run worker:grading:dev          # 開発時のローカル起動
mise run worker:grading:test         # go test ./...
mise run worker:grading:lint         # golangci-lint run
mise run worker:grading:audit        # govulncheck ./...
mise run worker:grading:deps-check   # go mod tidy -diff
mise run worker:grading:types-gen    # quicktype で jobtypes/ 生成（R0-11 で使用）
mise run worker:grading:sandbox-build  # ai-coding-drill-sandbox:latest をビルド
```

## ローカル E2E smoke 手順

問題生成パイプライン全体 (claim → LLM → sandbox → judge → DB) が動くかを 1 件で確認する手順。**`docker compose up -d` で postgres / redis が稼働済み**前提。

```bash
# 1. DB schema を最新に
mise run api:db-migrate

# 2. サンドボックス image を build (初回 / Dockerfile 変更時)
mise run worker:grading:sandbox-build

# 3. .env を確認 (DATABASE_URL は pgx 互換の postgresql:// 形式、.env.example 参照)
#    GOOGLE_API_KEY が設定されていること
grep DATABASE_URL apps/workers/grading/.env
grep GOOGLE_API_KEY apps/workers/grading/.env >/dev/null && echo OK

# 4. Worker を別シェルで起動
mise run worker:grading:dev

# 5. 別シェルで API 経由 or 直接 DB に enqueue
#    (直接 DB の例。本番フローでは POST /problems/generate 経由)
docker exec -i ai-coding-drill-postgres psql -U postgres ai_coding_drill <<'SQL'
INSERT INTO users (id, display_name, email)
VALUES ('00000000-0000-0000-0000-000000000001', 'e2e-smoke', 'e2e@example.com')
ON CONFLICT (id) DO NOTHING;

INSERT INTO generation_requests (id, user_id, category, difficulty)
VALUES ('11111111-1111-1111-1111-111111111111',
        '00000000-0000-0000-0000-000000000001',
        'array', 'easy')
ON CONFLICT (id) DO NOTHING;

INSERT INTO jobs (queue, type, payload)
VALUES ('generation', 'problem.generate',
        '{"generationRequestId":"11111111-1111-1111-1111-111111111111","userId":"00000000-0000-0000-0000-000000000001","category":"array","difficulty":"easy","traceContext":{"traceparent":null,"tracestate":""}}'::jsonb)
RETURNING id;

NOTIFY new_job, 'manual';
SQL

# 6. Worker ログで `problem.generate: completed` を確認
#    DB で結果確認:
docker exec ai-coding-drill-postgres psql -U postgres ai_coding_drill \
  -c "SELECT id, state, attempts, LEFT(COALESCE(last_error,''), 80) AS err FROM jobs ORDER BY id DESC LIMIT 1;"
# 成功時: state='succeeded' + generation_requests.status='completed' + problems INSERT 済
```

### 観測された既知の課題 (R1-3 時点)

- **prompt v1 が生成する問題は test_cases と reference_solution の関係が曖昧**で、Worker 側で組み立てる Vitest spec の `solve(...input)` spread と LLM 出力の `test_cases.input` 形式 (1 引数 vs N 引数の表現) が噛み合わずテスト全失敗するケースがある。Worker 側は正しく ErrInvalidProblem 検知 + バックオフ retry に流すため**フロー自体は健全**だが、生成成功率を上げるには prompt v2 で `test_cases.input` の形式を厳密化する必要がある
- 対応: prompt 改善は別 PR で対応 (PR2 のスコープ外、生成パイプラインが動くこと自体は確認済み)

## 関連

- 規約 SSoT（実装契約）：[.claude/rules/worker.md](../../../.claude/rules/worker.md)
- 構造 SSoT（手順 + 設計判断）：[worker-layers.md](../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)
- 関連 ADR：[0016](../../../docs/adr/0016-go-for-grading-worker.md) / [0019](../../../docs/adr/0019-go-code-quality.md) / [0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md) / [0009](../../../docs/adr/0009-disposable-sandbox-container.md) / [0007](../../../docs/adr/0007-llm-provider-abstraction.md) / [0008](../../../docs/adr/0008-custom-llm-judge.md) / [0004](../../../docs/adr/0004-postgres-as-job-queue.md) / [0010](../../../docs/adr/0010-w3c-trace-context-in-job-payload.md) / [0046](../../../docs/adr/0046-job-queue-delivery-guarantees.md)
