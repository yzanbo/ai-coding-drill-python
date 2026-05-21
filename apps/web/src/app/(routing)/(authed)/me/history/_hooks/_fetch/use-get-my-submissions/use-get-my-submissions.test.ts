// useGetMySubmissions のフックテスト。
//   要件: learning.md §学習履歴一覧画面 / grading.md §GET /api/submissions
//   - ?page=N を投げて 200 で {items,page,pageSize,totalPages} が返る
//   - 履歴ゼロは items=[] / totalPages=1
//   - 401 で error が確定する

import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { API_BASE, server } from "@/test/msw-server";
import { withQueryClient } from "@/test/render-with-query";

import { useGetMySubmissions } from "./use-get-my-submissions";

describe("useGetMySubmissions", () => {
  it("正常系: items + ページネーション情報が返る", async () => {
    server.use(
      http.get(`${API_BASE}/api/submissions`, ({ request }) => {
        const url = new URL(request.url);
        const page = Number(url.searchParams.get("page") ?? "1");
        return HttpResponse.json({
          items: [
            {
              id: "00000000-0000-0000-0000-000000000001",
              problemId: "00000000-0000-0000-0000-0000000000aa",
              problemTitle: "配列の合計",
              status: "graded",
              score: 3,
              totalCount: 3,
              gradedAt: "2026-05-21T00:00:00Z",
            },
          ],
          page,
          pageSize: 20,
          totalPages: 3,
        });
      }),
    );

    const { result } = renderHook(() => useGetMySubmissions(2), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.submissions?.items.length).toBe(1));
    expect(result.current.submissions?.page).toBe(2);
    expect(result.current.submissions?.totalPages).toBe(3);
  });

  it("正常系: 履歴ゼロは items=[] / totalPages=1", async () => {
    server.use(
      http.get(`${API_BASE}/api/submissions`, () =>
        HttpResponse.json({ items: [], page: 1, pageSize: 20, totalPages: 1 }),
      ),
    );

    const { result } = renderHook(() => useGetMySubmissions(1), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.submissions).toBeDefined());
    expect(result.current.submissions?.items).toEqual([]);
    expect(result.current.submissions?.totalPages).toBe(1);
  });

  it("異常系: 401 で error が確定する", async () => {
    server.use(
      http.get(`${API_BASE}/api/submissions`, () => new HttpResponse(null, { status: 401 })),
    );

    const { result } = renderHook(() => useGetMySubmissions(1), { wrapper: withQueryClient() });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.status).toBe(401);
  });
});
