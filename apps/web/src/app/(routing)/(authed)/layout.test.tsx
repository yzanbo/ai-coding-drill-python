// (authed) layout のテスト。
//   要件: authentication.md §1.1 ビジネスルール（認証必須）
//   - 認証時: children を表示
//   - 未認証時: /login?next=<現在のpath> に router.replace
//   - 読み込み中: 何も表示しない（チラ見せ防止）
import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { API_BASE, server } from "../../../test/msw-server";
import { withQueryClient } from "../../../test/render-with-query";

import AuthedLayout from "./layout";

let mockPathname = "/problems";
const mockReplace = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ push: vi.fn(), replace: mockReplace, prefetch: vi.fn() }),
}));

beforeEach(() => {
  mockPathname = "/problems";
  mockReplace.mockReset();
});

describe("AuthedLayout", () => {
  it("認証済みなら children を描画する", async () => {
    server.use(
      http.get(`${API_BASE}/auth/me`, () =>
        HttpResponse.json({ id: "u1", displayName: "yzanbo", email: null }),
      ),
    );

    render(
      <AuthedLayout>
        <div data-testid="child">protected</div>
      </AuthedLayout>,
      { wrapper: withQueryClient() },
    );

    expect(await screen.findByTestId("child")).toHaveTextContent("protected");
    expect(mockReplace).not.toHaveBeenCalled();
  });

  it("未認証なら /login?next=<現在のpath> へリダイレクトし、children を出さない", async () => {
    server.use(http.get(`${API_BASE}/auth/me`, () => new HttpResponse(null, { status: 401 })));

    render(
      <AuthedLayout>
        <div data-testid="child">protected</div>
      </AuthedLayout>,
      { wrapper: withQueryClient() },
    );

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/login?next=%2Fproblems"));
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
  });

  it("読み込み中は children を出さない（チラ見せ防止）", () => {
    // ハンドラ未登録だと onUnhandledRequest:"error" で落ちるため、応答を遅延させる handler を置く。
    server.use(
      http.get(
        `${API_BASE}/auth/me`,
        async () =>
          await new Promise<Response>((resolve) => {
            setTimeout(() => resolve(new HttpResponse(null, { status: 401 })), 1000);
          }),
      ),
    );

    render(
      <AuthedLayout>
        <div data-testid="child">protected</div>
      </AuthedLayout>,
      { wrapper: withQueryClient() },
    );

    // 初期レンダー時点では isLoading=true で children は出ない
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
    expect(mockReplace).not.toHaveBeenCalled();
  });
});
