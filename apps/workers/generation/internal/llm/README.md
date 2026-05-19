# internal/llm

## とは何か

LLM プロバイダ（Anthropic / Google / OpenAI / OpenRouter 等）を**差し替え可能**にする抽象化層（[ADR 0007](../../../../docs/adr/0007-llm-provider-abstraction.md)）。`Provider` interface を 1 つ定義し、各プロバイダ実装は `internal/llm/<provider>/` サブ package に置く。R1-2（LLM プロバイダ抽象化フェーズ）で本格実装。

## generation Worker での主用途

- **問題生成本体**：プロンプトから新しい TS 問題（題意 + 期待出力例 + テストコード + 模範解答）を生成
- generation worker は `internal/generation/`（orchestrator）から `llm/` を**直接呼ぶ**（解答評価は `internal/judge/` 経由、生成本体は orchestrator から直接呼ぶ）
- 多軸の prompt（テンプレ / トピック / 難易度 等）を `prompts/generation/*.yaml` から読み込んで投げる

## なぜ `internal/judge/` と分けるか

- `llm/` は **「LLM API を叩く層」**だけを担当（プロバイダ抽象、リトライ、レート制限ハンドリング、コスト計測）
- `judge/` は **「問題評価向けの prompt 整形 + response パース」** を担当し、`llm/` を使う側
- 分けることで `llm/` を「問題生成」と「judge による問題品質評価」の両用途で使い回せる
- 一体化すると provider 切り替えが prompt 構造に縛られる

## 役割（R1-2 で実装）

- `Provider` interface 定義：`Generate(ctx, messages, opts) (Response, error)` 等の最小 API
- 設定で差し替え：`LLM_PROVIDER` 環境変数で `anthropic` / `google` / `openai` / `openrouter` を選ぶ（[Config](../config/README.md)）
- 共通の振る舞い：指数バックオフ・レート制限ヘッダ尊重・**プロンプトキャッシュ**（R2、anthropic SDK の `cache_control` 等）
- コスト計測：input / output token を `internal/observability/` 経由でメトリクスに出す

## sub-package 構造

```
internal/llm/
├── provider.go              # Provider interface（公開）
├── errors.go                # ErrLLMRateLimit 等の共通エラー
├── anthropic/               # Anthropic Claude 実装
├── google/                  # Google Gemini 実装
├── openai/                  # OpenAI GPT 実装
└── openrouter/              # OpenRouter 経由実装
```

各 sub-package は親 `llm/` の interface のみ参照し、**互いに依存しない**。

## 両 Worker での扱い

- grading: `judge/` 経由で「解答評価」用に使う
- generation: 主に「問題生成」用に使う + `judge/` 経由で「問題評価」にも使う
- **同名 package を両 Worker に置く**：Go の `internal/` 規約と独立 module（[ADR 0040](../../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）のため、当面コード重複を許容する（将来共通 module 切り出しを検討）
- generation での judge 評価は grading で使うのと**別 provider**で動かしてバイアスを下げる戦略がある（[03-llm-pipeline.md](../../../../docs/requirements/2-foundation/03-llm-pipeline.md)）。**MVP は Gemini 単独で例外保留**、R2 ベンチマーク開始時に切替（→ [ADR 0049](../../../../docs/adr/0049-initial-llm-model-selection.md)）

## やってはいけないこと

- プロバイダ SDK を `internal/llm/` 外から**直接 import**：必ず `Provider` interface 経由（[worker-layers.md §E §13](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- `apps/api/` 側で LLM を呼ぶ：LLM は Worker に閉じる（[ADR 0040](../../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)）
- 別 Worker module から `import`：`apps/workers/grading/` から `apps/workers/generation/internal/llm/` は `internal/` 規約で禁止（[worker-layers.md §E §5](../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- API キーをコードに埋め込む：`config.Load()` 経由で環境変数から取得

## 関連

- 規約 SSoT：[.claude/rules/worker.md「LLM 呼び出し」セクション](../../../../.claude/rules/worker.md)
- 抽象化方針：[ADR 0007](../../../../docs/adr/0007-llm-provider-abstraction.md)
- Worker 集約：[ADR 0040](../../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)
- LLM パイプライン全体図：[03-llm-pipeline.md](../../../../docs/requirements/2-foundation/03-llm-pipeline.md)
