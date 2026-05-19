// Package google は LLM プロバイダ抽象化レイヤ (../) の Google Gemini 実装。
//
// SDK は公式の google.golang.org/genai を使う。MVP では Gemini 単独運用で、
// 役割 (generation / regeneration / judge) すべてに gemini-3.5-flash を割り当てる
// (詳細は ADR 0049)。プロバイダの差分 (Anthropic Prompt Caching 等) は
// 各 sub-package に閉じ込め、呼び出し側は llm.Provider interface 経由でしか
// 触れない (ADR 0007)。
//
// 関連:
//   - 抽象化レイヤ親 package:  ../README.md
//   - 設計判断 (抽象化):       ../../../../../docs/adr/0007-llm-provider-abstraction.md
//   - 初期モデル選定:          ../../../../../docs/adr/0049-initial-llm-model-selection.md
//   - Worker 集約:             ../../../../../docs/adr/0040-worker-grouping-and-llm-in-worker.md
//   - 役割別パラメータ既定値:    ../../../../../docs/requirements/2-foundation/03-llm-pipeline.md
//   - 業務側タイムアウト・上限: ../../../../../docs/requirements/4-features/problem-generation.md
package google

import (
	// context: opts.Timeout と呼び出し元 ctx の deadline を尊重する。
	// encoding/json: opts.JSONSchema (raw bytes) を any にデコードして
	//                genai.GenerateContentConfig.ResponseJsonSchema に詰める。
	// errors:  errors.As / errors.Is で genai.APIError / context.DeadlineExceeded を判定。
	// fmt:     エラー wrap で provider 名 / 詳細を残す。
	// strings: 複数 system message の連結、空応答チェック。
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"google.golang.org/genai"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/llm"
)

// Name: Provider 識別子。llm.Register(Name, New) で使う名前と一致させ、
// 観測ログ / メトリクスの provider 属性にも乗る。
// llm.yaml の providers.<role>.provider 値とも一致する必要がある。
const Name = "google"

// Provider: llm.Provider interface を Gemini API に対して実装する型。
// 1 つの Provider が全 Role を担当し、Options.Role で
// llm.Config.RoleConfigFor を引いてモデル ID を切り替える
// (MVP では全ロール同一モデルだが、ロール別モデル切替を将来禁じない設計)。
type Provider struct {
	client *genai.Client
	cfg    llm.Config
}

// New: llm.Config から google Provider を組み立てるファクトリ。
// llm.Register(google.Name, google.New) として登録する想定の signature
// (= llm.ProviderFactory)。
//
// APIKeys[Name] が空なら llm.ErrUnauthorized を wrap して即返す
// (設定ミスを Worker 起動時に検出するため)。
func New(cfg llm.Config) (llm.Provider, error) {
	apiKey, ok := cfg.APIKeys[Name]
	if !ok || apiKey == "" {
		return nil, fmt.Errorf("google: missing API key in Config.APIKeys[%q]: %w", Name, llm.ErrUnauthorized)
	}
	// genai.NewClient: SDK 内部で net/http の default client を使う。
	// 単発呼び出しタイムアウトは Generate 内で context.WithTimeout を被せて制御するため、
	// Client 自体には timeout を設けない。
	client, err := genai.NewClient(context.Background(), &genai.ClientConfig{
		APIKey:  apiKey,
		Backend: genai.BackendGeminiAPI,
	})
	if err != nil {
		return nil, fmt.Errorf("google: NewClient failed: %w", err)
	}
	return &Provider{client: client, cfg: cfg}, nil
}

// Name: llm.Provider interface 実装。観測ログに乗る provider 識別子。
func (p *Provider) Name() string { return Name }

