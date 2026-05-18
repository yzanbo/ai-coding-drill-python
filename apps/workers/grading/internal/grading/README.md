# internal/grading（採点フローの**オーケストレーター**）

## とは何か

採点ジョブ 1 件を処理するための**段取り役**。`internal/job/`（取得）→ `internal/sandbox/`（解答を test と実行）→ `internal/judge/`（LLM-as-a-Judge による品質評価）→ `internal/db/`（結果書き戻し）の順に呼び出し、各ステップのエラーハンドリング・リトライ判断・タイムアウトを 1 箇所に集約する。

## なぜ main.go に inline せず別 package か

- フロー全体が 100〜200 行規模になり、main.go に詰めると「組み立て」「シグナル」「フロー」が混在して見通しが悪い
- `grading.Process(ctx, deps, job)` を **テストで fake deps を注入して呼べる**形にしたい
- 将来別のジョブ種別が増えたとき、main.go の dispatch だけ拡張すれば本体は触らない

## 採点 1 件のスパン構成（observability で計測する目印）

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

各スパンは `internal/observability/` 経由で自動的に trace に乗る（`Process` は呼び出すだけ）。

## 役割

- `Process(ctx, deps, job) (jobtypes.GradingResult, error)`：1 ジョブの全段取り
- `Deps` 構造体：`Pool` / `Sandbox` / `Judge` などの依存を interface 経由で受け取る（テストで差し替え可能に）
- リトライ判定：エラー種別ごとに「再試行可能」or「即 dead」を分岐
- パニック吸収：`recover()` でログ → ジョブ failed 状態 → Worker 本体は継続
- タイムアウト：`JOB_TIMEOUT_SECONDS`（既定 5 秒、`internal/config/`）を `context.WithTimeout` で適用

## やってはいけないこと

- 別のフローを足すたびにファイルを増やす：1 ファイル `process.go` を中心に、ステップごとに非エクスポート関数で分割する程度に留める
- 上位（`cmd/grading/main.go`）が `process` の内部に直接介入する：main.go は組み立て + 起動 + シグナル受信だけ
- `internal/llm/` を直接 import：LLM 呼び出しは必ず `internal/judge/` 経由（[worker-layers.md §C](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- 1 ジョブ内で goroutine を多用：複数ジョブの並列処理は main.go の goroutine pool で行う、1 ジョブの中身は順次処理

## 関連

- 規約 SSoT：[.claude/rules/worker.md](../../../../.claude/rules/worker.md)
- 自動採点要件：[grading.md](../../../../docs/requirements/4-features/grading.md)
- LLM パイプライン全体図：[03-llm-pipeline.md](../../../../docs/requirements/2-foundation/03-llm-pipeline.md)
