// ProblemGenerationStatusView の結合テスト。
//   要件: problem-generation.md §生成ステータス画面
//   - pending: 「生成中…」を表示
//   - completed: /problems/:problemId に router.replace で遷移
//   - failed: 「生成に失敗しました」+ 再試行ボタン
//   - 取得失敗: 「生成状況を取得できませんでした」
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { API_BASE, server } from "@/test/msw-server";
import { withQueryClient } from "@/test/render-with-query";

import { POLLING_INTERVAL_MS } from "../../_hooks/_fetch/use-get-problem-generation-status/use-get-problem-generation-status";

import { ProblemGenerationStatusView } from "./problem-generation-status-view";

// next/navigation の router.replace を spy できるよう差し替える。
const mockReplace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: mockReplace,
    push: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

beforeEach(() => {
  mockReplace.mockReset();
});

describe("ProblemGenerationStatusView", () => {
  it("pending: 「生成中…」を表示する", async () => {
    server.use(
      http.get(`${API_BASE}/problems/generate/req-pending`, () =>
        HttpResponse.json({ requestId: "req-pending", status: "pending" }),
      ),
    );

    render(<ProblemGenerationStatusView requestId="req-pending" />, {
      wrapper: withQueryClient(),
    });

    expect(await screen.findByText("生成中…")).toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("completed: /problems/:problemId に router.replace で遷移する", async () => {
    server.use(
      http.get(`${API_BASE}/problems/generate/req-ok`, () =>
        HttpResponse.json({
          requestId: "req-ok",
          status: "completed",
          problemId: "prob-xyz",
        }),
      ),
    );

    render(<ProblemGenerationStatusView requestId="req-ok" />, { wrapper: withQueryClient() });

    await vi.waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/problems/prob-xyz"));
  });

  it("failed: 失敗メッセージと再試行ボタンを表示する", async () => {
    server.use(
      http.get(`${API_BASE}/problems/generate/req-ng`, () =>
        HttpResponse.json({ requestId: "req-ng", status: "failed" }),
      ),
    );

    render(<ProblemGenerationStatusView requestId="req-ng" />, { wrapper: withQueryClient() });

    expect(await screen.findByText("生成に失敗しました")).toBeInTheDocument();
    const retry = screen.getByRole("button", { name: "もう一度生成する" });
    await userEvent.click(retry);
    expect(mockReplace).toHaveBeenCalledWith("/problems/new");
  });

  it("取得失敗: エラー文言と再読み込みボタンを表示し、押下で再フェッチが走る", async () => {
    // 1 回目は 500、2 回目以降は pending を返すハンドラ。
    //   「再読み込み」を押下したらサーバへの GET 件数が増えることで refetch が発火したと確認する。
    let getCount = 0;
    server.use(
      http.get(`${API_BASE}/problems/generate/req-err`, () => {
        getCount += 1;
        if (getCount === 1) return new HttpResponse(null, { status: 500 });
        return HttpResponse.json({ requestId: "req-err", status: "pending" });
      }),
    );

    render(<ProblemGenerationStatusView requestId="req-err" />, { wrapper: withQueryClient() });

    expect(await screen.findByText("生成状況を取得できませんでした")).toBeInTheDocument();
    const callsBefore = getCount;

    await userEvent.click(screen.getByRole("button", { name: "再読み込み" }));

    await vi.waitFor(() => expect(getCount).toBeGreaterThan(callsBefore));
  });

  it("completed が一度確定したら、ポーリングで状態が再描画されても replace は 1 回しか呼ばれない", async () => {
    // 同じ completed レスポンスを返し続けるハンドラ。
    //   refetchInterval が completed で false を返す実装が正しければ追加リクエストは
    //   発生しないが、たとえポーリングが続いた場合でも router.replace は問題 ID ベースの
    //   useEffect deps により 1 回しか呼ばれないことを担保する（ナビゲーション暴発防止）。
    server.use(
      http.get(`${API_BASE}/problems/generate/req-once`, () =>
        HttpResponse.json({
          requestId: "req-once",
          status: "completed",
          problemId: "prob-once",
        }),
      ),
    );

    render(<ProblemGenerationStatusView requestId="req-once" />, { wrapper: withQueryClient() });

    await vi.waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/problems/prob-once"));

    // ポーリング 1 周期分 + 余白を待ってから、replace が増えていないことを確認。
    //   POLLING_INTERVAL_MS をフックから取り込むことで、間隔調整時にテスト側の追従漏れを防ぐ。
    await new Promise((resolve) => setTimeout(resolve, POLLING_INTERVAL_MS + 300));
    expect(mockReplace).toHaveBeenCalledTimes(1);
  });
});