// Generate: Gemini API を 1 回叩いて Response を返す。
//
// 主な処理:
//  1. opts.Role から Config.RoleConfigFor でモデル ID を引く
//  2. opts.Timeout (既定 30 秒) と ctx の deadline を AND 取って context.WithTimeout
//  3. messages の system は SystemInstruction、それ以外は []Content に変換
//  4. Temperature / MaxTokens / JSONMode / JSONSchema を GenerateContentConfig に詰める
//  5. genai.Models.GenerateContent を呼び、エラーは llm の sentinel に正規化
//  6. UsageMetadata からトークン数を取り、pricing.go でドル換算
//
// エラー正規化 (errors.Is で判定可能):
//   - HTTP 429              -> llm.ErrRateLimit
//   - HTTP 401 / 403        -> llm.ErrUnauthorized
//   - context.DeadlineExceeded -> llm.ErrTimeout
//   - 応答 text が空        -> llm.ErrInvalidSchema (JSONMode 強制下で本来あり得ない)
func (p *Provider) Generate(ctx context.Context, messages []llm.Message, opts llm.Options) (llm.Response, error) {
	roleCfg := p.cfg.RoleConfigFor(opts.Role)
	if roleCfg.Model == "" {
		return llm.Response{}, fmt.Errorf("google: empty model for role %q (RoleConfigFor returned blank)", opts.Role)
	}

	timeout := opts.Timeout
	if timeout <= 0 {
		timeout = llm.SingleCallTimeoutDefault
	}
	callCtx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	config, err := buildGenAIConfig(messages, opts)
	if err != nil {
		return llm.Response{}, fmt.Errorf("google: buildGenAIConfig: %w", err)
	}
	contents := buildContents(messages)

	resp, err := p.client.Models.GenerateContent(callCtx, roleCfg.Model, contents, config)
	if err != nil {
		return llm.Response{}, mapError(err, callCtx)
	}

	text := resp.Text()
	if strings.TrimSpace(text) == "" {
		return llm.Response{}, fmt.Errorf("google: empty response text (model=%s): %w", roleCfg.Model, llm.ErrInvalidSchema)
	}

	return llm.Response{
		Content:      text,
		Usage:        extractUsage(resp, roleCfg.Model),
		Provider:     Name,
		Model:        roleCfg.Model,
		CacheHit:     isCacheHit(resp),
		FinishReason: extractFinishReason(resp),
	}, nil
}

// buildContents: llm.Message から genai *Content スライスを作る。
// system は GenerateContentConfig.SystemInstruction に回すためここでは除外する。
// "assistant" は genai.RoleModel、それ以外は genai.RoleUser として扱う。
func buildContents(messages []llm.Message) []*genai.Content {
	contents := make([]*genai.Content, 0, len(messages))
	for _, m := range messages {
		if m.Role == "system" {
			continue
		}
		role := genai.Role(genai.RoleUser)
		if m.Role == "assistant" {
			role = genai.Role(genai.RoleModel)
		}
		contents = append(contents, genai.NewContentFromText(m.Content, role))
	}
	return contents
}

// buildGenAIConfig: llm.Options から genai.GenerateContentConfig を組み立てる。
// JSONMode (response_mime_type=application/json) と JSONSchema (raw bytes) を
// 個別に扱う: JSONSchema のみ指定時は JSONMode を暗黙 ON 扱いにする
// (Gemini 側は schema 指定だけでも application/json で返ってくる)。
func buildGenAIConfig(messages []llm.Message, opts llm.Options) (*genai.GenerateContentConfig, error) {
	cfg := &genai.GenerateContentConfig{}

	if opts.Temperature != nil {
		t := float32(*opts.Temperature)
		cfg.Temperature = &t
	}
	if opts.MaxTokens > 0 {
		// Gemini API は max_output_tokens を int32 で受ける。
		// MaxInt32 を超える値が来た場合は API 側で必ず弾かれるので、
		// ここで上限 clamp して overflow を避ける (gosec G115)。
		const maxInt32 = int(^uint32(0) >> 1)
		v := opts.MaxTokens
		if v > maxInt32 {
			v = maxInt32
		}
		cfg.MaxOutputTokens = int32(v) //nolint:gosec // 直前で int32 範囲に clamp 済み
	}
	if opts.JSONMode || len(opts.JSONSchema) > 0 {
		cfg.ResponseMIMEType = "application/json"
	}
	if len(opts.JSONSchema) > 0 {
		var schemaAny any
		if err := json.Unmarshal(opts.JSONSchema, &schemaAny); err != nil {
			return nil, fmt.Errorf("invalid JSONSchema bytes: %w", err)
		}
		cfg.ResponseJsonSchema = schemaAny
	}
	if sys := extractSystemMessage(messages); sys != "" {
		// SystemInstruction は role を要求するが、user / model のどちらでも
		// 実害が無く、SDK サンプルでも user を使うケースが多いため user で渡す。
		cfg.SystemInstruction = genai.NewContentFromText(sys, genai.Role(genai.RoleUser))
	}
	return cfg, nil
}

// extractSystemMessage: messages から system ロールの content を全て取り出して
// 改行で連結する (Gemini は system instruction を 1 つしか持たないため)。
func extractSystemMessage(messages []llm.Message) string {
	var parts []string
	for _, m := range messages {
		if m.Role == "system" {
			parts = append(parts, m.Content)
		}
	}
	return strings.Join(parts, "\n")
}

