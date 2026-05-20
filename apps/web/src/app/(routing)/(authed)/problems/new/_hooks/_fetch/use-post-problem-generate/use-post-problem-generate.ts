"use client";

// usePostProblemGenerate: 問題生成リクエスト送信フック。
//   - POST /problems/generate に { category, difficulty } を投げて 202 + requestId を取る
//   - 受け取った requestId をそのままページ側のリダイレクトに使う
//   - 通信エラーはグローバル ApiErrorProvider が toast で拾うため、本フックは error を返すだけ
//   要件: docs/requirements/4-features/problem-generation.md §API #post-problemsgenerate

import { useMutation } from "@tanstack/react-query";

import { requestProblemGenerationProblemsGeneratePost } from "@/__generated__/api/sdk.gen";
import type {
  ProblemGenerateAcceptedResponse,
  ProblemGenerateRequest,
} from "@/__generated__/api/types.gen";
import { type ApiError, throwIfError } from "@/lib/api/api-error";

type UsePostProblemGenerateOptions = {
  // onSuccess: 受付完了で requestId が確定した時に呼ばれる（ページ側でリダイレクトする想定）。
  onSuccess?: (data: ProblemGenerateAcceptedResponse) => void;
};

type UsePostProblemGenerateReturn = {
  requestGenerate: (body: ProblemGenerateRequest) => void;
  // isPending: 送信中フラグ（mutation 用。useGet* の isLoading とは別物）。
  isPending: boolean;
  // error: throwIfError が ApiError しか投げないので、型を明示して呼び出し側の narrowing コストを減らす。
  error: ApiError | null;
};

export const usePostProblemGenerate = (
  options: UsePostProblemGenerateOptions = {},
): UsePostProblemGenerateReturn => {
  const mutation = useMutation<ProblemGenerateAcceptedResponse, ApiError, ProblemGenerateRequest>({
    mutationFn: (body) => throwIfError(requestProblemGenerationProblemsGeneratePost({ body })),
    onSuccess: (data) => {
      options.onSuccess?.(data);
    },
  });

  return {
    requestGenerate: (body) => mutation.mutate(body),
    isPending: mutation.isPending,
    error: mutation.error,
  };
};
