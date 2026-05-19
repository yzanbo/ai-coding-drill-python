package google

// pricing.go: Gemini モデルの公開単価表 (USD / 1M tokens, 2026-05 時点)。
//
// SSoT: ADR 0049 (../../../../../docs/adr/0049-initial-llm-model-selection.md)。
// 価格改定が発生したら ADR 本文 (§Context の価格表) と本ファイルを同時更新する。
// 二重管理を避けるため、本ファイルの数値は ADR 0049 と必ず一致させる。
//
// 単価表に無いモデル ID では cost 0 を返す: 観測ログで「USD 0.00 が連続」と
// 並んだ時に「単価表に追記漏れがある」と検出できるようにする意図
// (silent に推測単価を当てると判別不能になる)。

// modelPricing: 1 モデル分の input / output 単価 (USD / 1M tokens)。
type modelPricing struct {
	InputUSDPer1M  float64
	OutputUSDPer1M float64
}

// pricingTable: モデル ID -> 単価。
// 出典は ADR 0049 §Context の価格表 (2026-05 時点)。
//
// gemini-3.5-flash は公式 pricing ページに未掲載のため、
// gemini-3-flash-preview と同単価を暫定値として置く (ADR 0049 §Context
// 参照、最安 flash + 無料枠の意図と整合)。Google が公式公開した時点で
// 確定値に差し替える (本ファイル + ADR 0049 同時更新)。
var pricingTable = map[string]modelPricing{
	// gemini-3.5-flash: 暫定 = gemini-3-flash-preview 同等
	"gemini-3.5-flash":       {InputUSDPer1M: 0.50, OutputUSDPer1M: 3.00},
	"gemini-3-flash-preview": {InputUSDPer1M: 0.50, OutputUSDPer1M: 3.00},
	"gemini-3.1-flash-lite":  {InputUSDPer1M: 0.25, OutputUSDPer1M: 1.50},
	"gemini-3.1-pro-preview": {InputUSDPer1M: 2.00, OutputUSDPer1M: 12.00},
}

// calcCostUSD: input / output トークン数からドル換算する。
// 単価表に無いモデル ID では 0 を返す (上記コメント参照)。
func calcCostUSD(model string, inputTokens, outputTokens int) float64 {
	p, ok := pricingTable[model]
	if !ok {
		return 0
	}
	return float64(inputTokens)*p.InputUSDPer1M/1_000_000 +
		float64(outputTokens)*p.OutputUSDPer1M/1_000_000
}
