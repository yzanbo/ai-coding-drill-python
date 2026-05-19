# internal/llm/google

## とは何か

[親 package `internal/llm/`](../README.md) の `Provider` interface を **Google Gemini API** に対して実装する sub-package。

SDK は公式の [`google.golang.org/genai`](https://pkg.go.dev/google.golang.org/genai) を採用（[ADR 0007: LLM プロバイダ抽象化戦略](../../../../../docs/adr/0007-llm-provider-abstraction.md) で「ベンダー差分は sub-package に閉じ込め、各 sub-package が最適 SDK を独立選定してよい」と決定済み）。

## MVP での役割

[ADR 0049: 初期 LLM モデル選定](../../../../../docs/adr/0049-initial-llm-model-selection.md) により、**MVP は Gemini 単独運用**。`generation` / `regeneration` / `judge` の全ロールに `gemini-3-flash` を割り当て、起動確認が取れた後に R2 ベンチマーク開始時点で `judge` を別ベンダーへ切替える計画（ADR 0008「Judge は別プロバイダ」例外保留中）。

## ファイル構成

| ファイル | 役割 |
|---|---|
| [provider.go](./provider.go) | `Provider` interface 実装本体（`Generate` / `Name`）、エラー正規化、SystemInstruction 抽出、Usage 抽出 |
| [pricing.go](./pricing.go) | モデル単価表（USD / 1M tokens、ADR 0049 が SSoT） |
| [provider_test.go](./provider_test.go) | helpers の unit test（ネットワーク叩かない） |
| [provider_integration_test.go](./provider_integration_test.go) | 実 Gemini API を叩く統合テスト。**build tag `integration` で隔離**、デフォルトの `go test ./...` では走らない |

## 統合テストの走らせ方

`provider_integration_test.go` は build tag `integration` で隔離されており、`GOOGLE_API_KEY` が設定されている時のみ実行する：

```bash
GOOGLE_API_KEY=xxxxx go test -tags=integration ./internal/llm/google/...
```

API キー未設定の状態でも tag を有効化すれば test 自体は走るが、`t.Skip` で抜ける。CI ではコスト / 鍵管理の都合上、本テストは走らせない。

## 登録方法（cmd/grading/main.go から）

`llm` package は本 sub-package を直接 import しない（循環インポート回避）。代わりに main で **registration pattern** を使う（→ [internal/llm/new.go](../new.go) の `Register` / `New`）：

```go
import (
    "github.com/yzanbo/.../apps/workers/grading/internal/llm"
    "github.com/yzanbo/.../apps/workers/grading/internal/llm/google"
)

func main() {
    llm.Register(google.Name, google.New)  // "google" を factory map に登録
    provider, err := llm.New(cfg)          // cfg.Generation.Provider == "google" なら google.New が呼ばれる
}
```

## エラー正規化

genai SDK が返すエラーは `Generate` 内で [llm の sentinel](../errors.go) に正規化する。呼び出し側は `errors.Is(err, llm.ErrXxx)` で判定可能：

| 元エラー | 正規化先 |
|---|---|
| HTTP 429 / `Status="RESOURCE_EXHAUSTED"` | `llm.ErrRateLimit` |
| HTTP 401 / 403 / `Status="UNAUTHENTICATED"` / `Status="PERMISSION_DENIED"` | `llm.ErrUnauthorized` |
| `context.DeadlineExceeded`（単発 30 秒 or ジョブ累積 180 秒） | `llm.ErrTimeout` |
| 応答 text が空（JSONMode 強制下） | `llm.ErrInvalidSchema` |

HTTP Code が 0 のまま Status のみセットされる SDK 内部実装変更にも耐性を持たせるため、`mapError` は `APIError.Code` と `APIError.Status` の両方を見る（[provider.go](./provider.go) の `httpStatusCode` / `apiErrorStatus` 参照）。

`ErrCostExceeded` は **呼び出し側**（orchestrator / judge）がジョブ単位の累積コストで判定し返す（[llm/errors.go](../errors.go) §責務境界）。Provider 自身はこのエラーを返さない。

## 観測ログ DoD への寄与

[problem-generation.md「観測ログ DoD」](../../../../../docs/requirements/4-features/problem-generation.md#ビジネスルール) で必須となる以下を `Response` 構造体に詰めて返す：

- `provider` / `model`：それぞれ `"google"` / `cfg.Generation.Model` 等
- `input_tokens` / `output_tokens`：`UsageMetadata.PromptTokenCount` / `CandidatesTokenCount`（genai v1.57.0 では output 側は `CandidatesTokenCount` で公開される、全 candidate 合計）
- `cost_usd`：`pricing.go` の単価表で計算
- `cache_hit`：`UsageMetadata.CachedContentTokenCount > 0`
- `finish_reason`：先頭 candidate の FinishReason

呼び出し側（orchestrator / judge）はこれらをそのまま `slog.InfoContext` / OTel span 属性に乗せれば DoD を満たす。

## やってはいけないこと

- `genai` SDK を本 sub-package **外**から直接 import：必ず `llm.Provider` interface 経由（[worker-layers.md §E §13](../../../../../docs/requirements/5-roadmap/r0-setup/worker-layers.md)）
- API キーをコードに埋め込む：`cfg.APIKeys["google"]` 経由でのみ受け取り、未設定時は `llm.ErrUnauthorized` を返す
- `pricing.go` の単価表を勝手に書き換える：必ず ADR 0049 と同時更新する
- ロール別モデル切替を Provider 内で勝手に解釈：必ず `llm.Config.RoleConfigFor(opts.Role)` を引いて行う

## 関連

- 親 package：[internal/llm/](../README.md)
- 抽象化戦略：[ADR 0007](../../../../../docs/adr/0007-llm-provider-abstraction.md)
- 初期モデル選定：[ADR 0049](../../../../../docs/adr/0049-initial-llm-model-selection.md)
- Worker 集約：[ADR 0040](../../../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md)
- 役割別パラメータ：[03-llm-pipeline.md「構造化出力」](../../../../../docs/requirements/2-foundation/03-llm-pipeline.md#構造化出力)
- 業務制約：[problem-generation.md「ビジネスルール」](../../../../../docs/requirements/4-features/problem-generation.md#ビジネスルール)
