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
// 表現する。
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
func (c Config) RoleConfigFor(role Role) RoleConfig {
	switch role {
	case RoleGeneration:
		return c.Generation
	case RoleRegeneration:
		return c.Regeneration
	case RoleJudge:
		return c.Judge
	default:
		return RoleConfig{}
	}
}
