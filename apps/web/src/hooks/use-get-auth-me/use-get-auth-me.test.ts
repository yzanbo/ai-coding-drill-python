// useGetAuthMe のフックテスト。
//   要件: authentication.md §1.4 GET /auth/me + §1.5 共通画面コンポーネント
//   - 200: user に displayName が入り isAuthenticated=true
//   - 401: isUnauthenticated=true / user=undefined / isAuthenticated=false
//   - 500: 一時的なネットワーク失敗扱い（user は undefined のまま）
import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { API_BASE, server } from "../../test/msw-server";
import { withQueryClient } from "../../test/render-with-query";

import { useGetAuthMe } from "./use-get-auth-me";

describe("useGetAuthMe", () => {
  it("正常系: 200 が返ると user と isAuthenticated が確定する", async () => {
    server.use(
      http.get(`${API_BASE}/auth/me`, () =>
        HttpResponse.json({
          id: "user-1",
          displayName: "yzanbo",
          email: "z@example.com",
        }),
      ),
    );

    const { result } = renderHook(() => useGetAuthMe(), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.isUnauthenticated).toBe(false);
    expect(result.current.user).toEqual({
      id: "user-1",
      displayName: "yzanbo",
      email: "z@example.com",
    });
  });

  it("異常系: 401 は未認証として確定（isUnauthenticated=true、user=undefined）", async () => {
    server.use(http.get(`${API_BASE}/auth/me`, () => new HttpResponse(null, { status: 401 })));

    const { result } = renderHook(() => useGetAuthMe(), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.isUnauthenticated).toBe(true));
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeUndefined();
  });

  it("異常系: 500 は未認証扱いにせず、user は undefined のまま", async () => {
    server.use(http.get(`${API_BASE}/auth/me`, () => new HttpResponse(null, { status: 500 })));

    const { result } = renderHook(() => useGetAuthMe(), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.isUnauthenticated).toBe(false);
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.user).toBeUndefined();
    expect(result.current.error).toBeDefined();
  });
});
