"use client";

// usePostSubmission: 解答送信 mutation フック（R1-4）。
//   - POST /api/submissions に { problemId, code } を投げて 202 + submissionId を取る
//   - 認証必須（ゲスト経路は呼ぶ前に AnswerWorkspace 側で /login にリダイレクトする）
//   - 採点結果ポーリングは R1-5 で別フックを足す
//
// 関わる要件：
//   - docs/requirements/4-features/grading.md §API #post-submissions
//   - docs/requirements/4-features/problem-display-and-answer.md §「実行」ボタン

import { useMutation } from "@tanstack/react-query";

import { submitAnswerApiSubmissionsPost } from "@/__generated__/api/sdk.gen";
import type {
  SubmissionAcceptedResponse,
  SubmissionCreateRequest,
} from "@/__generated__/api/types.gen";
import { type ApiError, throwIfError } from "@/lib/api/api-error";

type UsePostSubmissionOptions = {
  // onSuccess: submissionId が確定した時に呼ばれる
  //   （R1-5 でポーリング開始トリガーに使う想定）。
  onSuccess?: (data: SubmissionAcceptedResponse) => void;
};

type UsePostSubmissionReturn = {
  submitAnswer: (body: SubmissionCreateRequest) => void;
  isPending: boolean;
  error: ApiError | null;
  data: SubmissionAcceptedResponse | undefined;
};

export const usePostSubmission = (
  options: UsePostSubmissionOptions = {},
): UsePostSubmissionReturn => {
  const mutation = useMutation<SubmissionAcceptedResponse, ApiError, SubmissionCreateRequest>({
    mutationFn: (body) => throwIfError(submitAnswerApiSubmissionsPost({ body })),
    onSuccess: (data) => {
      options.onSuccess?.(data);
    },
  });

  return {
    submitAnswer: (body) => mutation.mutate(body),
    isPending: mutation.isPending,
    error: mutation.error,
    data: mutation.data,
  };
};
