"use client";

// useGetProblemGenerationStatus: 生成リクエストのステータスをポーリング取得するフック。
//   - GET /api/problems/generate/:requestId を 1.5 秒間隔で叩く
//   - status が completed / failed になった時点で自動停止（refetchInterval を false に倒す）
//   - 取得結果は呼び出し側でハンドリング（completed → 問題ページへ遷移、failed → 再試行 UI）
//   要件: docs/requirements/4-features/problem-generation.md §生成ステータス画面

import { useQuery } from "@tanstack/react-query";

import { getProblemGenerationStatusApiProblemsGenerateRequestIdGet } from "@/__generated__/api/sdk.gen";
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
  // isFetching: 再フェッチ中（refetch / ポーリング）を含む取得中フラグ。
  //   「再読み込み」ボタン押下後の押下感維持に使う。
  isFetching: boolean;
  // error: useQuery が ApiError 限定で型付けされているためそのまま伝播する。
  //   呼び出し側で status 等を見て分岐できるよう unknown でなく明示型を返す。
  error: ApiError | null;
  // refetch: 失敗後にユーザー操作で再取得を起動するための明示 API。
  //   ポーリングが停止した状態でも、これを呼ぶと query が再走し成功すれば
  //   refetchInterval が再開する。
  refetch: () => void;
};

export const useGetProblemGenerationStatus = (
  requestId: string,
): UseGetProblemGenerationStatusReturn => {
  const query = useQuery<ProblemGenerateStatusResponse, ApiError>({
    queryKey: problemGenerationStatusQueryKey(requestId),
    queryFn: () =>
      throwIfError(
        getProblemGenerationStatusApiProblemsGenerateRequestIdGet({
          path: { request_id: requestId },
        }),
      ),
    // retry: 5xx 時に既定 1 回リトライが走るとポーリング停止判定が遅れ、
    //   裏で 1.5 秒ごとに失敗 GET を叩き続けるリスクが残る。
    //   ポーリングという仕組み自体が「失敗したら次の周期で再試行」を内包しているため、
    //   1 回のリクエストでの retry は不要。即 error に倒して refetchInterval を停める。
    retry: 0,
    // refetchInterval: 以下のいずれかでポーリングを停止する。
    //   - データが終端状態（completed / failed）に達した
    //   - エラーが確定：裏で 1.5s ごとに 5xx を叩き続けて
    //     負荷とログを汚さないように止める。再開はユーザー操作（refetch）で行う。
    //   query.state から最新値を参照する（クロージャに残った古い値で判断しない）。
    refetchInterval: (q) => {
      const current = q.state.data?.status;
      if (current === "completed" || current === "failed") return false;
      if (q.state.error) return false;
      return POLLING_INTERVAL_MS;
    },
    // refetchOnWindowFocus: ポーリング中はタブ戻り時の余分なフェッチを抑止（POLLING_INTERVAL_MS で十分）。
    refetchOnWindowFocus: false,
  });

  return {
    status: query.data,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    error: query.error,
    refetch: () => {
      // void で握り潰す（戻り値の Promise は呼び出し側で必要ないため）。
      void query.refetch();
    },
  };
};
