// category-label: 問題カテゴリの DB 文字列 → 日本語ラベル変換ヘルパ。
//   - PROBLEM_CATEGORY_OPTIONS の label を引く（5 種類の許可値を網羅）
//   - 未知の値（将来 DB に新カテゴリが追加された場合）は raw 値をそのまま返す
//     のフォールバックを取る（落とすより未訳で表示する方が UX 影響が小さい）
//
//   要件: docs/requirements/4-features/learning.md §統計画面 / §弱点カテゴリ画面
//   （/me/stats / /me/weakness のレスポンスは MeCategoryStat.category: string
//    で返るが、UI では日本語ラベルで表示する）

import { PROBLEM_CATEGORY_OPTIONS } from "@/lib/constants/problem-categories";

export const formatCategoryLabel = (raw: string): string =>
  PROBLEM_CATEGORY_OPTIONS.find((o) => o.value === raw)?.label ?? raw;
