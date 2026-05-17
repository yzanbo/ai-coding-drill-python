// /login ページのテスト。
//   要件: authentication.md §2.2 ログイン画面 + §2 受け入れ条件
//   - 未認証時: 「GitHub でログイン」ボタンが正しい /auth/github?next=... を指す
//   - 認証済み: 自動的に next（既定 "/"）へ router.replace
//   - ?auth_error= が付いていたらトースト通知 + URL から auth_error を除去
//   - ?next=https://evil.com のような外部 URL は safeNextPath が "/" に倒す
import { render, screen, waitFor } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { API_BASE, server } from "../../../../test/msw-server";
import { withQueryClient } from "../../../../test/render-with-query";

import LoginPage from "./page";

// next/navigation を制御するためのモック state。テスト毎に上書き。
let mockSearch = new URLSearchParams();
let mockPathname = "/login";
const mockReplace = vi.fn();
const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => mockPathname,
  useRouter: () => ({ push: mockPush, replace: mockReplace, prefetch: vi.fn() }),
  useSearchParams: () => mockSearch,
}));

// sonner.toast.error を spy。プロダクトコード側は import { toast } from "sonner" で
//   オブジェクト経由で参照するので、モジュールごと差し替える。
const toastError = vi.fn();
vi.mock("sonner", () => ({
  toast: { error: (...args: unknown[]) => toastError(...args) },
}));

beforeEach(() => {
  mockSearch = new URLSearchParams();
  mockPathname = "/login";
  mockReplace.mockReset();
  mockPush.mockReset();
  toastError.mockReset();
});

describe("LoginPage", () => {
  it("未認証時は GitHub ログインボタンを表示し、href が /auth/github?next=/ になる", async () => {
    server.use(http.get(`${API_BASE}/auth/me`, () => new HttpResponse(null, { status: 401 })));

    render(<LoginPage />, { wrapper: withQueryClient() });

    const link = await screen.findByRole("link", { name: "GitHub でログイン" });
    expect(link).toHaveAttribute("href", "/auth/github?next=%2F");
  });

  it("?next=/problems が付いていれば href にそのまま流す", async () => {
    mockSearch = new URLSearchParams({ next: "/problems" });
    server.use(http.get(`${API_BASE}/auth/me`, () => new HttpResponse(null, { status: 401 })));

    render(<LoginPage />, { wrapper: withQueryClient() });

    const link = await screen.findByRole("link", { name: "GitHub でログイン" });
    expect(link).toHaveAttribute("href", "/auth/github?next=%2Fproblems");
  });

  it("?next=https://evil.com のような外部 URL は safeNextPath が / に倒す", async () => {
    mockSearch = new URLSearchParams({ next: "https://evil.com" });
    server.use(http.get(`${API_BASE}/auth/me`, () => new HttpResponse(null, { status: 401 })));

    render(<LoginPage />, { wrapper: withQueryClient() });

    const link = await screen.findByRole("link", { name: "GitHub でログイン" });
    expect(link).toHaveAttribute("href", "/auth/github?next=%2F");
  });

  it("認証済みなら next（既定 /）に router.replace で送る", async () => {
    server.use(
      http.get(`${API_BASE}/auth/me`, () =>
        HttpResponse.json({ id: "u1", displayName: "yzanbo", email: null }),
      ),
    );

    render(<LoginPage />, { wrapper: withQueryClient() });

    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith("/"));
  });

  it("?auth_error=oauth_canceled でトーストが出て、URL から auth_error が除去される", async () => {
    mockSearch = new URLSearchParams({ auth_error: "oauth_canceled" });
    server.use(http.get(`${API_BASE}/auth/me`, () => new HttpResponse(null, { status: 401 })));

    render(<LoginPage />, { wrapper: withQueryClient() });

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith(
        "ログインをキャンセルしました。もう一度お試しください。",
      ),
    );
    // URL クリーンアップ: ?auth_error= を除去した path のみが渡される
    expect(mockReplace).toHaveBeenCalledWith("/login");
  });

  it("?auth_error=state_invalid + ?next=/foo の時、next は保持して auth_error だけ除去", async () => {
    mockSearch = new URLSearchParams({ auth_error: "state_invalid", next: "/foo" });
    server.use(http.get(`${API_BASE}/auth/me`, () => new HttpResponse(null, { status: 401 })));

    render(<LoginPage />, { wrapper: withQueryClient() });

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    // mockReplace の引数のうち URL クリーンアップ呼び出しを拾う
    const cleanupCall = mockReplace.mock.calls.find(([url]) => url.startsWith("/login?"));
    expect(cleanupCall?.[0]).toBe("/login?next=%2Ffoo");
  });

  it("未知の auth_error 種別は汎用メッセージで通知する", async () => {
    mockSearch = new URLSearchParams({ auth_error: "unknown_kind" });
    server.use(http.get(`${API_BASE}/auth/me`, () => new HttpResponse(null, { status: 401 })));

    render(<LoginPage />, { wrapper: withQueryClient() });

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith("ログインに失敗しました。もう一度お試しください。"),
    );
  });
});
