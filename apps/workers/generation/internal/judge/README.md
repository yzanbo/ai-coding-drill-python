# internal/judge

## とは何か

「**LLM-as-a-Judge**（LLM に評価させる）」のロジックを置く package。generation worker では**生成された問題の品質**を評価する（題意の明確さ・難易度・テストの妥当性・模範解答との整合性 等）。`internal/llm/` の `Provider` interface を呼び出して使う側（[ADR 0008](../../../../docs/adr/0008-custom-llm-judge.md)）。

## grading worker の judge との違い

- grading worker：受験者の**解答**を評価
- generation worker：LLM が生成した**問題**を評価
- 評価軸（rubric）が違うため prompts も別物：[prompts/judge/](../../prompts/judge/) を generation 専用に整備（[ADR 0040](../../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)、両 Worker でプロンプトは同居しない）
- 評価の信頼性を上げるため、**generation で使う judge は問題生成と別の provider** で動かす戦略がある（[03-llm-pipeline.md](../../../../docs/requirements/2-foundation/03-llm-pipeline.md)）

## 役割

- プロンプト YAML 読み込み：`apps/workers/generation/prompts/judge/*.yaml` から評価指示を取り込む
- 入力データを差し込み：`{{.problem}}` / `{{.reference_solution}}` / `{{.sandbox_result}}` 等のテンプレ変数を置換
- `internal/llm.Provider.Generate(ctx, messages, opts)` を呼んで LLM の応答を取得
- 応答パース：JSON スキーマで構造化された judge verdict（多軸スコア + 理由テキスト）に変換
- リトライ判定：「応答が JSON 構造を満たさない」等の回復可能エラーは指数バックオフで再試行

## なぜ `internal/llm/` と分けるか

- `llm/` は「API を叩く層」、`judge/` は「**generation 専用の prompt と response の整形層**」
- judge prompt の差し替えや評価軸の調整が `llm/` の provider 切り替えと独立にできる
- grading worker でも同名 package を持つが、prompt と評価軸が異なる（grading worker は解答評価、generation worker は問題評価）

## 多回実行と平均化

- 単一の LLM 応答はばらつくため、**3〜5 回呼び出して平均**する（R2 で実装、[ADR 0008](../../../../docs/adr/0008-custom-llm-judge.md)）
- 異常値（極端な外れ値）は除外する

## やってはいけないこと

- `internal/llm/` の **provider SDK を直接 import**：必ず `Provider` interface 経由（[worker-layers.md §E §13](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- `internal/sandbox/` を import：同 Layer 1 内の横断は禁止、orchestrator（`internal/generation/`）経由にする（[worker-layers.md §E §2](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- プロンプトを **Go コードに hardcode**：すべて `prompts/judge/*.yaml` に外出しし、差し替え可能にする（[ADR 0040](../../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）
- judge の判定で `panic`：応答パース失敗は通常エラーで返し、上位（orchestrator）で「リトライ可能か」を判定

## 関連

- 規約 SSoT：[.claude/rules/worker.md「LLM 呼び出し」セクション](../../../../.claude/rules/worker.md)
- 評価戦略：[ADR 0008](../../../../docs/adr/0008-custom-llm-judge.md)（自前 LLM-as-a-Judge）
- prompts：[apps/workers/generation/prompts/judge/](../../prompts/judge/)（実装着手時に配置）
- 多層防御：[03-llm-pipeline.md](../../../../docs/requirements/2-foundation/03-llm-pipeline.md)
