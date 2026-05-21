// useCancelMyGeneration のフックテスト。
//   要件: problem-generation.md §履歴上のアクション (cancel)
//   - 正常系: 200 で {id, status:'canceled'} を返し、["me","generations"] を invalidate
//   - 異常系: 409 で error.status=409
//   - 異常系: 404 で error.status=404

import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { API_BASE, server } from "@/test/msw-server";
import { withQueryClient } from "@/test/render-with-query";

import { useCancelMyGeneration } from "./use-cancel-my-generation";

const GR_ID = "00000000-0000-0000-0000-000000000001";

describe("useCancelMyGeneration", () => {
  it("正常系: cancel が成功して {id, status:'canceled'} を返す", async () => {
    server.use(
      http.post(`${API_BASE}/api/me/generations/${GR_ID}/cancel`, () =>
        HttpResponse.json({ id: GR_ID, status: "canceled" }),
      ),
    );
    const { result } = renderHook(() => useCancelMyGeneration(), {
      wrapper: withQueryClient(),
    });
    const res = await result.current.cancel(GR_ID);
    expect(res.id).toBe(GR_ID);
    expect(res.status).toBe("canceled");
  });

  it("異常系: 409 で error.status=409", async () => {
    server.use(
      http.post(`${API_BASE}/api/me/generations/${GR_ID}/cancel`, () =>
        HttpResponse.json(
          { detail: "generation request is not cancelable (status=completed)" },
          { status: 409 },
        ),
      ),
    );
    const { result } = renderHook(() => useCancelMyGeneration(), {
      wrapper: withQueryClient(),
    });
    await expect(result.current.cancel(GR_ID)).rejects.toThrow();
    await waitFor(() => expect(result.current.error?.status).toBe(409));
  });

  it("異常系: 404 で error.status=404", async () => {
    server.use(
      http.post(
        `${API_BASE}/api/me/generations/${GR_ID}/cancel`,
        () => new HttpResponse(null, { status: 404 }),
      ),
    );
    const { result } = renderHook(() => useCancelMyGeneration(), {
      wrapper: withQueryClient(),
    });
    await expect(result.current.cancel(GR_ID)).rejects.toThrow();
    await waitFor(() => expect(result.current.error?.status).toBe(404));
  });
});
