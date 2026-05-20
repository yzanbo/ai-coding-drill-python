// result.go: Vitest の JSON reporter 出力をパースする。
//
// Vitest を `vitest run --reporter=json` で起動すると、stdout に JSON 1 オブジェクト
// が出力される (Jest 互換構造)。主に使うフィールド:
//   - numTotalTests
//   - numPassedTests
//   - numFailedTests
//   - testResults[].testResults[]  (1 件 1 件の it() の結果)
//
// 失敗理由を full スタックトレースまで含めるとログが膨らむため、本 PR では
// failureMessages を最初の 200 文字に短縮して保存する。
package sandbox

import (
	"encoding/json"
	"fmt"
	"strings"
)

// vitestOutput: Vitest JSON reporter の最小スキーマ。
// 必要キーだけ持つ (success / startTime / endTime 等は読まない)。
type vitestOutput struct {
	NumTotalTests  int                 `json:"numTotalTests"`
	NumPassedTests int                 `json:"numPassedTests"`
	NumFailedTests int                 `json:"numFailedTests"`
	TestResults    []vitestSuiteResult `json:"testResults"`
}

type vitestSuiteResult struct {
	TestResults []vitestTestResult `json:"assertionResults"`
}

type vitestTestResult struct {
	// Status: "passed" / "failed" / "skipped" / "pending"。
	Status   string `json:"status"`
	FullName string `json:"fullName"`
	Title    string `json:"title"`
	// FailureMessages: スタックトレース含むエラー文字列の配列。
	FailureMessages []string `json:"failureMessages"`
}

// VitestSummary: orchestrator が judge / DB 書き込み判断に使う集計結果。
type VitestSummary struct {
	Total  int
	Passed int
	Failed int
	// Failures: 失敗した it() の {name, snippet} を最初の 5 件だけ保持。
	// 全件持つと judge に渡す JSON が肥大化する。
	Failures []FailedTest
}

// FailedTest: 失敗 it 1 件分の概要。
type FailedTest struct {
	Name    string
	Snippet string
}

// AllPassed: 1 件以上テストが走って全部 passed なら true。
func (s *VitestSummary) AllPassed() bool {
	return s.Total > 0 && s.Failed == 0 && s.Passed == s.Total
}

// ParseVitest: stdout 文字列を Vitest JSON として解釈し VitestSummary を返す。
//
// 失敗パターン:
//   - JSON 不正 / 空文字 -> error
//
// 注意: vitest が起動エラー (config 不正 / モジュール解決失敗) で死ぬと
// JSON が出ない or 部分的になる。その場合は stderr を見て判断する責務を
// 呼び出し側 (orchestrator) に委ねる (本関数は「JSON で得られた結果」のみ
// を扱う)。
func ParseVitest(stdout string) (*VitestSummary, error) {
	stdout = strings.TrimSpace(stdout)
	if stdout == "" {
		return nil, fmt.Errorf("sandbox: empty vitest stdout")
	}
	// Vitest は --reporter=json で JSON object 1 個を出す。
	// 末尾に他の警告行が混じる可能性があるため、最後の '{' から末尾 '}' までを抜き取る。
	jsonText := extractLastJSONObject(stdout)
	if jsonText == "" {
		return nil, fmt.Errorf("sandbox: no JSON object found in stdout")
	}
	var raw vitestOutput
	if err := json.Unmarshal([]byte(jsonText), &raw); err != nil {
		return nil, fmt.Errorf("sandbox: parse vitest JSON: %w", err)
	}
	s := &VitestSummary{
		Total:  raw.NumTotalTests,
		Passed: raw.NumPassedTests,
		Failed: raw.NumFailedTests,
	}
	// 失敗テスト概要を収集 (最大 5 件)。
	for _, suite := range raw.TestResults {
		for _, tr := range suite.TestResults {
			if tr.Status != "failed" {
				continue
			}
			snippet := ""
			if len(tr.FailureMessages) > 0 {
				snippet = truncateLog(tr.FailureMessages[0], 200) //nolint:mnd // 200 chars (UX 上の選択)
			}
			s.Failures = append(s.Failures, FailedTest{
				Name:    firstNonEmpty(tr.FullName, tr.Title),
				Snippet: snippet,
			})
			if len(s.Failures) >= 5 { //nolint:mnd // 上限 5 件 (UX 上の選択)
				return s, nil
			}
		}
	}
	return s, nil
}

// extractLastJSONObject: 文字列の末尾から { ... } の対応を取り出す。
// Vitest は JSON object をそのまま出すが、warning 行が前後に混じることがあるため。
func extractLastJSONObject(s string) string {
	end := strings.LastIndex(s, "}")
	if end < 0 {
		return ""
	}
	// ブレース対応を後ろから前へカウント。
	depth := 0
	for i := end; i >= 0; i-- {
		switch s[i] {
		case '}':
			depth++
		case '{':
			depth--
			if depth == 0 {
				return s[i : end+1]
			}
		}
	}
	return ""
}

// truncateLog: snippet の文字数制限。
func truncateLog(s string, n int) string {
	s = strings.TrimSpace(s)
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}

// firstNonEmpty: 引数のうち最初の non-empty な文字列を返す。
func firstNonEmpty(args ...string) string {
	for _, a := range args {
		if a != "" {
			return a
		}
	}
	return ""
}
