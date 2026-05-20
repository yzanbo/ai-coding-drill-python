"use client";

// useGetProblemGenerationStatus: 生成リクエストのステータスをポーリング取得するフック。
//   - GET /problems/generate/:requestId を 1.5 秒間隔で叩く
//   - status が completed / failed になった時点で自動停止（refetchInterval を false に倒す）
//   - 取得結果は呼び出し側でハンドリング（completed → 問題ページへ遷移、failed → 再試行 UI）
//   要件: docs/requirements/4-features/problem-generation.md §生成ステータス画面

import { useQuery } from "@tanstack/react-query";

import { getProblemGenerationStatusProblemsGenerateRequestIdGet } from "@/__generated__/api/sdk.gen";
import type { ProblemGenerateStatusResponse } from "@/__generated__/api/types.gen";
import { type ApiError, throwIfError } from "@/lib/api/api-error";

// POLLING_INTERVAL_MS: ポーリング間隔。生成は数秒〜数十秒のオーダーなので
//   サーバ負荷と UX の体感反応速度のバランスで 1.5 秒に置く。
const POLLING_INTERVAL_MS = 1500;

const problemGenerationStatusQueryKey = (requestId: string) =>
  ["problems", "generate", requestId] as const;

type UseGetProblemGenerationStatusReturn = {
  status: ProblemGenerateStatusResponse | undefined;
  // isLoading: 初回フェッチ中。fetch 条件（requestId 確定）を満たすので初期値は true（frontend.md ルール）。
  isLoading: boolean;
  error: unknown;
};

export const useGetProblemGenerationStatus = (
  requestId: string,
): UseGetProblemGenerationStatusReturn => {
  const query = useQuery<ProblemGenerateStatusResponse, ApiError>({
    queryKey: problemGenerationStatusQueryKey(requestId),
    queryFn: () =>
      throwIfError(
        getProblemGenerationStatusProblemsGenerateRequestIdGet({ path: { request_id: requestId } }),
      ),
    // refetchInterval: 終端状態（completed / failed）に達したら false を返してポーリング停止。
    //   query.state.data から最新ステータスを参照する（クロージャに残った古い値で判断しない）。
    refetchInterval: (q) => {
      const current = q.state.data?.status;
      if (current === "completed" || current === "failed") return false;
      return POLLING_INTERVAL_MS;
    },
    // refetchOnWindowFocus: ポーリング中はタブ戻り時の余分なフェッチを抑止（POLLING_INTERVAL_MS で十分）。
    refetchOnWindowFocus: false,
  });

  return {
    status: query.data,
    isLoading: query.isLoading,
    error: query.error,
  };
};
