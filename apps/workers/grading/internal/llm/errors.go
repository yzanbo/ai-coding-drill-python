package llm

// errors.go: LLM 抽象化レイヤが返す共通エラー (sentinel) を集約する。
// 各プロバイダ実装は HTTP ステータス / プロバイダ固有エラーコードを
// ここで定義したセンチネルに正規化して返す。呼び出し側は
// errors.Is(err, llm.ErrRateLimit) のように判定する。

import (
	// errors: errors.New でセンチネルエラーを作る。
	"errors"
)

var (
	// ErrRateLimit: プロバイダのレート制限に到達 (HTTP 429 等)。
	// orchestrator 側で指数バックオフ + リトライを試みる。
	ErrRateLimit = errors.New("llm: provider rate limited")

	// ErrTimeout: 単発呼び出しが Options.Timeout / ctx.Done() で打ち切られた。
	ErrTimeout = errors.New("llm: call timed out")

	// ErrUnauthorized: API キー不正・権限不足 (HTTP 401 / 403)。
	// リトライ不可。設定ミスとして即 fail させる。
	ErrUnauthorized = errors.New("llm: unauthorized")

	// ErrInvalidSchema: JSONMode 強制下で出力が JSONSchema を満たさなかった。
	// 03-llm-pipeline.md の生成フローでは再生成 (上位モデル) に進む。
	ErrInvalidSchema = errors.New("llm: response violates required schema")

	// ErrCostExceeded: ジョブ累積コストが業務上の上限 (USD 0.20 等、
	// problem-generation.md「ビジネスルール」) を超えた。
	// 呼び出し側で再生成を打ち切り failed 扱いにする。
	//
	// 責務境界 (二重カウント / カウント漏れ防止):
	//   - Provider 実装: 単発呼び出しのコストを Response.Usage.CostUSD に
	//     詰めて返す。累積コストは持たない。
	//   - 呼び出し側 (orchestrator / judge): ジョブ単位で CostUSD を
	//     合算し、業務上限と比較する。超過時にこの ErrCostExceeded を
	//     呼び出し元へ返す (Provider 自身がこのエラーを返すことはない)。
	ErrCostExceeded = errors.New("llm: per-job cost cap exceeded")
)

// 未登録 provider 判定用 sentinel は new.go の ErrUnknownProvider を参照。
