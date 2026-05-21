// useGetMyGenerations のフックテスト。
//   要件: problem-generation.md §生成履歴画面 / §ポーリング
//   - ?page=N を投げて 200 で {items,page,pageSize,totalPages} が返る
//   - 履歴ゼロは items=[] / totalPages=0
//   - 401 で error が確定する
//   注: refetchInterval / refetchIntervalInBackground の動的判定は実装側の責務で、
//        単体テストでは初回レスポンスの形を pin するに留める（タイマー駆動の検証は
//        E2E で「画面に新規行が出る」を観測する方が信頼度が高い）

import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { API_BASE, server } from "@/test/msw-server";
import { withQueryClient } from "@/test/render-with-query";

import { useGetMyGenerations } from "./use-get-my-generations";

describe("useGetMyGenerations", () => {
  it("正常系: items + ページネーション情報が返る", async () => {
    server.use(
      http.get(`${API_BASE}/api/me/generations`, ({ request }) => {
        const url = new URL(request.url);
        const page = Number(url.searchParams.get("page") ?? "1");
        return HttpResponse.json({
          items: [
            {
              id: "00000000-0000-0000-0000-000000000001",
              category: "array",
              difficulty: "easy",
              status: "completed",
              producedProblemId: "00000000-0000-0000-0000-0000000000aa",
              promptVersion: "v1",
              retryOf: null,
              retryCount: 0,
              createdAt: "2026-05-21T00:00:00Z",
              completedAt: "2026-05-21T00:01:30Z",
            },
          ],
          page,
          pageSize: 20,
          totalPages: 2,
        });
      }),
    );

    const { result } = renderHook(() => useGetMyGenerations(2), {
      wrapper: withQueryClient(),
    });

    await waitFor(() => expect(result.current.generations?.items.length).toBe(1));
    expect(result.current.generations?.page).toBe(2);
    expect(result.current.generations?.totalPages).toBe(2);
  });

  it("正常系: 履歴ゼロは items=[] / totalPages=0", async () => {
    server.use(
      http.get(`${API_BASE}/api/me/generations`, () =>
        HttpResponse.json({ items: [], page: 1, pageSize: 20, totalPages: 0 }),
      ),
    );

    const { result } = renderHook(() => useGetMyGenerations(1), {
      wrapper: withQueryClient(),
    });

    await waitFor(() => expect(result.current.generations).toBeDefined());
    expect(result.current.generations?.items).toEqual([]);
    expect(result.current.generations?.totalPages).toBe(0);
  });

  it("異常系: 401 で error が確定する", async () => {
    server.use(
      http.get(`${API_BASE}/api/me/generations`, () => new HttpResponse(null, { status: 401 })),
    );

    const { result } = renderHook(() => useGetMyGenerations(1), {
      wrapper: withQueryClient(),
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.status).toBe(401);
  });
});
