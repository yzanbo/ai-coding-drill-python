package llm

// config.go: 役割ごとの (provider, model) を選ぶ設定。
// YAML 上の形 (ADR 0007 §設定駆動の切替):
//
//   providers:
//     generation:    { provider: <vendor>, model: <model-id> }
//     regeneration:  { provider: <vendor>, model: <model-id> }
//     judge:         { provider: <vendor>, model: <model-id> }
//
// R1-2 skeleton では struct のみ定義。YAML 読み込み実装は config/ で行い、
// この struct を埋めて New() に渡す。

// RoleConfig: 1 ロール分の (provider, model) 指定。
type RoleConfig struct {
	// Provider: "anthropic" / "google" / "openai" / "openrouter" 等。
	Provider string
	// Model: ベンダー側のモデル ID。具体値は ADR 0049 (初期モデル選定) を SSoT とする。
	Model string
}

// Config: LLM 抽象化レイヤ全体の設定。
// 役割ごとに別 provider/model を持てる構造になっており、生成と Judge を
// 別ベンダーで動かす運用 (ADR 0008「自己評価バイアス回避」) を要件として
// 表現する。MVP は Gemini 単独運用で ADR 0008 を例外保留し、R2 ベンチマーク
// 開始時に別ベンダー Judge へ切替える (ADR 0049)。
type Config struct {
	Generation   RoleConfig
	Regeneration RoleConfig
	Judge        RoleConfig
	// APIKeys: provider 名 -> API キー (環境変数経由で main で詰める想定)。
	// config package を import できない (Layer 0 制約) ため map で受け取る。
	APIKeys map[string]string
}

// RoleConfigFor: 指定ロールに対応する RoleConfig を返す。
// orchestrator や judge から「自分のロールはどの (provider, model) か」を
// 引きやすくするためのヘルパ。
//
// 既知ロール (RoleGeneration / RoleRegeneration / RoleJudge) 以外を
// 渡した場合は panic する。Role 値は package 内 const で網羅される
// enum であり、未知ロールが渡るのは「新規 Role 追加時の switch 追従漏れ」
// または「Role(string) で外部入力を直接キャストした」のいずれかで
// プログラマエラーに該当する (config / YAML からの role 文字列は
// バリデーション層で正規化してから渡す前提)。
// silent に空 RoleConfig を返すと、空 Provider 文字列のまま LLM ファクトリに
// 渡って遠い場所での「API キーが見つからない」エラーになり、原因究明が
// 困難になる。
func (c Config) RoleConfigFor(role Role) RoleConfig {
	switch role {
	case RoleGeneration:
		return c.Generation
	case RoleRegeneration:
		return c.Regeneration
	case RoleJudge:
		return c.Judge
	default:
		panic("llm: unknown role: " + string(role))
	}
}
