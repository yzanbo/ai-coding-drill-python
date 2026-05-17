"use client";

// QueryClientProvider: TanStack Query の「Query キャッシュの入れ物」を React ツリー
//   全体に配る Provider。useQuery / useMutation はここからキャッシュを参照する。
//   useState で 1 度だけインスタンス化することで、StrictMode の二重実行や
//   コンポーネント再描画でキャッシュが捨てられないようにする。
//
// 同時に lib/api/api-client.ts の configureApiClient() を呼んで、Hey API クライアントの
//   credentials / CSRF / baseUrl を初期化する。
//   Provider の評価はブラウザ側で 1 度しか走らないため、初期化用フックとしても都合がよい。

import {
  QueryClient,
  QueryClientProvider as TanstackQueryClientProvider,
} from "@tanstack/react-query";
import { useState } from "react";

import { configureApiClient } from "@/lib/api/api-client";

type QueryClientProviderProps = {
  children: React.ReactNode;
};

export const QueryClientProvider = ({ children }: QueryClientProviderProps) => {
  const [client] = useState(() => {
    configureApiClient();
    return new QueryClient({
      defaultOptions: {
        queries: {
          // staleTime: データを「新鮮」とみなす時間。短すぎると再フェッチが増える。
          //   1 分: 認証状態のような UI 同期には十分、長すぎない。
          staleTime: 60_000,
          // refetchOnWindowFocus: タブを切り替えて戻ってきた時の自動再取得。
          //   セッション切れに気付きたいので有効化。
          refetchOnWindowFocus: true,
          // retry: 401 / 4xx は再試行しない方が UX が良い（リダイレクトされるため）。
          retry: 1,
        },
        mutations: {
          retry: 0,
        },
      },
    });
  });

  return <TanstackQueryClientProvider client={client}>{children}</TanstackQueryClientProvider>;
};
