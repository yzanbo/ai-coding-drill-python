"use client";

// useCancelMyGeneration: pending の generation_request をキャンセルするフック。
//   - POST /api/me/generations/:id/cancel を叩く（CSRF cookie 付き、apiClient で自動同梱）
//   - 成功後は ["me", "generations"] を invalidate して履歴を再フェッチ
//   要件: docs/requirements/4-features/problem-generation.md §履歴上のアクション

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { cancelMyGenerationApiMeGenerationsRequestIdCancelPost } from "@/__generated__/api/sdk.gen";
import type { GenerationRequestCancelResponse } from "@/__generated__/api/types.gen";
import { type ApiError, throwIfError } from "@/lib/api/api-error";

type UseCancelMyGenerationReturn = {
  cancel: (requestId: string) => Promise<GenerationRequestCancelResponse>;
  isPending: boolean;
  error: ApiError | null;
};

export const useCancelMyGeneration = (): UseCancelMyGenerationReturn => {
  const queryClient = useQueryClient();
  const mutation = useMutation<GenerationRequestCancelResponse, ApiError, string>({
    mutationFn: (requestId: string) =>
      throwIfError(
        cancelMyGenerationApiMeGenerationsRequestIdCancelPost({
          path: { request_id: requestId },
        }),
      ),
    onSuccess: () => {
      // 履歴一覧を再フェッチして UI を最新化（status='canceled' が反映される）。
      void queryClient.invalidateQueries({ queryKey: ["me", "generations"] });
    },
  });
  return {
    cancel: (requestId: string) => mutation.mutateAsync(requestId),
    isPending: mutation.isPending,
    error: mutation.error,
  };
};
