// test_template.go: ProblemDraft (生成された問題) から Vitest 用テストファイルを
// 組み立てる。
//
// 出力 2 ファイル:
//   - solution.ts      : LLM が返した reference_solution (export function solve(...))
//   - solution.spec.ts : 自動生成のテスト harness。it.each で test_cases を回す
//
// 設計判断:
//   - test_cases は JSON でそのまま埋め込む (Vitest 内で展開)。これにより
//     文字列エスケープを 1 箇所に閉じる
//   - Vitest 設定ファイル (vitest.config.ts) は生成しない: グローバル vitest
//     のデフォルトで *.spec.ts を自動拾いし JSON reporter を CLI で指定する
package grading

import (
	"encoding/json"
	"fmt"
)

// SolutionFileName: reference_solution を書き出すファイル名。
const SolutionFileName = "solution.ts"

// SpecFileName: 自動生成テスト harness のファイル名 (Vitest が *.spec.ts を拾う)。
const SpecFileName = "solution.spec.ts"

// buildSpecFile: ProblemDraft の test_cases から solution.spec.ts 本文を組み立てる。
//
// 注意点:
//   - solve は可変長引数で呼ぶため、test_cases[i].input は配列を spread する
//     (= input: [1, 2] なら solve(1, 2))
//   - expected は toEqual で深い等価チェック (オブジェクト / 配列対応)
//
// 失敗パターン: test_cases を JSON にできない (any のシリアライズ失敗)。
// LLM 応答に NaN / 関数等の非 JSON 値が混ざった場合に該当する。
func buildSpecFile(draft *ProblemDraft) (string, error) {
	cases, err := json.Marshal(draft.TestCases)
	if err != nil {
		return "", fmt.Errorf("grading: marshal test cases: %w", err)
	}
	const tmpl = `import { describe, it, expect } from "vitest";
import { solve } from "./solution.ts";

// 本ファイルは Worker が自動生成 (internal/grading/test_template.go)。
// LLM 出力の test_cases を JSON でそのまま埋め込んでいる。
const cases = %s as Array<{ input: unknown[]; expected: unknown }>;

describe("solve", () => {
  it.each(cases)("case %%#", ({ input, expected }) => {
    // input は呼び出し引数の配列。spread で solve に渡す。
    // any cast は LLM 出力の型不定 (number / string / 任意 object) を許容するため。
    const actual = (solve as (...args: unknown[]) => unknown)(...(input as unknown[]));
    expect(actual).toEqual(expected);
  });
});
`
	return fmt.Sprintf(tmpl, string(cases)), nil
}
