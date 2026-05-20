//go:build integration

package grading

// generation_smoke_integration_test.go: 実 Gemini API に問題生成プロンプト v2 を
// 5 回投げて、ProblemDraft として parse + validate 通過する割合を観測する smoke。
//
// 用途:
//   - prompts/generation/problem-gen.vN.yaml を更新した時の手元動作確認
//   - test_cases[i].input が配列で返る・reference_solution が export function solve 形で
//     返るといった v2 で厳密化した契約が、実 LLM で守られるかを観測
//
// 走らせる例:
//   GOOGLE_API_KEY=xxxxx go test -tags=integration \
//     -run TestGenerate_Integration_Smoke5 -v \
//     ./internal/grading/...
//
// 失敗判定:
//   - 5 回中 4 回以上成功で pass (1 件の transient flake は許容)
//   - それ未満なら fail。LLM の出力ばらつきが許容範囲を超えたサイン
//
// 不変条件チェック (validate 通過後):
//   - 全 test_cases[i].input が配列であること (TestCase.Input []any で構造的に保証されるが
//     念のため再確認、長さ 0 の input も認める)
//   - reference_solution に `export function solve` を含むこと

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/llm"
	"github.com/yzanbo/ai-coding-drill-python/apps/workers/grading/internal/llm/google"
)

func TestGenerate_Integration_Smoke5(t *testing.T) {
	apiKey := os.Getenv("GOOGLE_API_KEY")
	if apiKey == "" {
		t.Skip("GOOGLE_API_KEY 未設定のため skip")
	}

	// prompt YAML 解決: テスト cwd は internal/grading/ なので 3 階層上の
	// apps/workers/grading/prompts/... を指す。
	promptPath, err := filepath.Abs(filepath.Join("..", "..", "prompts", "generation", "problem-gen.v2.yaml"))
	require.NoError(t, err)
	prompt, err := LoadGenerationPrompt(promptPath)
	require.NoError(t, err, "v2 prompt の load が成功するべき")
	t.Logf("prompt loaded: path=%s version=%s hash=%s", prompt.Path(), prompt.Version, prompt.Hash()[:12])

	// llm.Provider を組み立て: Generation ロールに gemini-2.5-flash を割り当てる。
	// 5 回回しても安価に収まるモデル。
	llm.Register(google.Name, google.New)
	provider, err := llm.New(llm.Config{
		Generation:   llm.RoleConfig{Provider: google.Name, Model: "gemini-2.5-flash"},
		Regeneration: llm.RoleConfig{Provider: google.Name, Model: "gemini-2.5-flash"},
		Judge:        llm.RoleConfig{Provider: google.Name, Model: "gemini-2.5-flash"},
		APIKeys:      map[string]string{google.Name: apiKey},
	})
	require.NoError(t, err)

	gen := NewProblemGenerator(prompt, provider)

	// 5 回分の入力。category / difficulty をばらつかせて偏りを減らす。
	cases := []struct {
		category   string
		difficulty string
	}{
		{"配列操作", "easy"},
		{"文字列操作", "easy"},
		{"オブジェクト変換", "medium"},
		{"再帰", "medium"},
		{"高階関数", "easy"},
	}

	type result struct {
		idx        int
		category   string
		difficulty string
		ok         bool
		failReason string
		// 観測用の主要フィールド (成功時のみ埋まる)
		title       string
		numCases    int
		hasSolveExp bool
		allArrInput bool
	}

	results := make([]result, 0, len(cases))
	successes := 0

	for i, c := range cases {
		// 1 回ごとの timeout。Gemini Flash は thinking 込みで 60 秒あれば十分。
		ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)

		t.Logf("--- iteration %d: category=%s difficulty=%s ---", i+1, c.category, c.difficulty)
		draft, err := gen.Generate(ctx, c.category, c.difficulty)
		cancel()

		r := result{idx: i + 1, category: c.category, difficulty: c.difficulty}
		if err != nil {
			r.failReason = err.Error()
			results = append(results, r)
			t.Logf("FAIL: %v", err)
			continue
		}

		// 不変条件チェック: v2 で厳密化したルールが守られているか。
		allArr := true
		for _, tc := range draft.TestCases {
			if tc.Input == nil {
				allArr = false
				break
			}
		}
		hasSolve := strings.Contains(draft.ReferenceSolution, "export function solve")

		r.ok = true
		r.title = draft.Title
		r.numCases = len(draft.TestCases)
		r.hasSolveExp = hasSolve
		r.allArrInput = allArr
		results = append(results, r)
		successes++

		t.Logf("OK: title=%q test_cases=%d input配列=%v export-function-solve=%v cost=$%.6f tokens=in:%d/out:%d",
			draft.Title, len(draft.TestCases), allArr, hasSolve,
			draft.GeneratedBy.CostUSD, draft.GeneratedBy.InputTokens, draft.GeneratedBy.OutputTokens)

		if !hasSolve {
			t.Logf("  ⚠ reference_solution に 'export function solve' なし: %s", truncate(draft.ReferenceSolution, 200))
		}
	}

	// サマリ出力
	t.Log("===== smoke summary =====")
	for _, r := range results {
		if r.ok {
			t.Logf("  [%d] OK   cat=%s diff=%s title=%q cases=%d", r.idx, r.category, r.difficulty, r.title, r.numCases)
		} else {
			t.Logf("  [%d] FAIL cat=%s diff=%s reason=%s", r.idx, r.category, r.difficulty, truncate(r.failReason, 200))
		}
	}
	t.Logf("成功率: %d/%d", successes, len(cases))

	// 4/5 以上で pass。閾値の根拠:
	//   - LLM は確率的なので 100% を要求すると flake が頻発する
	//   - 一方 3/5 以下なら v2 のルール強化が効いていない兆候、PR を再考すべき
	const threshold = 4
	if successes < threshold {
		t.Fatalf("成功率が閾値未満: %d/%d (要 >= %d/%d)", successes, len(cases), threshold, len(cases))
	}

	// 全成功イテレーションで「input が配列」「export function solve」が守られているかも確認。
	// 1 件でも守られていなければ警告 (FAIL までは行かない、v3 で再強化検討)。
	violations := 0
	for _, r := range results {
		if !r.ok {
			continue
		}
		if !r.allArrInput {
			t.Logf("  ⚠ [%d] test_cases[i].input が配列でない要素あり", r.idx)
			violations++
		}
		if !r.hasSolveExp {
			t.Logf("  ⚠ [%d] reference_solution が export function solve 形でない", r.idx)
			violations++
		}
	}
	if violations > 0 {
		t.Logf("不変条件違反 %d 件。v3 で system_prompt をさらに強化する余地あり", violations)
	}

	// 観測値は CI ではなく手元で見るのが主用途なので、stdout の t.Log を
	// 目視で確認する想定。
}
