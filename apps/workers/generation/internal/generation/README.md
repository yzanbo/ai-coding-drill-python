# internal/generation（問題生成フローの**オーケストレーター**）

## とは何か

問題生成ジョブ 1 件を処理するための**段取り役**。`internal/job/`（取得）→ `internal/llm/`（問題生成 LLM 呼び出し）→ `internal/sandbox/`（模範解答の動作確認）→ `internal/judge/`（生成された問題の品質評価）→ `internal/db/`（`problems` テーブルへの INSERT + ジョブ完了）の順に呼び出し、各ステップのエラーハンドリング・リトライ判断・タイムアウトを 1 箇所に集約する。

## なぜ main.go に inline せず別 package か

- フロー全体が 100〜200 行規模になり、main.go に詰めると「組み立て」「シグナル」「フロー」が混在して見通しが悪い
- `generation.Process(ctx, deps, job)` を **テストで fake deps を注入して呼べる**形にしたい
- 将来別の生成ジョブ種別（テンプレ別・難易度別 等）が増えたとき、main.go の dispatch だけ拡張すれば本体は触らない

## 問題生成 1 件のスパン構成（observability で計測する目印）

```
[generate_problem_job]
  ├─ [job.claim]                ジョブ取得 SQL
  ├─ [generation.invoke]        生成 LLM 呼び出し（ADR 0040）
  ├─ [schema.validate]          JSON Schema → quicktype 生成 Go struct でバリデーション
  ├─ [sandbox.run]              模範解答を sandbox で実行して動作確認
  ├─ [judge.invoke]             別プロバイダ judge で問題品質を評価（MVP は Gemini 単独で例外保留、R2 で切替 / ADR 0049）
  └─ [job.complete]             problems テーブル INSERT + state='done' 更新
```

各スパンは `internal/observability/` 経由で自動的に trace に乗る（`Process` は呼び出すだけ）。

## 役割

- `Process(ctx, deps, job) (jobtypes.GenerationResult, error)`：1 ジョブの全段取り
- `Deps` 構造体：`Pool` / `LLM` / `Sandbox` / `Judge` などの依存を interface 経由で受け取る（テストで差し替え可能に）
- 多段防御の実装：「LLM が出した問題が JSON スキーマを満たすか」→「模範解答が sandbox で実際に通るか」→「judge LLM が品質を OK と評価するか」を順に確認、どれかで NG なら問題を弾く（or 再生成）
- リトライ判定：エラー種別ごとに「再試行可能」or「即 dead」を分岐
- パニック吸収：`recover()` でログ → ジョブ failed 状態 → Worker 本体は継続
- タイムアウト：`JOB_TIMEOUT_SECONDS`（`internal/config/`、生成 LLM 呼び出しが長いため grading より大きい値）を `context.WithTimeout` で適用

## grading の orchestrator との違い

- grading orchestrator は **judge 評価が主**で、sandbox は受験者の解答実行に使う
- generation orchestrator は **LLM 直接呼び出し（問題生成）+ sandbox（模範解答検証）+ judge（生成物評価）** の 3 つを順に重ねる多段構造
- どちらも構造（layer 図）は同じだが、データの流れと重みが異なる

## やってはいけないこと

- 別のフローを足すたびにファイルを増やす：1 ファイル `process.go` を中心に、ステップごとに非エクスポート関数で分割する程度に留める
- 上位（`cmd/generation/main.go`）が `process` の内部に直接介入する：main.go は組み立て + 起動 + シグナル受信だけ
- `internal/llm/` 直接呼び出しと `internal/judge/` 経由を混在させる場面でルールを忘れる：問題**生成**は `llm/` 直接、問題**評価**は `judge/` 経由（[worker-layers.md §C](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- 1 ジョブ内で goroutine を多用：複数ジョブの並列処理は main.go の goroutine pool で行う、1 ジョブの中身は順次処理

## 関連

- 規約 SSoT：[.claude/rules/worker.md](../../../../.claude/rules/worker.md)
- 問題生成要件：[problem-generation.md](../../../../docs/requirements/4-features/problem-generation.md)
- LLM パイプライン全体図：[03-llm-pipeline.md](../../../../docs/requirements/2-foundation/03-llm-pipeline.md)
