"use client";

// ApiErrorProvider: API 呼び出しで発生したエラーを「トースト 1 か所」で通知する。
//   - useMutation のエラー: ほぼ全部トースト対象（保存失敗 / 削除失敗 / ログアウト失敗 等）
//   - useQuery のエラー: 一覧取得失敗 等を画面に出さず黙ると気付かれないため、ここで通知
//
//   個別フック側は `error` state を引き続き返す（フォームのインラインエラー用）。
//   トーストとインライン表示の二重表示は意図的: トーストは一時的、インラインは恒常的。
//   不要なら呼び出し側で meta: { silent: true } を付けて抑制する。
//
//   仕組み:
//     - QueryClient の MutationCache / QueryCache に subscribe して onError 相当の通知を拾う
//     - sonner の toast.error でメッセージを出す

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { toast } from "sonner";
import { ApiError } from "@/lib/api/api-error";
import { extractApiErrorMessage } from "@/lib/api/api-error-interceptor";

type ApiErrorProviderProps = {
  children: React.ReactNode;
};

// isSilent: meta.silent が true ならトーストしない（呼び出し側で抑止できる）。
const isSilent = (meta: unknown): boolean => {
  if (!meta || typeof meta !== "object") return false;
  return (meta as { silent?: boolean }).silent === true;
};

// pickStatusAndBody: useQuery / useMutation の error から status と body を取り出す。
//   ApiError（lib/api/api-error.ts）を主とし、それ以外の形（Response / 不明型）も拾う。
const pickStatusAndBody = (error: unknown): { status?: number; body: unknown } => {
  if (error instanceof ApiError) return { status: error.status, body: error.body };
  if (error instanceof Response) return { status: error.status, body: undefined };
  return { status: undefined, body: error };
};

export const ApiErrorProvider = ({ children }: ApiErrorProviderProps) => {
  const queryClient = useQueryClient();

  useEffect(() => {
    // mutation エラーは原則すべてトースト。
    const unsubMutation = queryClient.getMutationCache().subscribe((event) => {
      if (event.type !== "updated") return;
      const mutation = event.mutation;
      if (mutation?.state.status !== "error") return;
      if (isSilent(mutation.options.meta)) return;
      const { status, body } = pickStatusAndBody(mutation.state.error);
      toast.error(extractApiErrorMessage(status, body));
    });

    // query エラーは 401（未認証）を除いてトースト（401 は (authed) layout が拾う）。
    const unsubQuery = queryClient.getQueryCache().subscribe((event) => {
      if (event.type !== "updated") return;
      const query = event.query;
      if (query.state.status !== "error") return;
      if (isSilent(query.meta)) return;
      const { status, body } = pickStatusAndBody(query.state.error);
      if (status === 401) return;
      toast.error(extractApiErrorMessage(status, body));
    });

    return () => {
      unsubMutation();
      unsubQuery();
    };
  }, [queryClient]);

  return <>{children}</>;
};
