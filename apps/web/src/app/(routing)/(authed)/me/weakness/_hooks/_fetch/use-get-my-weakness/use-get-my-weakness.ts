"use client";

// useGetMyWeakness: 弱点カテゴリ Top N を取得するフック。
//   - GET /api/me/weakness を 1 回叩いて結果を保持
//   - 認証必須。401 は (authed) layout 側で処理されるので retry しない
//   - 履歴ゼロ / 候補なしでも 200 で weakCategories=[] が返る
//   要件: docs/requirements/4-features/learning.md §弱点カテゴリ画面

import { useQuery } from "@tanstack/react-query";

import { getMyWeaknessApiMeWeaknessGet } from "@/__generated__/api/sdk.gen";
import type { MeWeaknessResponse } from "@/__generated__/api/types.gen";
import { type ApiError, throwIfError } from "@/lib/api/api-error";
import { authAwareRetry } from "@/lib/api/query-retry";

const ME_WEAKNESS_QUERY_KEY = ["me", "weakness"] as const;

type UseGetMyWeaknessReturn = {
  weakness: MeWeaknessResponse | undefined;
  isLoading: boolean;
  error: ApiError | null;
};

export const useGetMyWeakness = (): UseGetMyWeaknessReturn => {
  const query = useQuery<MeWeaknessResponse, ApiError>({
    queryKey: ME_WEAKNESS_QUERY_KEY,
    queryFn: () => throwIfError(getMyWeaknessApiMeWeaknessGet()),
    retry: authAwareRetry,
  });

  return {
    weakness: query.data,
    isLoading: query.isLoading,
    error: query.error,
  };
};
