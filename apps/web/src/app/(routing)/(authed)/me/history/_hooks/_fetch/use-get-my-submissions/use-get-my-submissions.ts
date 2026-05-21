"use client";

// useGetMySubmissions: 自分の解答履歴一覧を取得するフック（ページネーション付き）。
//   - GET /api/submissions?page=N を叩いて { items, page, pageSize, totalPages } を返す
//   - 認証必須。401 は (authed) layout 側で処理されるので retry しない
//   - 同一問題への複数回解答は独立した行として並ぶ（grading.md §JSON 例 #get-submissions）
//   要件: docs/requirements/4-features/learning.md §学習履歴一覧画面
//        docs/requirements/4-features/grading.md §GET /api/submissions

import { useQuery } from "@tanstack/react-query";

import { listMySubmissionsApiSubmissionsGet } from "@/__generated__/api/sdk.gen";
import type { SubmissionsListResponse } from "@/__generated__/api/types.gen";
import { type ApiError, throwIfError } from "@/lib/api/api-error";
import { authAwareRetry } from "@/lib/api/query-retry";

const mySubmissionsQueryKey = (page: number) => ["me", "submissions", { page }] as const;

type UseGetMySubmissionsReturn = {
  submissions: SubmissionsListResponse | undefined;
  isLoading: boolean;
  error: ApiError | null;
};

export const useGetMySubmissions = (page: number): UseGetMySubmissionsReturn => {
  const query = useQuery<SubmissionsListResponse, ApiError>({
    queryKey: mySubmissionsQueryKey(page),
    queryFn: () =>
      throwIfError(
        listMySubmissionsApiSubmissionsGet({
          query: { page },
        }),
      ),
    retry: authAwareRetry,
  });

  return {
    submissions: query.data,
    isLoading: query.isLoading,
    error: query.error,
  };
};
