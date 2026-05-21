"use client";

// useGetAuthMe: ログイン中ユーザーの情報を取得するフック。
//   - 未認証なら API が 401 を返す → 本フックは isUnauthenticated=true で抜ける（throw しない）
//   - 認証済みなら user に { id, displayName, email } が入る
//   ログアウト後など再フェッチさせたい時は useQueryClient().invalidateQueries({ queryKey: AUTH_ME_QUERY_KEY })
//   を呼ぶ。

import { useQuery } from "@tanstack/react-query";

import { getMeAuthMeGet } from "@/__generated__/api/sdk.gen";
import type { UserResponse } from "@/__generated__/api/types.gen";
import { ApiError, throwIfError } from "@/lib/api/api-error";
import { authAwareRetry } from "@/lib/api/query-retry";

export const AUTH_ME_QUERY_KEY = ["auth", "me"] as const;

type UseGetAuthMeReturn = {
  user: UserResponse | undefined;
  // isLoading: 初回フェッチ中。fetch 条件は常に満たすので初期値は true（frontend.md ルール）。
  isLoading: boolean;
  isAuthenticated: boolean;
  // isUnauthenticated: 401 を受け取った確定状態（fetch 中は false）。
  isUnauthenticated: boolean;
  error: unknown;
};

export const useGetAuthMe = (): UseGetAuthMeReturn => {
  const query = useQuery<UserResponse, ApiError>({
    queryKey: AUTH_ME_QUERY_KEY,
    queryFn: () => throwIfError(getMeAuthMeGet()),
    // 401 を「未認証」として確定させる（retry すると無駄なリクエストになる）。
    retry: authAwareRetry,
    // グローバル toast から除外（未認証は (authed) layout のリダイレクトで扱う）。
    meta: { silent: true },
  });

  const isUnauthenticated = query.error instanceof ApiError && query.error.status === 401;

  // 500 / ネットワーク断（status undefined）の時は isUnauthenticated=false のまま。
  //   この場合 query.data は前回成功値が残るので isAuthenticated は維持される
  //   （UX: 一時的な通信失敗で勝手にログアウト相当に倒さない）。再評価は次の
  //   window focus / staleTime 経過 / invalidateQueries で行う。
  return {
    // user: 401 が返った後は古いユーザー情報を返さない（TanStack Query は既定で
    //   error 時に前回 data を保持するため、ここで明示的に握り潰す）。
    user: isUnauthenticated ? undefined : query.data,
    isLoading: query.isLoading,
    // isAuthenticated: 401 を受けたら強制的に false（再ログイン誘導のため）。
    isAuthenticated: !!query.data && !isUnauthenticated,
    isUnauthenticated,
    error: query.error,
  };
};
