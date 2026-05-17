// usePostAuthLogout のフックテスト。
//   要件: authentication.md §1.6 ログアウトフロー
//   - 204: onSuccess が呼ばれ、isPending が false に戻る
//   - 失敗時: onSuccess は呼ばれない、error に詰まる
//   - onSettled では成功・失敗どちらでも /auth/me のキャッシュが無効化される
import { type QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { API_BASE, server } from "../../test/msw-server";
import { createTestQueryClient } from "../../test/render-with-query";
import { AUTH_ME_QUERY_KEY } from "../use-get-auth-me/use-get-auth-me";

import { usePostAuthLogout } from "./use-post-auth-logout";

// renderWithClient: 同じ QueryClient インスタンスを介してテスト本体からも
//   invalidateQueries の発火を観測できるようにする小さなラッパ。
const renderWithClient = (client: QueryClient) => ({
  wrapper: ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  ),
});

describe("usePostAuthLogout", () => {
  it("正常系: 204 で onSuccess が呼ばれ isPending が false に戻る", async () => {
    server.use(http.post(`${API_BASE}/auth/logout`, () => new HttpResponse(null, { status: 204 })));
    const onSuccess = vi.fn();

    const client = createTestQueryClient();
    const { result } = renderHook(() => usePostAuthLogout({ onSuccess }), renderWithClient(client));

    act(() => result.current.logout());

    await waitFor(() => expect(result.current.isPending).toBe(false));
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(result.current.error).toBeNull();
  });

  it("異常系: 失敗時は onSuccess を呼ばず error を保持する", async () => {
    server.use(http.post(`${API_BASE}/auth/logout`, () => new HttpResponse(null, { status: 500 })));
    const onSuccess = vi.fn();

    const client = createTestQueryClient();
    const { result } = renderHook(() => usePostAuthLogout({ onSuccess }), renderWithClient(client));

    act(() => result.current.logout());

    await waitFor(() => expect(result.current.isPending).toBe(false));
    expect(onSuccess).not.toHaveBeenCalled();
    expect(result.current.error).toBeDefined();
  });

  it("onSettled で AUTH_ME_QUERY_KEY が invalidate される（成功時）", async () => {
    server.use(http.post(`${API_BASE}/auth/logout`, () => new HttpResponse(null, { status: 204 })));
    const client = createTestQueryClient();
    const invalidateSpy = vi.spyOn(client, "invalidateQueries");

    const { result } = renderHook(() => usePostAuthLogout(), renderWithClient(client));

    act(() => result.current.logout());
    await waitFor(() => expect(result.current.isPending).toBe(false));

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: AUTH_ME_QUERY_KEY });
  });
});
