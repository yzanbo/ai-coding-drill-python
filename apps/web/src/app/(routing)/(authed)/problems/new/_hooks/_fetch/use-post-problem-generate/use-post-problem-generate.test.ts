// usePostProblemGenerate のフックテスト。
//   要件: problem-generation.md §POST /api/problems/generate
//   - 202 + requestId が返ったら onSuccess に渡される
//   - 5xx 等はエラーになり error が確定する
import { act, renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { API_BASE, server } from "@/test/msw-server";
import { withQueryClient } from "@/test/render-with-query";

import { usePostProblemGenerate } from "./use-post-problem-generate";

describe("usePostProblemGenerate", () => {
  it("正常系: 202 が返ると onSuccess に requestId が渡る", async () => {
    server.use(
      http.post(`${API_BASE}/api/problems/generate`, () =>
        HttpResponse.json({ requestId: "req-001", status: "pending" }, { status: 202 }),
      ),
    );

    const onSuccess = vi.fn();
    const { result } = renderHook(() => usePostProblemGenerate({ onSuccess }), {
      wrapper: withQueryClient(),
    });

    act(() => {
      result.current.requestGenerate({ category: "array", difficulty: "easy" });
    });

    await waitFor(() => expect(result.current.isPending).toBe(false));
    expect(onSuccess).toHaveBeenCalledWith({ requestId: "req-001", status: "pending" });
    expect(result.current.error).toBeNull();
  });

  it("異常系: 500 が返ると error が立ち onSuccess は呼ばれない", async () => {
    server.use(
      http.post(`${API_BASE}/api/problems/generate`, () => new HttpResponse(null, { status: 500 })),
    );

    const onSuccess = vi.fn();
    const { result } = renderHook(() => usePostProblemGenerate({ onSuccess }), {
      wrapper: withQueryClient(),
    });

    act(() => {
      result.current.requestGenerate({ category: "string", difficulty: "easy" });
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(onSuccess).not.toHaveBeenCalled();
  });
});
