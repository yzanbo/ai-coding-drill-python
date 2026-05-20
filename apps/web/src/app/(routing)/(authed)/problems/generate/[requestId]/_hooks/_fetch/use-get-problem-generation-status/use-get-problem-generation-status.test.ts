// useGetProblemGenerationStatus のフックテスト。
//   要件: problem-generation.md §GET /problems/generate/:requestId
//   - pending → completed の遷移を検知できる（ポーリングが動く）
//   - completed / failed に到達したら以後フェッチしない（refetchInterval 停止）
import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { API_BASE, server } from "@/test/msw-server";
import { withQueryClient } from "@/test/render-with-query";

import { useGetProblemGenerationStatus } from "./use-get-problem-generation-status";

describe("useGetProblemGenerationStatus", () => {
  it("正常系: pending → completed の遷移を取得できる", async () => {
    let callCount = 0;
    server.use(
      http.get(`${API_BASE}/problems/generate/req-001`, () => {
        callCount += 1;
        if (callCount >= 2) {
          return HttpResponse.json({
            requestId: "req-001",
            status: "completed",
            problemId: "prob-xyz",
          });
        }
        return HttpResponse.json({ requestId: "req-001", status: "pending" });
      }),
    );

    const { result } = renderHook(() => useGetProblemGenerationStatus("req-001"), {
      wrapper: withQueryClient(),
    });

    // ポーリング間隔は実装側で 1500ms 固定。waitFor の既定 1000ms では足りないため
    //   タイムアウトを 3000ms に伸ばす（テストランタイムへの実時間影響は最大数秒程度）。
    await waitFor(() => expect(result.current.status?.status).toBe("completed"), {
      timeout: 3000,
    });
    expect(result.current.status?.problemId).toBe("prob-xyz");
  });

  it("正常系: 即 failed が返った場合も status に反映される", async () => {
    server.use(
      http.get(`${API_BASE}/problems/generate/req-002`, () =>
        HttpResponse.json({ requestId: "req-002", status: "failed" }),
      ),
    );

    const { result } = renderHook(() => useGetProblemGenerationStatus("req-002"), {
      wrapper: withQueryClient(),
    });

    await waitFor(() => expect(result.current.status?.status).toBe("failed"));
    expect(result.current.status?.problemId).toBeFalsy();
  });

  it("異常系: 5xx エラーで error が確定する", async () => {
    server.use(
      http.get(
        `${API_BASE}/problems/generate/req-err`,
        () => new HttpResponse(null, { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useGetProblemGenerationStatus("req-err"), {
      wrapper: withQueryClient(),
    });

    // error は TanStack Query 既定で「未確定 = null」「確定 = ApiError 等」。
    //   null だと toBeDefined() は通ってしまうため、明示的に非 null を待つ。
    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.status).toBeUndefined();
  });
});
