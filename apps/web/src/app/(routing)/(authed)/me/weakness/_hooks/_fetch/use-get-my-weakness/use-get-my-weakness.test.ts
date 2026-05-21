// useGetMyWeakness のフックテスト。
//   要件: learning.md §GET /me/weakness / §受け入れ条件
//   - 履歴ゼロでも 200 + weakCategories=[] が返る
//   - 正常系で weakCategories が並んで返る
//   - 401 / 5xx で error に ApiError がセットされる

import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { API_BASE, server } from "@/test/msw-server";
import { withQueryClient } from "@/test/render-with-query";

import { useGetMyWeakness } from "./use-get-my-weakness";

describe("useGetMyWeakness", () => {
  it("正常系: 履歴ゼロは weakCategories が空", async () => {
    server.use(
      http.get(`${API_BASE}/api/me/weakness`, () => HttpResponse.json({ weakCategories: [] })),
    );

    const { result } = renderHook(() => useGetMyWeakness(), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.weakness).toBeDefined());
    expect(result.current.weakness?.weakCategories).toEqual([]);
  });

  it("正常系: 弱点カテゴリが並んで返る", async () => {
    server.use(
      http.get(`${API_BASE}/api/me/weakness`, () =>
        HttpResponse.json({
          weakCategories: [{ category: "recursion", attempts: 5, correct: 1, accuracy: 0.2 }],
        }),
      ),
    );

    const { result } = renderHook(() => useGetMyWeakness(), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.weakness?.weakCategories?.length).toBe(1));
    expect(result.current.weakness?.weakCategories?.[0].category).toBe("recursion");
    expect(result.current.weakness?.weakCategories?.[0].accuracy).toBeCloseTo(0.2);
  });

  it("異常系: 401 で error が確定する", async () => {
    server.use(
      http.get(`${API_BASE}/api/me/weakness`, () => new HttpResponse(null, { status: 401 })),
    );

    const { result } = renderHook(() => useGetMyWeakness(), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.status).toBe(401);
  });
});
