"use client";

// usePostAuthLogout: ログアウト用フック。
//   - POST /auth/logout を叩いて Redis セッション破棄 + Cookie クリア
//   - 成功時に /auth/me のキャッシュを無効化し、未認証状態に戻す
//   - 成功時の遷移先は呼び出し側が決める（ヘッダーは "/" に router.push する想定）
//   呼び出し側が `onSuccess` を渡せるようにオプションで受け取る。

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { logoutAuthLogoutPost } from "@/__generated__/api/sdk.gen";
import { AUTH_ME_QUERY_KEY } from "@/hooks/use-get-auth-me/use-get-auth-me";
import { throwIfError } from "@/lib/api/api-error";

type UsePostAuthLogoutOptions = {
  onSuccess?: () => void;
};

type UsePostAuthLogoutReturn = {
  logout: () => void;
  // isPending: API 通信中フラグ（mutation 専用の命名、useGet* の isLoading とは別物）。
  isPending: boolean;
  error: unknown;
};

export const usePostAuthLogout = (
  options: UsePostAuthLogoutOptions = {},
): UsePostAuthLogoutReturn => {
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => throwIfError(logoutAuthLogoutPost()),
    // onSettled: 成功・失敗どちらの後でも /auth/me を必ず再評価する。
    //   セッションが既に切れているとサーバ側で 401 になる（CSRF middleware が
    //   sid を見つけられない）が、UI 上は「ログアウト後の状態」を反映したい。
    //   /auth/me が 401 を返せば未認証として SiteHeader / (authed) layout が
    //   切り替わる。逆に成功ケースでもキャッシュをクリアして同じ経路に乗せる。
    onSettled: async (_data, error) => {
      await queryClient.invalidateQueries({ queryKey: AUTH_ME_QUERY_KEY });
      if (!error) options.onSuccess?.();
    },
  });

  return {
    logout: () => mutation.mutate(),
    isPending: mutation.isPending,
    error: mutation.error,
  };
};
