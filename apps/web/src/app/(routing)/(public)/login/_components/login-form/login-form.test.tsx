// LoginForm のテスト。
//   役割：/login の Client 側部分（OAuth 開始ボタン + ?auth_error トースト）を検証。
//   認証判定とリダイレクトは親 (page.tsx) が server-side で行うため、本テスト
//   では「未認証ユーザーが LoginForm を見ている状態」を前提に挙動だけを観測する。

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "./login-form";

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

describe("LoginForm", () => {
  it("nextPath='/' の時 href は /auth/github?next=/", async () => {
    render(<LoginForm nextPath="/" />);

    const link = await screen.findByRole("link", { name: "GitHub でログイン" });
    expect(link).toHaveAttribute("href", "/auth/github?next=%2F");
  });

  it("nextPath='/problems' の時 href は /auth/github?next=/problems", async () => {
    render(<LoginForm nextPath="/problems" />);

    const link = await screen.findByRole("link", { name: "GitHub でログイン" });
    expect(link).toHaveAttribute("href", "/auth/github?next=%2Fproblems");
  });

  it("?auth_error=oauth_canceled でトーストが出て、URL から auth_error が除去される", async () => {
    mockSearch = new URLSearchParams({ auth_error: "oauth_canceled" });

    render(<LoginForm nextPath="/" />);

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

    render(<LoginForm nextPath="/foo" />);

    await waitFor(() => expect(toastError).toHaveBeenCalled());
    // mockReplace の引数のうち URL クリーンアップ呼び出しを拾う
    const cleanupCall = mockReplace.mock.calls.find(([url]) => url.startsWith("/login?"));
    expect(cleanupCall?.[0]).toBe("/login?next=%2Ffoo");
  });

  it("未知の auth_error 種別は汎用メッセージで通知する", async () => {
    mockSearch = new URLSearchParams({ auth_error: "unknown_kind" });

    render(<LoginForm nextPath="/" />);

    await waitFor(() =>
      expect(toastError).toHaveBeenCalledWith("ログインに失敗しました。もう一度お試しください。"),
    );
  });
});
