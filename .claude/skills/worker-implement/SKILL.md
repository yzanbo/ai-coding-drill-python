---
name: worker-implement
description: 要件 .md を読んで Go Worker を実装する
argument-hint: "[F-XX-feature-name] (例: F-04-auto-grading, F-02-problem-generation)"
---

# 要件ベースの Worker 実装

引数 `$ARGUMENTS` を機能名として解釈する。Go Worker 群（`apps/workers/<name>/`）の実装を扱う（採点 / 問題生成、→ [ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）。

## 手順

### 1. 要件の読み込み

- 機能要件：`docs/requirements/4-features/$ARGUMENTS.md`
- ベース要件：[02-architecture.md: ジョブキュー](../../../docs/requirements/2-foundation/02-architecture.md#ジョブキューpostgres-select-for-update-skip-locked)、[01-data-model.md: jobs テーブル](../../../docs/requirements/3-cross-cutting/01-data-model.md)
- 関連 ADR：[ADR 0004](../../../docs/adr/0004-postgres-as-job-queue.md)、[ADR 0016](../../../docs/adr/0016-go-for-grading-worker.md)、[ADR 0009](../../../docs/adr/0009-disposable-sandbox-container.md)、[ADR 0040](../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)
- Worker ルール：[.claude/rules/worker.md](../../rules/worker.md)
- 共有 artifact：`apps/api/job-schemas/<job-type>.schema.json`（Pydantic から書き出し、→ [ADR 0006](../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)）

### 2. 現状の確認

- 対象 Worker のディレクトリを特定（採点なら `apps/workers/grading/`、問題生成なら `apps/workers/generation/`）
- 関連する既存コード（`apps/workers/<name>/internal/`）を確認
- quicktype で生成された Go struct（`apps/workers/<name>/internal/jobtypes/`、gitignore）を確認
- jobs テーブルの該当ジョブタイプ（`type` 列）が既存ハンドラでカバーされているか確認
- 採点コンテナイメージ（`apps/workers/grading/sandbox/`、採点 Worker のみ）の必要な変更を確認

### 3. 実装方針の提示

要件に基づいて実装方針をユーザーに提示する：

- 新規ジョブタイプの追加（`type` 列の値）
- 新規ハンドラの追加（`internal/job/handler/<type>.go`）
- Docker コンテナへ渡すコマンド・環境変数の変更
- 採点結果スキーマの変更（`apps/api/app/schemas/jobs/grading_result.py` の Pydantic を更新 → `apps/api/job-schemas/grading-result.schema.json` に書き出し）
- スタックジョブ回収・リトライポリシーの調整

ユーザーの承認を待ってから実装に着手する。

### 4. 実装

[.claude/rules/worker.md](../../rules/worker.md) のコーディング規約に従って実装する。重要なポイント：

#### ジョブ取得（claim）

- `SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1` で 1 件取得
- 短いトランザクションで `state='running'`, `locked_at=now()`, `locked_by` を更新してすぐコミット
- 別トランザクションで Docker 実行（行ロックを長時間握らない）

#### Docker 実行

- ホストの `docker.sock` 経由（DooD）
- 採点コンテナは使い捨て（毎回 `ContainerCreate` → `Start` → `Wait` → `Logs` → `Remove`）
- 制約：`--network none` / `--memory 256m` / `--cpus 0.5` / `--read-only` / `--tmpfs /tmp` / 非 root / 5 秒タイムアウト

#### 結果書き戻し

- 別トランザクションで `state='done'` または `'failed'`、`result` JSONB、`updated_at` を更新
- 関連リソース（`submissions.status`, `submissions.score`, `submissions.graded_at` 等）も同時に更新

#### エラー処理

- リトライ可能（DB 接続エラー、Docker エラー等）→ `last_error` 記録、`run_at = now() + backoff` で再試行
- リトライ不可（コードコンパイルエラー、タイムアウト、テスト失敗等）→ 最大試行回数到達で `state='dead'`
- パニックは `recover()` で吸収しジョブを `'failed'` 状態に、ワーカー本体は継続

#### LISTEN/NOTIFY 統合

- `pgx` の `Conn.WaitForNotification` で NOTIFY 受信
- 30 秒間隔の低頻度ポーリングを並走（取りこぼし対策）

#### スタックジョブの回収

- 別 goroutine で定期実行（既定 30 秒間隔）
- `locked_at < now() - interval '5 min'` を `state='queued'` に戻す（attempts++）

### 5. 共有 artifact（ジョブペイロード）変更時

- 新規ジョブペイロード型 → `apps/api/app/schemas/jobs/<job_type>.py` の Pydantic モデルを追加・修正
- `mise run api:job-schemas-export` で `apps/api/job-schemas/<job-type>.schema.json` を更新
- `mise run worker:<name>:types-gen`（または `mise run worker:types-gen` で全 Worker 一括）で quicktype が Go struct を再生成
- 詳細は [ADR 0006](../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)

### 6. サンドボックスイメージ変更時

採点 Worker の場合、`apps/workers/grading/sandbox/` を変更したら：

```bash
docker build -t ai-coding-drill-sandbox:latest apps/workers/grading/sandbox
```

ローカル DB 起動中の Docker Engine にビルドされる。

### 7. ステータス更新

実装完了後、`docs/requirements/4-features/$ARGUMENTS.md` のステータスチェックボックスを更新：

```markdown
## ステータス
- [x] 要件定義完了（このファイルが受け入れ条件まで埋まっている）
- [x] バックエンド実装完了
- [x] フロントエンド実装完了
- [x] ワーカー実装完了（必要な場合のみ）    ← ここをチェック
- [ ] ユニットテスト完了
- [ ] E2E テスト完了（主要フローのみ）
- [ ] **受け入れ条件すべて満たす**
- [ ] PR マージ済み
```

### 8. 動作確認

```bash
# 型チェック・リント・脆弱性スキャン
mise run worker:grading:lint           # golangci-lint run
mise run worker:grading:audit          # govulncheck ./...
mise run worker:grading:deps-check     # go mod tidy 後の差分チェック

# ビルド（Go 直接、apps/workers/grading）
cd apps/workers/grading
go build ./cmd/grading

# ローカル統合確認：
# 1. docker compose up -d（DB / Redis）
# 2. mise run api:db-migrate
# 3. docker build -t ai-coding-drill-sandbox:latest apps/workers/grading/sandbox
# 4. mise run worker:grading:dev
# 5. FastAPI から手動でジョブを投入し、採点が完了することを確認
```

問題があれば修正してから完了とする。
