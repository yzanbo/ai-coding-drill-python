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

  it("completed 確定後の再描画で useEffect が再発火せず replace は 1 回しか呼ばれない", async () => {
    // 守りたいバグ: status オブジェクトの reference 揺れで useEffect が再発火し、
    //   router.replace が連発される。これはレンダー直後に同期で再現するため、
    //   ポーリング 1 周期分の壁時計待ちは不要（refetchInterval も completed で false を
    //   返すため、そもそも追加 fetch も発生しない）。
    //   waitFor で 1 回目の replace 到達を見届けた後、マイクロタスクと 1 タイマー tick を
    //   flush してから、replace が増えていないことを確認する。
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

    // マイクロタスクキュー + 直近のタイマー tick を 1 巡 flush。
    //   useEffect の再発火はレンダー直後に同期で起きるので、これで十分捕まる。
    await Promise.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(mockReplace).toHaveBeenCalledTimes(1);
  });
});
