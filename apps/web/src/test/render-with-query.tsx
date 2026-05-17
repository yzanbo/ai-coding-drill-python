// テスト用の描画 / フック実行ヘルパ。
//   - TanStack Query の Provider でラップ（テストごとに新しい QueryClient を
//     作って状態が漏れないようにする）
//   - retry: false にして 401 等のエラー応答が即時に確定するように倒す
//     （プロダクトの retry: 1 を引き継ぐと waitFor のタイムアウト要因になる）
//   - configureApiClient() をテスト起動時に 1 回呼んで Hey API クライアントの
//     baseUrl / credentials / CSRF 注入を有効化する
//
// 使い方:
//   const { result } = renderHook(() => useGetAuthMe(), { wrapper: withQueryClient() });
//   render(<SiteHeader />, { wrapper: withQueryClient() });

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

// 注意: Hey API クライアントの初期化（configureApiClient + baseUrl 上書き）は
//   vitest.setup.ts で全テスト共通に行っているので、本ファイルでは扱わない。

export const createTestQueryClient = (): QueryClient =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        // retryDelay: 0 にしておく。フック側で `retry` を関数で上書きしている
        //   場合（例 useGetAuthMe）はそちらが優先されるため、デフォルトの
        //   exponential backoff（最大 30s）が走ってテストが waitFor で
        //   タイムアウトする事故を防ぐ。
        retryDelay: 0,
        staleTime: 0,
        gcTime: 0,
      },
      mutations: { retry: false, retryDelay: 0 },
    },
  });

export const withQueryClient = () => {
  const client = createTestQueryClient();
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
};
