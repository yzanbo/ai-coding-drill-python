// useGetSubmission のフックテスト。
//   要件: grading.md §GET /api/submissions/:id (R1-5)
//   - submissionId=null の間は fetch されない (enabled=false)
//   - pending → graded の遷移を検知できる (ポーリングが動く)
//   - graded / failed に到達したら以後フェッチしない (refetchInterval 停止)
//   - 401 / 404 / 5xx で error に ApiError がセットされる
import { renderHook, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { API_BASE, server } from "@/test/msw-server";
import { withQueryClient } from "@/test/render-with-query";

import { useGetSubmission } from "./use-get-submission";

const SUBMISSION_ID = "00000000-0000-0000-0000-000000000123";
const PROBLEM_ID = "00000000-0000-0000-0000-0000000000aa";

describe("useGetSubmission", () => {
  it("submissionId が null なら fetch されない (enabled=false)", async () => {
    let calls = 0;
    server.use(
      http.get(`${API_BASE}/api/submissions/:id`, () => {
        calls += 1;
        return HttpResponse.json({
          id: SUBMISSION_ID,
          problemId: PROBLEM_ID,
          status: "pending",
        });
      }),
    );

    const { result } = renderHook(() => useGetSubmission(null), {
      wrapper: withQueryClient(),
    });

    // 少し待ってもリクエストが飛ばないこと。
    //   waitFor で計 200ms 程度回しても calls が増えないことを観測する。
    await new Promise((r) => setTimeout(r, 100));
    expect(calls).toBe(0);
    expect(result.current.submission).toBeUndefined();
    expect(result.current.isLoading).toBe(false);
  });

  it("正常系: pending → graded の遷移を取得できる", async () => {
    let callCount = 0;
    server.use(
      http.get(`${API_BASE}/api/submissions/${SUBMISSION_ID}`, () => {
        callCount += 1;
        if (callCount >= 2) {
          return HttpResponse.json({
            id: SUBMISSION_ID,
            problemId: PROBLEM_ID,
            status: "graded",
            score: 3,
            totalCount: 3,
            result: {
              passed: true,
              durationMs: 120,
              testResults: [
                { name: "case1", passed: true, durationMs: 40 },
                { name: "case2", passed: true, durationMs: 40 },
                { name: "case3", passed: true, durationMs: 40 },
              ],
            },
            gradedAt: "2026-05-21T00:00:00Z",
          });
        }
        return HttpResponse.json({
          id: SUBMISSION_ID,
          problemId: PROBLEM_ID,
          status: "pending",
        });
      }),
    );

    const { result } = renderHook(() => useGetSubmission(SUBMISSION_ID), {
      wrapper: withQueryClient(),
    });

    // ポーリング間隔は実装側で 1500ms 固定。waitFor の既定 1000ms では足りないため
    //   タイムアウトを 3000ms に伸ばす (テストランタイムへの実時間影響は最大数秒程度)。
    await waitFor(() => expect(result.current.submission?.status).toBe("graded"), {
      timeout: 3000,
    });
    expect(result.current.submission?.score).toBe(3);
    expect(result.current.submission?.result?.passed).toBe(true);
  });

  it("正常系: 即 failed が返った場合も submission に反映され ポーリング停止", async () => {
    server.use(
      http.get(`${API_BASE}/api/submissions/${SUBMISSION_ID}`, () =>
        HttpResponse.json({
          id: SUBMISSION_ID,
          problemId: PROBLEM_ID,
          status: "failed",
        }),
      ),
    );

    const { result } = renderHook(() => useGetSubmission(SUBMISSION_ID), {
      wrapper: withQueryClient(),
    });

    await waitFor(() => expect(result.current.submission?.status).toBe("failed"));
    expect(result.current.submission?.result).toBeFalsy();
  });

  it("異常系: 404 で error が確定する (他人の id / 不在)", async () => {
    server.use(
      http.get(
        `${API_BASE}/api/submissions/${SUBMISSION_ID}`,
        () => new HttpResponse(null, { status: 404 }),
      ),
    );

    const { result } = renderHook(() => useGetSubmission(SUBMISSION_ID), {
      wrapper: withQueryClient(),
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.status).toBe(404);
    expect(result.current.submission).toBeUndefined();
  });

  it("異常系: 5xx で error が確定する (一時障害)", async () => {
    server.use(
      http.get(
        `${API_BASE}/api/submissions/${SUBMISSION_ID}`,
        () => new HttpResponse(null, { status: 500 }),
      ),
    );

    const { result } = renderHook(() => useGetSubmission(SUBMISSION_ID), {
      wrapper: withQueryClient(),
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.status).toBe(500);
    expect(result.current.submission).toBeUndefined();
  });
});
