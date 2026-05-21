// AttemptErrorList の型を生成物から再 export する。
//   FailureReasonTag は他箇所でも import されるので、ここで集約しておくと
//   将来「FE 全体で使う失敗理由 enum」の取り出し口が 1 つになる。

import type { AttemptError, GenerationRequestSummary } from "@/__generated__/api/types.gen";

export type { AttemptError };

// FailureReasonTag: API レスポンスから NonNullable で導出（Hey API が Literal を
//   top-level 型として export しないため、フィールド型から逆算する）。
//   page.tsx の FAILURE_MESSAGES とも整合するので、同じ取り出し方を維持する。
export type FailureReasonTag = NonNullable<GenerationRequestSummary["failureReason"]>;
