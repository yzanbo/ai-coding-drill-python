// useGetMyStats のフックテスト。
//   要件: learning.md §GET /me/stats / §受け入れ条件
//   - 履歴ゼロでも 200 + 空集計が返って stats が埋まる
//   - 正常系で byCategory が返る
//   - 401 / 5xx で error に ApiError がセットされる

import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { API_BASE, server } from "@/test/msw-server";
import { withQueryClient } from "@/test/render-with-query";

import { useGetMyStats } from "./use-get-my-stats";

describe("useGetMyStats", () => {
  it("正常系: 履歴ゼロでも 200 で空集計が返る", async () => {
    server.use(
      http.get(`${API_BASE}/api/me/stats`, () =>
        HttpResponse.json({ total: 0, correct: 0, accuracy: 0.0, byCategory: [] }),
      ),
    );

    const { result } = renderHook(() => useGetMyStats(), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.stats).toBeDefined());
    expect(result.current.stats?.total).toBe(0);
    expect(result.current.stats?.accuracy).toBe(0.0);
    expect(result.current.stats?.byCategory).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it("正常系: byCategory が含まれて取得できる", async () => {
    server.use(
      http.get(`${API_BASE}/api/me/stats`, () =>
        HttpResponse.json({
          total: 15,
          correct: 9,
          accuracy: 0.6,
          byCategory: [
            { category: "array", attempts: 10, correct: 8, accuracy: 0.8 },
            { category: "recursion", attempts: 5, correct: 1, accuracy: 0.2 },
          ],
        }),
      ),
    );

    const { result } = renderHook(() => useGetMyStats(), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.stats?.total).toBe(15));
    expect(result.current.stats?.byCategory).toHaveLength(2);
    expect(result.current.stats?.byCategory?.[0].category).toBe("array");
  });

  it("異常系: 401 で error が確定する（認証切れ）", async () => {
    server.use(http.get(`${API_BASE}/api/me/stats`, () => new HttpResponse(null, { status: 401 })));

    const { result } = renderHook(() => useGetMyStats(), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.status).toBe(401);
    expect(result.current.stats).toBeUndefined();
  });

  it("異常系: 5xx で error が確定する", async () => {
    server.use(http.get(`${API_BASE}/api/me/stats`, () => new HttpResponse(null, { status: 500 })));

    const { result } = renderHook(() => useGetMyStats(), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.status).toBe(500);
  });
});
