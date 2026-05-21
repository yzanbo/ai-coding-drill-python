// /login ページ（Server Component）のロジック単体テスト。
//
// 何を担保するか：
//   - 認証済み（session_id Cookie あり）で /login を踏むと redirect() で
//     nextPath（既定 "/"）に飛ばされる
//   - 未認証（Cookie なし）なら redirect しない（= 子の LoginForm を描画する）
//   - ?next= の検証は safeNextPath（lib/utils/safe-next-path）が担うので、
//     ここでは外部 URL 拒否のみ代表的なケースで確認
//
// 仕組み：
//   LoginPage は async な Server Component なので、関数を直接 await して呼び出し、
//   redirect() / cookies() のモックが期待どおり呼ばれたかを観測する。
//   実際の Next.js ランタイムでは redirect() は内部例外を throw して制御を抜くが、
//   テストでは vi.fn() に置き換えて副作用だけ拾えれば検証目的を満たす。

import { beforeEach, describe, expect, it, vi } from "vitest";

// next/navigation: redirect だけ差し替え。
//   redirect は通常 throw するが、テストでは spy だけ取りたいので何もしないモックにする。
const mockRedirect = vi.fn();
vi.mock("next/navigation", () => ({
  redirect: (...args: unknown[]) => mockRedirect(...args),
}));

// next/headers: cookies() を差し替える。テストごとに「Cookie あり / なし」を切替。
let mockCookieGetReturn: { value: string } | undefined;
vi.mock("next/headers", () => ({
  cookies: () =>
    Promise.resolve({
      get: () => mockCookieGetReturn,
    }),
}));

// 子の Client Component（LoginForm）はインポートだけ通せばよい。
//   LoginPage は <LoginForm nextPath={...} /> という React 要素を返すだけで、
//   テスト側ではそれを render せず element の props を直接観測する
//   （Server Component を「呼ぶだけ」で済ませる testing パターン）。
vi.mock("./_components/login-form/login-form", () => ({
  LoginForm: (props: { nextPath: string }) => props,
}));

// import は vi.mock の後に置く（Vitest が hoisting する mock を先に効かせるため）。
const { LoginForm } = await import("./_components/login-form/login-form");
const { default: LoginPage } = await import("./page");

beforeEach(() => {
  mockRedirect.mockReset();
  mockCookieGetReturn = undefined;
});

describe("LoginPage", () => {
  it("認証済み（Cookie あり）なら nextPath（既定 /）に redirect する", async () => {
    mockCookieGetReturn = { value: "dummy-session" };
    await LoginPage({ searchParams: Promise.resolve({}) });
    expect(mockRedirect).toHaveBeenCalledWith("/");
  });

  it("認証済み + ?next=/problems なら /problems に redirect する", async () => {
    mockCookieGetReturn = { value: "dummy-session" };
    await LoginPage({ searchParams: Promise.resolve({ next: "/problems" }) });
    expect(mockRedirect).toHaveBeenCalledWith("/problems");
  });

  it("認証済み + ?next=https://evil.com は safeNextPath が / に倒す", async () => {
    mockCookieGetReturn = { value: "dummy-session" };
    await LoginPage({ searchParams: Promise.resolve({ next: "https://evil.com" }) });
    expect(mockRedirect).toHaveBeenCalledWith("/");
  });

  it("未認証（Cookie なし）なら redirect せず LoginForm を nextPath 付きで返す", async () => {
    mockCookieGetReturn = undefined;
    const element = await LoginPage({
      searchParams: Promise.resolve({ next: "/problems" }),
    });
    expect(mockRedirect).not.toHaveBeenCalled();
    // 返り値は <LoginForm nextPath="/problems" />。React 要素の type / props を観測する。
    expect(element?.type).toBe(LoginForm);
    expect(element?.props).toEqual({ nextPath: "/problems" });
  });

  it("未認証 + ?next 無し なら LoginForm の nextPath は '/'", async () => {
    mockCookieGetReturn = undefined;
    const element = await LoginPage({ searchParams: Promise.resolve({}) });
    expect(element?.props).toEqual({ nextPath: "/" });
  });
});
