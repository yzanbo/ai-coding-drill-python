// SiteHeader のコンポーネントテスト。
//   要件: authentication.md §1.5 共通画面コンポーネント
//   - 未認証時: 「ログイン」リンク
//   - 認証時:   ユーザー名 + 「ログアウト」ボタン（押下で /auth/logout → "/" 遷移）
//   - /login ページ上では未認証 CTA を出さない
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { API_BASE, server } from "../../../test/msw-server";
import { withQueryClient } from "../../../test/render-with-query";

import { SiteHeader } from "./site-header";

// next/navigation は jsdom に無いので vi.mock で置き換える。
//   テスト毎に router / pathname を差し替えたいので、変数経由で参照する。
let mockPathname = "/";
const mockReplace = vi.fn();
const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ push: mockPush, replace: mockReplace, prefetch: vi.fn() }),
}));

beforeEach(() => {
  mockPathname = "/";
  mockReplace.mockReset();
  mockPush.mockReset();
});

describe("SiteHeader", () => {
  it("未認証（/auth/me=401）時はログインリンクのみを表示する", async () => {
    server.use(http.get(`${API_BASE}/auth/me`, () => new HttpResponse(null, { status: 401 })));

    render(<SiteHeader />, { wrapper: withQueryClient() });

    const link = await screen.findByRole("link", { name: "ログイン" });
    // pathname="/" のため ?next=%2F が付く（SiteHeader は /login 以外の任意 path で next を保存する）
    expect(link).toHaveAttribute("href", "/login?next=%2F");
    expect(screen.queryByRole("button", { name: "ログアウト" })).not.toBeInTheDocument();
  });

  it("/login ページ上では未認証時の「ログイン」CTA を抑制する", async () => {
    mockPathname = "/login";
    server.use(http.get(`${API_BASE}/auth/me`, () => new HttpResponse(null, { status: 401 })));

    render(<SiteHeader />, { wrapper: withQueryClient() });

    // 読み込み完了を待つ（ユーザー名が出ないことを確認するため fetch を完了させる）
    await waitFor(() =>
      expect(screen.queryByRole("link", { name: "ログイン" })).not.toBeInTheDocument(),
    );
  });

  it("認証済み（200）時はユーザー名 + ログアウトボタンを表示する", async () => {
    server.use(
      http.get(`${API_BASE}/auth/me`, () =>
        HttpResponse.json({ id: "u1", displayName: "yzanbo", email: null }),
      ),
    );

    render(<SiteHeader />, { wrapper: withQueryClient() });

    expect(await screen.findByText("yzanbo")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ログアウト" })).toBeInTheDocument();
  });

  it("ログアウトボタン押下で POST /auth/logout を叩き、成功後にホーム / へ push", async () => {
    server.use(
      http.get(`${API_BASE}/auth/me`, () =>
        HttpResponse.json({ id: "u1", displayName: "yzanbo", email: null }),
      ),
      http.post(`${API_BASE}/auth/logout`, () => new HttpResponse(null, { status: 204 })),
    );

    render(<SiteHeader />, { wrapper: withQueryClient() });

    const logoutButton = await screen.findByRole("button", { name: "ログアウト" });
    await userEvent.click(logoutButton);

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/"));
  });
});
