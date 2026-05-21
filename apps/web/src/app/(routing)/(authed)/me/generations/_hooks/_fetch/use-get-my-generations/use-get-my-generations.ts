"use client";

// useGetMyGenerations: 自分の生成リクエスト履歴一覧を取得するフック。
//   - GET /api/me/generations?page=N をポーリングで叩く
//   - 進行中（pending）の行があれば 1 秒間隔で再フェッチ、全件終端なら停止
//   - タブ非アクティブの間は停止（refetchIntervalInBackground: false）
//   - 401 は (authed) layout のガードが捌くので retry しない
//   要件: docs/requirements/4-features/problem-generation.md §生成履歴画面

import { useQuery } from "@tanstack/react-query";

import { listMyGenerationsApiMeGenerationsGet } from "@/__generated__/api/sdk.gen";
import type { ListMyGenerationsApiMeGenerationsGetResponse } from "@/__generated__/api/types.gen";
import { type ApiError, throwIfError } from "@/lib/api/api-error";
import { authAwareRetry } from "@/lib/api/query-retry";

// POLL_INTERVAL_MS: 進行中行がある時のポーリング間隔。
//   1 秒は LLM 生成（数十秒〜数分）に対して過剰だが、要件で「1 秒間隔」と決めたため
//   そのまま採用。終端後は止まる + タブ非アクティブで止まるので無駄リクエストは限定的。
const POLL_INTERVAL_MS = 1000;

const myGenerationsQueryKey = (page: number) => ["me", "generations", { page }] as const;

type UseGetMyGenerationsReturn = {
  generations: ListMyGenerationsApiMeGenerationsGetResponse | undefined;
  isLoading: boolean;
  error: ApiError | null;
};

export const useGetMyGenerations = (page: number): UseGetMyGenerationsReturn => {
  const query = useQuery<ListMyGenerationsApiMeGenerationsGetResponse, ApiError>({
    queryKey: myGenerationsQueryKey(page),
    queryFn: () =>
      throwIfError(
        listMyGenerationsApiMeGenerationsGet({
          query: { page },
        }),
      ),
    // refetchInterval: 進行中（pending）の行が 1 つでもあれば POLL_INTERVAL_MS、
    //   全件終端なら false（停止）。「進行中」の判定は status を見るだけで済む。
    refetchInterval: (q) => {
      const data = q.state.data;
      if (!data) return POLL_INTERVAL_MS; // 初回ロード中は polling 開始
      const hasInFlight = data.items.some((it) => it.status === "pending");
      return hasInFlight ? POLL_INTERVAL_MS : false;
    },
    // refetchIntervalInBackground: false がデフォルト動作だが明示しておく。
    //   タブ非アクティブの間は polling を止める（電池節約 + サーバ負荷軽減）。
    refetchIntervalInBackground: false,
    retry: authAwareRetry,
  });

  return {
    generations: query.data,
    isLoading: query.isLoading,
    error: query.error,
  };
};
