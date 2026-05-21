"use client";

// useRetryMyGeneration: failed の generation_request を新規 generation_request として複製。
//   - POST /api/me/generations/:id/retry を叩く（CSRF cookie 付き）
//   - 成功後は ["me", "generations"] を invalidate して履歴を再フェッチ
//     （新規 pending 行が一番上に追加される）
//   - 共有フック：生成履歴ページ + 生成中ページの両方から呼ばれる
//   要件: docs/requirements/4-features/problem-generation.md §履歴上のアクション

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { retryMyGenerationApiMeGenerationsRequestIdRetryPost } from "@/__generated__/api/sdk.gen";
import type { GenerationRequestRetryResponse } from "@/__generated__/api/types.gen";
import { type ApiError, throwIfError } from "@/lib/api/api-error";

type UseRetryMyGenerationReturn = {
  retry: (requestId: string) => Promise<GenerationRequestRetryResponse>;
  isPending: boolean;
  error: ApiError | null;
};

export const useRetryMyGeneration = (): UseRetryMyGenerationReturn => {
  const queryClient = useQueryClient();
  const mutation = useMutation<GenerationRequestRetryResponse, ApiError, string>({
    mutationFn: (requestId: string) =>
      throwIfError(
        retryMyGenerationApiMeGenerationsRequestIdRetryPost({
          path: { request_id: requestId },
        }),
      ),
    onSuccess: () => {
      // 履歴一覧を再フェッチ：新規 pending 行が一番上に出る + ポーリングが
      // refetchInterval ロジックで自動再開する。
      void queryClient.invalidateQueries({ queryKey: ["me", "generations"] });
    },
  });
  return {
    retry: (requestId: string) => mutation.mutateAsync(requestId),
    isPending: mutation.isPending,
    error: mutation.error,
  };
};