// extractUsage: GenerateContentResponse.UsageMetadata から llm.Usage に変換し、
// CostUSD は pricing.go の単価表で計算する。UsageMetadata が nil の場合は
// 全ゼロ (= cost 0) を返し、観測ログで「USD 0.00」が並んだ時に検出できるようにする。
func extractUsage(resp *genai.GenerateContentResponse, model string) llm.Usage {
	if resp == nil || resp.UsageMetadata == nil {
		return llm.Usage{}
	}
	in := int(resp.UsageMetadata.PromptTokenCount)
	// CandidatesTokenCount: 全 candidate の合計出力トークン数。
	// genai SDK の GenerateContentResponse 用 metadata では output 側は
	// ResponseTokenCount ではなく CandidatesTokenCount で公開される (v1.57.0)。
	out := int(resp.UsageMetadata.CandidatesTokenCount)
	return llm.Usage{
		InputTokens:  in,
		OutputTokens: out,
		CostUSD:      calcCostUSD(model, in, out),
	}
}

// isCacheHit: UsageMetadata.CachedContentTokenCount > 0 をキャッシュヒットとみなす。
// Gemini Context Caching の API 仕様 (https://ai.google.dev/gemini-api/docs/caching) 準拠。
func isCacheHit(resp *genai.GenerateContentResponse) bool {
	if resp == nil || resp.UsageMetadata == nil {
		return false
	}
	return resp.UsageMetadata.CachedContentTokenCount > 0
}

// extractFinishReason: 最初の candidate の FinishReason 文字列を返す。
// candidate が無い場合は "unknown" を返し、観測ログで欠落を検出できるようにする。
func extractFinishReason(resp *genai.GenerateContentResponse) string {
	if resp == nil || len(resp.Candidates) == 0 {
		return "unknown"
	}
	return string(resp.Candidates[0].FinishReason)
}

// mapError: genai SDK のエラーを llm package の sentinel に正規化する。
// 呼び出し側は errors.Is(err, llm.ErrRateLimit) 等で判定できる。
//
// context.DeadlineExceeded の判定は err 本体 (errors.Is) と callCtx の状態の
// 両方を見る: SDK が err を返した時点で callCtx が deadline 超過していれば
// 原因は timeout と判断する。
//
// HTTP Code が立っていれば優先し、Code が 0 で Status のみ立っているケース
// (SDK 内部実装変更や gRPC ライク応答) でも RESOURCE_EXHAUSTED 等から
// 同じ sentinel へ正規化する。
func mapError(err error, callCtx context.Context) error {
	if errors.Is(err, context.DeadlineExceeded) || errors.Is(callCtx.Err(), context.DeadlineExceeded) {
		return fmt.Errorf("google: %w: %v", llm.ErrTimeout, err)
	}
	if code, ok := httpStatusCode(err); ok {
		switch code {
		case 429:
			return fmt.Errorf("google: %w (http=%d): %v", llm.ErrRateLimit, code, err)
		case 401, 403:
			return fmt.Errorf("google: %w (http=%d): %v", llm.ErrUnauthorized, code, err)
		}
	}
	if status, ok := apiErrorStatus(err); ok {
		switch status {
		case "RESOURCE_EXHAUSTED":
			return fmt.Errorf("google: %w (status=%s): %v", llm.ErrRateLimit, status, err)
		case "UNAUTHENTICATED", "PERMISSION_DENIED":
			return fmt.Errorf("google: %w (status=%s): %v", llm.ErrUnauthorized, status, err)
		}
	}
	return fmt.Errorf("google: GenerateContent failed: %w", err)
}

// httpStatusCode: err の chain から genai.APIError を取り出し HTTP code を返す。
// SDK 実装が APIError を値 / ポインタどちらで wrap しても拾えるよう両形を試す。
func httpStatusCode(err error) (int, bool) {
	var apiErrPtr *genai.APIError
	if errors.As(err, &apiErrPtr) && apiErrPtr != nil {
		return apiErrPtr.Code, true
	}
	var apiErrVal genai.APIError
	if errors.As(err, &apiErrVal) {
		return apiErrVal.Code, true
	}
	return 0, false
}

// apiErrorStatus: err の chain から genai.APIError を取り出し Status 文字列を返す。
// HTTP Code が 0 のまま Status のみセットされるケース (SDK 内部実装変更 /
// gRPC ライク応答) に備えて httpStatusCode と独立した fallback として使う。
func apiErrorStatus(err error) (string, bool) {
	var apiErrPtr *genai.APIError
	if errors.As(err, &apiErrPtr) && apiErrPtr != nil && apiErrPtr.Status != "" {
		return apiErrPtr.Status, true
	}
	var apiErrVal genai.APIError
	if errors.As(err, &apiErrVal) && apiErrVal.Status != "" {
		return apiErrVal.Status, true
	}
	return "", false
}
