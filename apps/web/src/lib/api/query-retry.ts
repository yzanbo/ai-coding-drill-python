// query-retry: TanStack Query の retry コールバック共通ヘルパ。
//   useQuery({ retry: authAwareRetry }) として渡し、認証エラーと一過性エラーを
//   1 つの方針で扱う：
//     - 401（未認証）: 即 error に倒す。(authed) layout 側のガードが /login に誘導する
//                      ため、ここで retry すると無駄なネットワーク往復が増えるだけ
//     - その他（5xx / ネットワーク断）: 1 回だけ retry。瞬断にだけ寛容にする
//
//   このプロジェクトの認証必須フックは全て同じ方針で書いていたため（PR #81
//   セルフレビュー §軽微 (3)）、4 箇所重複していたインライン定義を本ヘルパに集約する。

import { ApiError } from "./api-error";

export const authAwareRetry = (failureCount: number, error: unknown): boolean => {
  if (error instanceof ApiError && error.status === 401) return false;
  return failureCount < 1;
};
