// 問題難易度の日本語ラベル。
//   許可値（'easy' / 'medium' / 'hard'）は OpenAPI 生成型 ProblemDifficulty が SSoT。
//   要件: docs/requirements/4-features/problem-generation.md §バリデーション

import type { ProblemDifficulty } from "@/__generated__/api/types.gen";

type ProblemDifficultyOption = {
  value: ProblemDifficulty;
  label: string;
  description: string;
};

export const PROBLEM_DIFFICULTY_OPTIONS: readonly ProblemDifficultyOption[] = [
  { value: "easy", label: "やさしい", description: "入門〜基礎レベル" },
  { value: "medium", label: "ふつう", description: "実務でよく出る応用レベル" },
  { value: "hard", label: "むずかしい", description: "考え込みが必要な応用問題" },
] as const;
