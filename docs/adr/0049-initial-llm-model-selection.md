# 0049. 初期 LLM モデル選定（MVP は Gemini 単独で起動確認、抽象化レイヤで切替可能性は保持）

- **Status**: Accepted
- **Date**: 2026-05-19
- **Decision-makers**: 神保 陽平

## Context（背景・課題）

ロードマップ R1-2「LLM プロバイダ抽象化レイヤ + 初期モデル選定（Worker 側に集約、実装着手時に確定）」で、抽象化レイヤ skeleton 配置と並んで初期モデルを確定する必要がある（[ADR 0007: モデル選定の運用方針](./0007-llm-provider-abstraction.md#モデル選定の運用方針)）。

- 本サイトはポートフォリオ用途で、**「LLM を呼んで問題生成・評価ができる」起動確認が取れれば MVP の体裁が成立する**
- R2 で評価パイプライン（judge / mutation / 集合的評価）を入れた後にプロバイダ横断ベンチマークを行う計画は ADR 0007 で確定済み
- LLM 市場は 2026 年に入って Gemini 3 系・Claude 4.x 系・GPT-5 系が出揃い、半年単位で価格・性能が動く状況
- 抽象化レイヤ（`apps/workers/grading/internal/llm/`）は R1-2 で配置済みで、YAML 1 行でプロバイダを切り替えられる構造

参考にした情報源：

- [Gemini API ドキュメント（2026-05 時点）](https://ai.google.dev/gemini-api/docs/models)：実 API v1beta で `generateContent` が叩ける flash 系 stable は `gemini-3.5-flash` / `gemini-3.1-flash-lite` / `gemini-2.5-flash` / `gemini-2.0-flash`、preview は `gemini-3-flash-preview` / `gemini-3.1-flash-lite-preview`。pro 系は `gemini-3-pro-preview` / `gemini-3.1-pro-preview`（preview のみ）
- 2026-04-01 から Gemini Pro は有料化、Flash / Flash-Lite は無料枠維持（無料枠は日次クォータ縮小済み）
- 価格（2026-05 時点、$/1M tokens、[公式 pricing ページ](https://ai.google.dev/gemini-api/docs/pricing)）：
  - `gemini-3.5-flash`: **公式未掲載**。`gemini-3-flash-preview` と同等の input $0.50 / output $3.00 を暫定値として運用（無料枠あり）
  - `gemini-3-flash-preview`: input $0.50 / output $3.00（無料枠あり）
  - `gemini-3.1-flash-lite`: input $0.25 / output $1.50（無料枠あり）
  - `gemini-3.1-pro-preview`: input $2.00 / output $12.00（< 200K context、preview のみ）

## Decision（決定内容）

**MVP の初期 LLM プロバイダは Google Gemini 単独**とし、3 ロール（`generation` / `regeneration` / `judge`）すべてに `gemini-3.5-flash` を割り当てる。ADR 0008「生成と Judge は別ベンダー」の方針は R2 のベンチマーク開始時点まで例外的に保留する。

> **モデル ID の訂正経緯**：本 ADR の初版は `gemini-3-flash`（preview suffix 落ち）を採用 model として指定していたが、R1-2 後半の integration test で v1beta API に該当モデル ID が存在しないことが判明（HTTP 404 NOT_FOUND）。Google AI Studio `models.list` で実在する flash 系 stable のうち、当初意図（最安 + 無料枠付き + 3.x 世代）に最も近い `gemini-3.5-flash` に訂正。公式 pricing ページに `gemini-3.5-flash` 単価が未掲載のため、`gemini-3-flash-preview` と同等（input $0.50 / output $3.00）を [pricing.go](../../apps/workers/grading/internal/llm/google/pricing.go) で暫定値として運用、公式公開時に確定値へ差し替える。

### 役割 × モデル割り当て（YAML SSoT は実装時に `apps/workers/grading/llm.yaml` 等で配置）

| ロール | プロバイダ | モデル ID | 既定 temperature |
|---|---|---|---|
| `generation` | google | `gemini-3.5-flash` | 0.7 |
| `regeneration` | google | `gemini-3.5-flash` | 0.7 |
| `judge` | google | `gemini-3.5-flash` | 0.0 |

設定形式は ADR 0007 §設定駆動の切替に従う：

```yaml
providers:
  generation:   { provider: google, model: gemini-3.5-flash }
  regeneration: { provider: google, model: gemini-3.5-flash }
  judge:        { provider: google, model: gemini-3.5-flash }
```

`temperature` / `max_tokens` / `json_mode` の役割別既定値は **[03-llm-pipeline.md: 構造化出力](../requirements/2-foundation/03-llm-pipeline.md#構造化出力)** が SSoT。Go 定数として **[apps/workers/grading/internal/llm/provider.go の DefaultOptions(Role)](../../apps/workers/grading/internal/llm/provider.go)** に固定済み（数値が二重管理にならない構造）。

### ADR 0008「生成と Judge は別ベンダー」の例外運用

- ADR 0008 は自己評価バイアス回避のため別ベンダー化を求めるが、**R2 ベンチマーク開始までは Gemini 単独**で運用する
- 理由：ポートフォリオ用途で「起動確認」が成立すれば十分、複数 API キー管理 / 複数プロバイダ実装の初期負担を R2 まで遅延させる
- R2 着手時に `judge` ロールを Anthropic（`claude-haiku-4-5` 等）に切替えることを既定計画とする（YAML 1 行 + Anthropic sub-package 実装で済む）

### 実装の優先順位

1. R1-2（**完了**）：`apps/workers/grading/internal/llm/google/` sub-package で Provider interface を Gemini API に対して実装
   - ✅ Provider interface 実装（[provider.go](../../apps/workers/grading/internal/llm/google/provider.go)）
   - ✅ JSON mode 強制（`ResponseMIMEType=application/json`）
   - ✅ cost 計算（[pricing.go](../../apps/workers/grading/internal/llm/google/pricing.go)、本 ADR の価格表が SSoT）
   - ✅ registration pattern + `llm.yaml` + `internal/config/` + `cmd/grading/main.go` 結線
   - ⏳ OTel span 統合 → **R4「観測性」** で追加（OpenTelemetry SDK 組み込みと Grafana / Tempo 等の収集基盤が R4 で揃うため、LLM スパンだけ先行で出しても可視化先がない。[01-roadmap.md L113](../requirements/5-roadmap/01-roadmap.md) の R4 項目を参照）
   - ⏳ 指数バックオフリトライ → **R1-3「問題生成リクエスト」** で追加（orchestrator (`internal/grading/`) が provider を呼び始めるタイミングと同時に 429 リトライを `google/provider.go` の `Generate` 内ループとして入れるのが自然。なお **ジョブレベル**のリトライ・DLQ・スタックジョブ回収は別概念で R2「非同期ジョブ化の完全実装」に属する）
2. R2：ベンチマーク基盤を作って Anthropic / OpenAI / OpenRouter の sub-package を追加。`judge` ロールを別ベンダーに切替

## Why（採用理由）

1. **ポートフォリオ用途では「動く」ことが最優先**
   - 「LLM を呼んで問題生成・評価ができる」起動確認が取れれば MVP の体裁が成立する
   - 複数プロバイダを最初から並べる初期コストは、ベンチマーク基盤がない段階では正当化できない
2. **Gemini Flash は無料枠が厚く、ローカル開発 + ポートフォリオ閲覧時のコストがほぼゼロ**
   - Anthropic / OpenAI は無料枠なし、Gemini は 2026-04 以降も Flash / Flash-Lite で無料枠維持
   - 採用担当者がデモを触る際にコスト懸念なく LLM 機能を見せられる
3. **抽象化レイヤで切替可能性が既に確保されている**
   - ADR 0007 + R1-2 で配置した `internal/llm/` skeleton で、`Provider` interface 経由でしか LLM に触れない構造になっている
   - YAML 設定 1 行で別プロバイダに切り替えられるため、初期 1 ベンダーの選択は不可逆ではない
4. **R2 ベンチマーク前に「最適モデル」を議論しても無駄**
   - ADR 0007「品質の主因はモデルではなくプロンプト × 評価 × キャッシュ戦略」に沿い、R2 評価基盤が立ち上がってから実データで選び直す
   - MVP では「動作することを示す」以外の選定根拠はベンチマーク不在で全て主観
5. **`gemini-3.5-flash` は構造化出力（JSON mode）と関数呼び出しを安定サポート**
   - 03-llm-pipeline.md「構造化出力」で必須要件としている JSON mode 強制が Gemini API の `response_mime_type: application/json` + `response_schema` で実現できる
   - quicktype で生成した Go struct によるバリデーション（[ADR 0006](./0006-json-schema-as-single-source-of-truth.md)）と組み合わせて 2 段防御が成立する
6. **2026-06-01 に Gemini 2.0 系がシャットダウンするため、3 系を初期採用するのが最も賢い**
   - 2.0 Flash / 2.0 Flash-Lite は 2026-02-18 deprecated → 2026-06-01 shutdown
   - 3 系を初手で採用すれば、シャットダウンに伴う移行作業を回避できる

## Alternatives Considered（検討した代替案）

| 候補 | 概要 | 採用しなかった理由 |
|---|---|---|
| 全ロール Gemini（採用、Flash 単独） | （採用） | — |
| ロール別 Gemini（generation = Flash / judge = Flash-Lite or Pro） | 同ベンダー内で価格段差をつける | MVP 起動確認では差別化価値が薄い、Flash 単一の方が運用シンプル |
| ベンダー混合（generation = Anthropic Haiku 4.5 / judge = Gemini） | ADR 0008「別ベンダー」を最初から満たす | 複数 API キー + 2 sub-package 実装が必要、R2 で同じ作業をするので前倒し価値が薄い |
| 全ロール Anthropic Claude（Haiku 4.5 / Sonnet 4.6） | TS コード生成品質に定評 | 無料枠なし、ポートフォリオ閲覧時のコストが読みづらい |
| 全ロール OpenAI（GPT-5-mini） | function calling 安定 | 無料枠なし、最新版数 (2026-05) で価格が動きやすい |
| 全ロール OpenRouter（DeepSeek V3 等の集約） | 安価、自前 API キー集約 | 第二段リクエストのレイテンシが高い、評価ベンチマークが OpenRouter 経由で混在しやすい |
| プロバイダ未確定（ADR を起票のみ、選定は実装時） | R1-2 の判断を後ろ倒し | Provider interface を満たす具体実装が無いと R1-2 完了とは言えない |

## Consequences（結果・トレードオフ）

### 得られるもの

- MVP の LLM パイプラインが Gemini Flash 1 本で動作確認できる（無料枠の範囲内でローカル + ポートフォリオ運用が完結）
- 抽象化レイヤと相まって「R2 でベンチマークしてから本格選定する」という設計判断を採用担当者に説明できる
- Gemini 3 系を初手採用することで 2.0 系シャットダウン（2026-06-01）の影響を完全に回避

### 失うもの・受容するリスク

- ADR 0008「自己評価バイアス回避」が MVP 段階では成立しない（同一モデルが生成と Judge を兼ねるため）。これは R2 ベンチマーク開始時に解消する前提でリスク受容
- Gemini 単独依存により、Google 側の障害・規約変更・価格改定が直接 MVP の稼働に影響する。抽象化レイヤがあるため切替は容易だが、別プロバイダの sub-package 実装は必要
- Anthropic Prompt Caching のような特定ベンダー固有の最適化を MVP では使えない（Gemini Context Caching は使える）

### 将来の見直しトリガー

- **R2 ベンチマーク基盤の稼働開始**：ADR 0008「別ベンダー Judge」を有効化する標準タイミング。第 2 プロバイダ（Anthropic Haiku 4.5 を有力候補とする）を `judge` ロールに割り当て直す
- **Gemini API の価格改定 / 無料枠廃止**：無料枠が事実上消えた時点で別プロバイダへの移行コストを再評価
- **Gemini 3 系のシャットダウン予告**：2.0 系と同様の deprecation サイクルに入ったら次世代モデルへの移行 ADR を起票
- **生成品質が「全く使えない」レベルだった場合**：Anthropic / OpenAI の最上位モデルへの即時切替を検討（ベンチマーク不在でも実用判定で動ける）

## References

- [ADR 0007: LLM プロバイダ抽象化戦略](./0007-llm-provider-abstraction.md)
- [ADR 0008: LLM-as-a-Judge を自前実装](./0008-custom-llm-judge.md)
- [ADR 0040: Worker のグルーピングと LLM 呼び出しを Worker 側に置く](./0040-worker-grouping-and-llm-in-worker.md)
- [03-llm-pipeline.md: モデル選定ポリシー](../requirements/2-foundation/03-llm-pipeline.md#モデル選定ポリシー)
- [problem-generation.md: ビジネスルール](../requirements/4-features/problem-generation.md#ビジネスルール)
- [apps/workers/grading/internal/llm/provider.go](../../apps/workers/grading/internal/llm/provider.go)（Provider interface + DefaultOptions）
- [Gemini API モデル一覧](https://ai.google.dev/gemini-api/docs/models)
- [Gemini API 価格表](https://ai.google.dev/gemini-api/docs/pricing)
