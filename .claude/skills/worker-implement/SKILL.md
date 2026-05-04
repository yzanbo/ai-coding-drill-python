---
name: worker-implement
description: 要件 .md を読んで Go 採点ワーカーを実装する
argument-hint: "[feature-name] (例: grading, regrading)"
---

# 要件ベースの採点ワーカー実装

引数 `$ARGUMENTS` を機能名として解釈する。Go 採点ワーカー（`apps/grading-worker/`）の実装を扱う。

## 手順

### 1. 要件の読み込み

- 機能要件：`docs/requirements/4-features/$ARGUMENTS.md`
- ベース要件：[02-architecture.md: ジョブキュー](../../../docs/requirements/2-foundation/02-architecture.md#ジョブキューpostgres-select-for-update-skip-locked)、[01-data-model.md: jobs テーブル](../../../docs/requirements/3-cross-cutting/01-data-model.md)
- 関連 ADR：[ADR 0001](../../../docs/adr/0001-postgres-as-job-queue.md)、[ADR 0005](../../../docs/adr/0005-go-for-grading-worker.md)、[ADR 0008](../../../docs/adr/0008-disposable-sandbox-container.md)
- ワーカールール：[.claude/rules/worker.md](../../rules/worker.md)
- 共有スキーマ：`packages/shared-types/schemas/job.schema.json`

### 2. 現状の確認

- 関連する既存コード（`apps/grading-worker/internal/`）を確認
- 共有スキーマから生成された Go 型（`apps/grading-worker/internal/schema/`）を確認
- jobs テーブルの該当ジョブタイプ（`type` 列）が既存ハンドラでカバーされているか確認
- 採点コンテナイメージ（`apps/grading-worker/sandbox/`）の必要な変更を確認

### 3. 実装方針の提示

要件に基づいて実装方針をユーザーに提示する：

- 新規ジョブタイプの追加（`type` 列の値）
- 新規ハンドラの追加（`internal/job/handler/<type>.go`）
- Docker コンテナへ渡すコマンド・環境変数の変更
- 採点結果スキーマの変更（`packages/shared-types/schemas/grading-result.schema.json`）
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

### 5. 共有スキーマ変更時

- 新規ジョブペイロード型 → `packages/shared-types/schemas/job.schema.json` を拡張
- `pnpm shared-types:generate` で Go 型再生成（`internal/schema/`）
- TS 側（NestJS Producer）の Zod 型も自動再生成される
- 詳細は [ADR 0014](../../../docs/adr/0014-json-schema-as-single-source-of-truth.md)

### 6. サンドボックスイメージ変更時

`apps/grading-worker/sandbox/` を変更した場合：

```bash
pnpm sandbox:build       # ai-coding-drill-sandbox イメージ再ビルド
```

ローカル DB 起動中の Docker Engine にビルドされる。

### 7. ステータス更新

実装完了後、`docs/requirements/4-features/$ARGUMENTS.md` のステータスチェックボックスを更新：

```markdown
## ステータス
- [x] 要件定義完了
- [x] バックエンド実装完了
- [x] フロントエンド実装完了
- [x] 採点ワーカー実装完了    ← ここをチェック
- [ ] テスト完了
```

### 8. 動作確認

```bash
# 型チェック・リント
pnpm --filter @ai-coding-drill/grading-worker typecheck   # go vet 相当
golangci-lint run apps/grading-worker/...

# ビルド
pnpm --filter @ai-coding-drill/grading-worker build

# ローカル統合確認：
# 1. docker compose up -d（DB / Redis）
# 2. pnpm db:migrate
# 3. pnpm sandbox:build
# 4. pnpm --filter @ai-coding-drill/grading-worker dev
# 5. NestJS から手動でジョブを投入し、採点が完了することを確認
```

問題があれば修正してから完了とする。
