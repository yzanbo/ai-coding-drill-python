// usePostSubmission のフックテスト。
//   要件: grading.md §POST /api/submissions
//   - 202 + submissionId が返ったら onSuccess に渡され data に詰まる
//   - 5xx 等はエラーになり error が確定する
//   - 404 / 401 等の業務 / 認証エラーも error として渡る

import { act, renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";

import { API_BASE, server } from "@/test/msw-server";
import { withQueryClient } from "@/test/render-with-query";

import { usePostSubmission } from "./use-post-submission";

describe("usePostSubmission", () => {
  it("正常系: 202 が返ると onSuccess に submissionId が渡り data にも詰まる", async () => {
    server.use(
      http.post(`${API_BASE}/api/submissions`, () =>
        HttpResponse.json({ submissionId: "sub-001", status: "pending" }, { status: 202 }),
      ),
    );

    const onSuccess = vi.fn();
    const { result } = renderHook(() => usePostSubmission({ onSuccess }), {
      wrapper: withQueryClient(),
    });

    act(() => {
      result.current.submitAnswer({ problemId: "prob-001", code: "const solve = () => 1;" });
    });

    await waitFor(() => expect(result.current.isPending).toBe(false));
    expect(onSuccess).toHaveBeenCalledWith({ submissionId: "sub-001", status: "pending" });
    expect(result.current.data).toEqual({ submissionId: "sub-001", status: "pending" });
    expect(result.current.error).toBeNull();
  });

  it("異常系: 500 が返ると error が立ち onSuccess は呼ばれない", async () => {
    server.use(
      http.post(`${API_BASE}/api/submissions`, () => new HttpResponse(null, { status: 500 })),
    );

    const onSuccess = vi.fn();
    const { result } = renderHook(() => usePostSubmission({ onSuccess }), {
      wrapper: withQueryClient(),
    });

    act(() => {
      result.current.submitAnswer({ problemId: "prob-001", code: "x" });
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.status).toBe(500);
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("異常系: 404 (問題が存在しない) も error として上がる", async () => {
    server.use(
      http.post(`${API_BASE}/api/submissions`, () =>
        HttpResponse.json({ detail: "指定された問題が見つかりません" }, { status: 404 }),
      ),
    );

    const { result } = renderHook(() => usePostSubmission(), {
      wrapper: withQueryClient(),
    });

    act(() => {
      result.current.submitAnswer({ problemId: "missing", code: "x" });
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.status).toBe(404);
  });
});
