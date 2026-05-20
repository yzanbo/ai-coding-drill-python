"use client";

// useGetSubmission: 採点結果をポーリング取得するフック（R1-5）。
//   - GET /api/submissions/:id を 1.5 秒間隔で叩く
//   - status が graded / failed に達した時点で自動停止
//   - submissionId が無ければ enabled=false でリクエストしない（送信前の状態）
//
// 要件:
//   - docs/requirements/4-features/grading.md §採点結果表示
//   - docs/requirements/4-features/grading.md §JSON 例 #get-submissionsid

import { useQuery } from "@tanstack/react-query";

import { getSubmissionApiSubmissionsSubmissionIdGet } from "@/__generated__/api/sdk.gen";
import type { SubmissionStatusResponse } from "@/__generated__/api/types.gen";
import { type ApiError, throwIfError } from "@/lib/api/api-error";

// POLLING_INTERVAL_MS: ポーリング間隔。要件「1〜2 秒間隔」の中間で 1.5 秒に置く。
//   採点は通常数秒で終わるが、Worker キューイング次第で遅延することもある。
const POLLING_INTERVAL_MS = 1500;

const submissionQueryKey = (submissionId: string) => ["submissions", submissionId] as const;

type UseGetSubmissionReturn = {
  submission: SubmissionStatusResponse | undefined;
  // isLoading: 初回フェッチ中。enabled=true で fetch 実行条件を満たすので
  //   submissionId 確定時の初期値は true（frontend-hooks.md ルール）。
  isLoading: boolean;
  // isFetching: 再フェッチ中（ポーリング中も含む）。スピナー継続表示に使う。
  isFetching: boolean;
  // error: useQuery が ApiError 限定で型付け済。404 / 401 を呼び出し側で
  //   分岐できるよう明示型を残す。
  error: ApiError | null;
};

export const useGetSubmission = (submissionId: string | null): UseGetSubmissionReturn => {
  // submissionId が null（解答未送信）の間は呼ばない。送信後にセットされて
  // 自動で初回フェッチ → ポーリング開始する流れ。
  const enabled = submissionId !== null;

  const query = useQuery<SubmissionStatusResponse, ApiError>({
    // submissionId が null の時は不正な queryKey を作らないため空文字を入れる
    //   （enabled=false なので実 fetch は発生しない）。
    queryKey: submissionQueryKey(submissionId ?? ""),
    queryFn: () =>
      throwIfError(
        getSubmissionApiSubmissionsSubmissionIdGet({
          // 末尾の `?? ""` は型安全のための非到達分岐（enabled=false で呼ばれない）。
          path: { submission_id: submissionId ?? "" },
        }),
      ),
    enabled,
    // retry: ポーリングが「失敗したら次の周期で再試行」を内包するため
    //   1 リクエスト内の retry は不要。即 error に倒して refetchInterval を停める
    //   （useGetProblemGenerationStatus と同方針）。
    retry: 0,
    // refetchInterval: pending の間だけ 1.5s 周期で再取得。
    //   graded / failed に達したら false にしてポーリング停止。
    //   エラー時も停止（裏で 5xx を叩き続けて負荷とログを汚さないため）。
    refetchInterval: (q) => {
      const current = q.state.data?.status;
      if (current === "graded" || current === "failed") return false;
      if (q.state.error) return false;
      return POLLING_INTERVAL_MS;
    },
    // refetchOnWindowFocus: タブ復帰時の余分なフェッチを抑止
    //   （POLLING_INTERVAL_MS で十分カバーする）。
    refetchOnWindowFocus: false,
  });

  return {
    submission: query.data,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: query.error,
  };
};
