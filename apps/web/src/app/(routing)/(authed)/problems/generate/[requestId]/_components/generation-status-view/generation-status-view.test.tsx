// GenerationStatusView の結合テスト。
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

import { GenerationStatusView } from "./generation-status-view";

// next/navigation の router.replace / router.refresh を spy できるよう差し替える。
const mockReplace = vi.fn();
const mockRefresh = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: mockReplace,
    refresh: mockRefresh,
    push: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

beforeEach(() => {
  mockReplace.mockReset();
  mockRefresh.mockReset();
});

describe("GenerationStatusView", () => {
  it("pending: 「生成中…」を表示する", async () => {
    server.use(
      http.get(`${API_BASE}/problems/generate/req-pending`, () =>
        HttpResponse.json({ requestId: "req-pending", status: "pending" }),
      ),
    );

    render(<GenerationStatusView requestId="req-pending" />, { wrapper: withQueryClient() });

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

    render(<GenerationStatusView requestId="req-ok" />, { wrapper: withQueryClient() });

    await vi.waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/problems/prob-xyz"));
  });

  it("failed: 失敗メッセージと再試行ボタンを表示する", async () => {
    server.use(
      http.get(`${API_BASE}/problems/generate/req-ng`, () =>
        HttpResponse.json({ requestId: "req-ng", status: "failed" }),
      ),
    );

    render(<GenerationStatusView requestId="req-ng" />, { wrapper: withQueryClient() });

    expect(await screen.findByText("生成に失敗しました")).toBeInTheDocument();
    const retry = screen.getByRole("button", { name: "もう一度生成する" });
    await userEvent.click(retry);
    expect(mockReplace).toHaveBeenCalledWith("/problems/new");
  });

  it("取得失敗: エラー文言と再読み込みボタンを表示する", async () => {
    server.use(
      http.get(
        `${API_BASE}/problems/generate/req-err`,
        () => new HttpResponse(null, { status: 500 }),
      ),
    );

    render(<GenerationStatusView requestId="req-err" />, { wrapper: withQueryClient() });

    expect(await screen.findByText("生成状況を取得できませんでした")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "再読み込み" }));
    expect(mockRefresh).toHaveBeenCalled();
  });
});
