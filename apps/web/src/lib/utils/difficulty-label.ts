// difficulty-label: 問題難易度の DB 文字列 → 日本語ラベル変換ヘルパ。
//   - PROBLEM_DIFFICULTY_OPTIONS の label を引く（easy / medium / hard を網羅）
//   - 未知の値（将来 DB に新難易度が追加された場合）は raw 値をそのまま返す
//     フォールバック（落とすより未訳で表示する方が UX 影響が小さい）
//
//   category-label.ts と同じ思想・同じ形（揃えることで読み手の認知負荷を下げる）。
//   生成履歴 / 統計 / 弱点画面など、UI で難易度を出す全ての場所はこのヘルパ経由
//   で表示する（raw "easy" 等の生 string を画面に出さない）。

import { PROBLEM_DIFFICULTY_OPTIONS } from "@/lib/constants/problem-difficulties";

export const formatDifficultyLabel = (raw: string): string =>
  PROBLEM_DIFFICULTY_OPTIONS.find((o) => o.value === raw)?.label ?? raw;
