// 問題難易度の日本語ラベル。
//   許可値（'easy' / 'medium' / 'hard'）は OpenAPI 生成型 ProblemDifficulty が SSoT。
//   要件: docs/requirements/4-features/problem-generation.md §バリデーション
//
// 全件網羅は型で機械強制（PROBLEM_DIFFICULTY_LABELS の Record<ProblemDifficulty, ...>）。
//   詳細は問題カテゴリ側 (./problem-categories.ts) のコメントと同じ整理。

import type { ProblemDifficulty } from "@/__generated__/api/types.gen";

type ProblemDifficultyLabel = {
  label: string;
  description: string;
};

const PROBLEM_DIFFICULTY_LABELS: Record<ProblemDifficulty, ProblemDifficultyLabel> = {
  easy: { label: "やさしい", description: "入門〜基礎レベル" },
  medium: { label: "ふつう", description: "実務でよく出る応用レベル" },
  hard: { label: "むずかしい", description: "考え込みが必要な応用問題" },
};

const PROBLEM_DIFFICULTY_ORDER = [
  "easy",
  "medium",
  "hard",
] as const satisfies readonly ProblemDifficulty[];

export type ProblemDifficultyOption = {
  value: ProblemDifficulty;
  label: string;
  description: string;
};

export const PROBLEM_DIFFICULTY_OPTIONS: readonly ProblemDifficultyOption[] =
  PROBLEM_DIFFICULTY_ORDER.map((value) => ({ value, ...PROBLEM_DIFFICULTY_LABELS[value] }));
