// useRetryMyGeneration のフックテスト。
//   要件: problem-generation.md §履歴上のアクション (retry)
//   - 正常系: 202 で {id, status:'pending', retryOf} を返す
//   - 異常系: 409 で error.status=409

import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { API_BASE, server } from "@/test/msw-server";
import { withQueryClient } from "@/test/render-with-query";

import { useRetryMyGeneration } from "./use-retry-my-generation";

const ORIG_ID = "00000000-0000-0000-0000-000000000001";
const NEW_ID = "00000000-0000-0000-0000-000000000002";

describe("useRetryMyGeneration", () => {
  it("正常系: retry が成功して新規 id + retryOf を返す", async () => {
    server.use(
      http.post(`${API_BASE}/api/me/generations/${ORIG_ID}/retry`, () =>
        HttpResponse.json({ id: NEW_ID, status: "pending", retryOf: ORIG_ID }, { status: 202 }),
      ),
    );
    const { result } = renderHook(() => useRetryMyGeneration(), {
      wrapper: withQueryClient(),
    });
    const res = await result.current.retry(ORIG_ID);
    expect(res.id).toBe(NEW_ID);
    expect(res.status).toBe("pending");
    expect(res.retryOf).toBe(ORIG_ID);
  });

  it("異常系: 409 で error.status=409", async () => {
    server.use(
      http.post(`${API_BASE}/api/me/generations/${ORIG_ID}/retry`, () =>
        HttpResponse.json(
          { detail: "generation request is not retryable (status=pending)" },
          { status: 409 },
        ),
      ),
    );
    const { result } = renderHook(() => useRetryMyGeneration(), {
      wrapper: withQueryClient(),
    });
    await expect(result.current.retry(ORIG_ID)).rejects.toThrow();
    await waitFor(() => expect(result.current.error?.status).toBe(409));
  });
});
