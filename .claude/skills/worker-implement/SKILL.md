---
name: worker-implement
description: 要件 .md を読んで Go Worker を実装する
argument-hint: "[<name>] (例: grading, problem-generation)"
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

ユーザーの承認を待ってから次の手順に進む。

### 4. 要件 vs 実装の事前判断（方針の質疑で確定した決定を SSoT 側に反映）

手順 3 の方針提示で**ユーザーと対話的に確定した決定**について、**要件 .md を変えるべきか、実装を変えるべきかを工数を無視して純粋なメリット観点から判断**する。要件 .md の追従ありきで進めず、要件の方が正しい場合は実装側を直す前提に立つ。実装中に決めるとズレが残るため、**着手前に SSoT 側を確定**させる。

判断軸（工数は度外視）：

- 要件 .md の記述が業務として正しい → 実装をそれに合わせる
- 既存実装の挙動が業務として正しい / 要件記述が陳腐化している → 要件 .md を更新（ステータス・受け入れ条件含む）
- 双方が並行進化していて整合しない → 正しい側を選んで他方を直す

反映先：

- 要件側を変える場合：機能要件 .md の該当節（ビジネスルール / ジョブペイロード / 受け入れ条件 等）、必要なら横断要件（`3-cross-cutting/`）にも追記。観測可能な振る舞いは**受け入れ条件**にも追加
- 実装側を変える場合：手順 5 の実装で対応。**後方互換は取らない**（旧ジョブタイプ / 旧ハンドラ / 旧結果スキーマの併存禁止、最新状態に合わせて直接修正、→ CLAUDE.md「後方互換性について」）
- 実装詳細（依存ライブラリ / 設定値 / コンテナ設定）は要件 .md に書かない（SSoT は go.mod / 設定ファイル / Dockerfile 側、→ `_template.md` 冒頭の長期運用原則）

設計判断レベルの決定は ADR 起票も検討する。判断結果を反映してから手順 5 の実装に進む。

### 5. 実装

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

#### 後方互換とコミット粒度

- **後方互換は取らない**：旧ジョブタイプ / 旧結果スキーマ / 旧ハンドラの併存禁止。`apps/api/job-schemas/*.schema.json` から再生成された Go struct で signature が変わった呼び出し元は同じコミット内で最新形に直接修正（→ CLAUDE.md「後方互換性について」）
- **適切な粒度で適宜コミット**する（このスキルの実行自体がユーザの明示指示として `git add` / `git commit` を許容する）。スキーマ追加 / ハンドラ実装 / Docker 統合 / スタックジョブ回収 / 再生成 artifact など論理単位で区切る
- 再生成された Go struct（quicktype 出力）と手書きコードはコミットを分けるのが望ましい
- コミットメッセージは CLAUDE.md「コミットメッセージ」の規約（`<type>(<scope>): <subject>`、本文必須）に従う。AI 生成文言（`Co-Authored-By` / `Generated with` 等）は入れない
- `git push` / PR 作成はユーザの明示指示があるまで行わない

### 6. 共有 artifact（ジョブペイロード）変更時

- 新規ジョブペイロード型 → `apps/api/app/schemas/jobs/<job_type>.py` の Pydantic モデルを追加・修正
- `mise run api:job-schemas-export` で `apps/api/job-schemas/<job-type>.schema.json` を更新
- `mise run worker:<name>:types-gen`（または `mise run worker:types-gen` で全 Worker 一括）で quicktype が Go struct を再生成
- 詳細は [ADR 0006](../../../docs/adr/0006-json-schema-as-single-source-of-truth.md)

### 7. サンドボックスイメージ変更時

採点 Worker の場合、`apps/workers/grading/sandbox/` を変更したら：

```bash
docker build -t ai-coding-drill-sandbox:latest apps/workers/grading/sandbox
```

ローカル DB 起動中の Docker Engine にビルドされる。

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

問題があれば修正してから次の手順に進む。

### 9. 要件 vs 実装の事後判断（動作確認で出た差分をどちら側で吸収するか）

動作確認まで通った段階で、実装と要件 .md の間に差分があれば、**ステータス更新の前に**「要件を直す / 実装を直す」を**工数を無視して純粋なメリット観点から判断**して解消する。「実装が SSoT だから要件側を書き換える」と機械的に決めない。

判断軸（工数は度外視）：

- 実装の振る舞いが業務として正しい → 要件 .md を更新（受け入れ条件・ジョブペイロード / 結果スキーマ節など）
- 要件 .md の記述が業務として正しい / 実装が要件から外れている → 実装を直す（**後方互換 NG、最新状態に合わせて修正**、→ CLAUDE.md「後方互換性について」）
- 実装中に「これも担保すべき」と気付いた振る舞いは、要件側に受け入れ条件として追加する候補

確認対象の差分例：

- **追加された振る舞い / 契約**：新規ジョブタイプ・新規ハンドラ動作・新規エラーケース・スタックジョブ回収条件 等
- **ジョブペイロード / 結果スキーマ**：Pydantic → quicktype の流れで確定した最終的なフィールド構成

軽微な追従はこのスキル内で直接更新してよい。差分の規模が大きい場合は `/update-requirements` で対話的に進める。

### 10. ステータス更新

動作確認と要件追従まで完了したら、`docs/requirements/4-features/$ARGUMENTS.md` のステータスチェックボックスのうち**ワーカー実装完了**にチェックを入れる。

ステータス節の項目構成は `docs/requirements/4-features/_template.md` を踏襲し、機能固有の補足が括弧書きで追加されているケースもある。**項目の追加・削除はしない**（テンプレからの drift を作らない）。Worker が不要な機能（authentication 等）ではそもそも「ワーカー実装完了」項目自体が存在しないことがあるので、無ければ作らない。テンプレ本体の更新が必要なら `_template.md` を直し、既存機能ファイルにも同じ構造を反映する。
