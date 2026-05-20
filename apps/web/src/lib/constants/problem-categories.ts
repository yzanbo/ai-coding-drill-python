// 問題カテゴリの日本語ラベル。
//   許可値（'string' / 'array' / ...）は OpenAPI 生成型 ProblemCategory が SSoT。
//   ここでは UI で並べる順序と表示文言だけを管理する。
//   要件: docs/requirements/4-features/problem-generation.md §バリデーション
//
// 全件網羅は型で機械強制：
//   - PROBLEM_CATEGORY_LABELS を Record<ProblemCategory, ...> で持つことで、
//     API 側に新カテゴリが増えたら TS が「キー不足」エラーで気付かせる
//   - 表示順は PROBLEM_CATEGORY_ORDER（satisfies readonly ProblemCategory[]）で固定し、
//     PROBLEM_CATEGORY_OPTIONS でラベルと結合する

import type { ProblemCategory } from "@/__generated__/api/types.gen";

type ProblemCategoryLabel = {
  // label: 画面に出す日本語名
  label: string;
  // description: ラジオカード下に出す補足（どんな問題が出るかのヒント）
  description: string;
};

const PROBLEM_CATEGORY_LABELS: Record<ProblemCategory, ProblemCategoryLabel> = {
  string: { label: "文字列", description: "split / replace / 正規表現などの基本操作" },
  array: { label: "配列", description: "map / filter / reduce などのコレクション操作" },
  recursion: { label: "再帰", description: "木構造・分割統治などの再帰アルゴリズム" },
  async: { label: "非同期", description: "Promise / async-await / 並行実行" },
  "type-puzzle": {
    label: "型パズル",
    description: "Conditional Types / Mapped Types など TS の型操作",
  },
};

// PROBLEM_CATEGORY_ORDER: 画面で並べる順序。
//   satisfies readonly ProblemCategory[] で値の妥当性は検査する。
//   全件網羅自体は PROBLEM_CATEGORY_LABELS の Record で担保しているので、
//   ここに足し忘れた値は単に末尾に出ないだけで実害は小さい。
const PROBLEM_CATEGORY_ORDER = [
  "string",
  "array",
  "recursion",
  "async",
  "type-puzzle",
] as const satisfies readonly ProblemCategory[];

export type ProblemCategoryOption = {
  value: ProblemCategory;
  label: string;
  description: string;
};

export const PROBLEM_CATEGORY_OPTIONS: readonly ProblemCategoryOption[] =
  PROBLEM_CATEGORY_ORDER.map((value) => ({ value, ...PROBLEM_CATEGORY_LABELS[value] }));
