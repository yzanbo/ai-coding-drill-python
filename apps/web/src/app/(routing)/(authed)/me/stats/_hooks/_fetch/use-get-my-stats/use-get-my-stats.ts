"use client";

// useGetMyStats: 全期間の正答率 + カテゴリ別習熟度を取得するフック。
//   - GET /api/me/stats を 1 回叩いて結果を保持
//   - 認証必須エンドポイント。401 は (authed) layout の useGetAuthMe が拾うので
//     本フックでは retry せず即 error に倒す
//   - 履歴ゼロでも 200 で total=0 / byCategory=[] が返る（learning.md §受け入れ条件）
//   要件: docs/requirements/4-features/learning.md §統計画面

import { useQuery } from "@tanstack/react-query";

import { getMyStatsApiMeStatsGet } from "@/__generated__/api/sdk.gen";
import type { MeStatsResponse } from "@/__generated__/api/types.gen";
import { type ApiError, throwIfError } from "@/lib/api/api-error";
import { authAwareRetry } from "@/lib/api/query-retry";

const ME_STATS_QUERY_KEY = ["me", "stats"] as const;

type UseGetMyStatsReturn = {
  stats: MeStatsResponse | undefined;
  // isLoading: 初回フェッチ中。fetch 条件（認証済み）は常に満たすので初期値は true。
  isLoading: boolean;
  error: ApiError | null;
};

export const useGetMyStats = (): UseGetMyStatsReturn => {
  const query = useQuery<MeStatsResponse, ApiError>({
    queryKey: ME_STATS_QUERY_KEY,
    queryFn: () => throwIfError(getMyStatsApiMeStatsGet()),
    // retry: 401 は (authed) layout が捌くため即 error に倒し、それ以外は 1 回だけ retry。
    //   詳細は @/lib/api/query-retry.ts の authAwareRetry。
    retry: authAwareRetry,
  });

  return {
    stats: query.data,
    isLoading: query.isLoading,
    error: query.error,
  };
};
