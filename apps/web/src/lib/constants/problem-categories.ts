// 問題カテゴリの日本語ラベル。
//   許可値（'string' / 'array' / ...）は OpenAPI 生成型 ProblemCategory が SSoT。
//   ここでは UI で並べる順序と表示文言だけを管理する。
//   要件: docs/requirements/4-features/problem-generation.md §バリデーション

import type { ProblemCategory } from "@/__generated__/api/types.gen";

type ProblemCategoryOption = {
  value: ProblemCategory;
  // label: 画面に出す日本語名
  label: string;
  // description: ラジオカード下に出す補足（どんな問題が出るかのヒント）
  description: string;
};

export const PROBLEM_CATEGORY_OPTIONS: readonly ProblemCategoryOption[] = [
  { value: "string", label: "文字列", description: "split / replace / 正規表現などの基本操作" },
  { value: "array", label: "配列", description: "map / filter / reduce などのコレクション操作" },
  { value: "recursion", label: "再帰", description: "木構造・分割統治などの再帰アルゴリズム" },
  { value: "async", label: "非同期", description: "Promise / async-await / 並行実行" },
  {
    value: "type-puzzle",
    label: "型パズル",
    description: "Conditional Types / Mapped Types など TS の型操作",
  },
] as const;
