// E2E 共通の Playwright fixture 群。
//
// なぜ要るか:
//   - 各テスト前に DB / Redis を初期化したい (テスト間で user / session が
//     残ると 「同じ user で再ログイン」「ログアウト後の旧 session 401」等の
//     アサートが不安定になる)
//   - Mock GitHub OAuth サーバの /_test/reset を叩く HTTP request だけなので
//     軽量に Playwright の test.extend で実現する

import { test as base, type Page } from "@playwright/test";
import { MOCK_GITHUB_ORIGIN } from "./constants";

/**
 * DB (users / auth_providers) と Redis (session / state / rate limit) を全消去する。
 * 各 test の beforeEach から呼ぶ想定。
 */
async function resetState(page: Page): Promise<void> {
  const res = await page.request.post(`${MOCK_GITHUB_ORIGIN}/_test/reset`);
  if (!res.ok()) {
    throw new Error(`state reset failed: ${res.status()} ${await res.text()}`);
  }
}

/**
 * Mock GitHub server に対して認可遷移を行うショートカット。
 * /auth/github をブラウザで踏むと Backend が mock の /authorize に 302 で飛ばし、
 * mock が即 /auth/github/callback に code+state を載せて 302 で返す。
 * 結果として callback の処理が走り、セッション cookie が発行されてホーム / に着地する。
 */
async function loginViaMockGithub(
  page: Page,
  options: { mode?: "auto" | "cancel" } = {},
): Promise<void> {
  // 手順:
  //   1. Backend の /auth/github をリダイレクト追従なし (maxRedirects: 0) で踏み、
  //      state を発行させ Location ヘッダから mock /authorize の URL を取り出す
  //   2. URL に _mode クエリを足してブラウザで開く
  //      (Backend が組み立てる URL に _mode を埋め込めないため後付けで追加する)
  //   3. mock /authorize が callback に 302 → Backend が user 情報取得・session 発行 → / に着地
  const mode = options.mode ?? "auto";
  const initialResponse = await page.request.get("/auth/github", {
    maxRedirects: 0,
  });
  const authorizeUrl = initialResponse.headers().location;
  if (!authorizeUrl) {
    throw new Error("/auth/github did not return a redirect location");
  }
  const url = new URL(authorizeUrl);
  url.searchParams.set("_mode", mode);
  await page.goto(url.toString());
}

/**
 * ログイン → 認証必須ページへの遷移を 1 つにまとめたショートカット。
 * loginViaMockGithub の直後に page.goto すると、Cookie がブラウザに
 * セットされ切る前に (authed) layout が未認証扱いで /login にリダイレクト
 * する race を踏むため、必ず /（ログイン後の終端着地）を待ってから次の
 * URL に進む。3 spec で同じ手順を繰り返さないよう helper に閉じ込める。
 */
async function loginAndGoto(page: Page, path: string): Promise<void> {
  await loginViaMockGithub(page);
  await page.waitForURL("/");
  await page.goto(path);
}

/**
 * ログアウト POST のショートカット。CSRF token を Cookie から取り出して
 * X-CSRF-Token ヘッダに詰める (double submit cookie の正規経路を再現)。
 */
async function logoutViaApi(page: Page): Promise<number> {
  const cookies = await page.context().cookies();
  const csrfToken = cookies.find((c) => c.name === "csrf_token")?.value ?? "";
  const res = await page.request.post("/auth/logout", {
    headers: { "X-CSRF-Token": csrfToken },
  });
  return res.status();
}

/**
 * test.extend: 全 spec で resetState を beforeEach 相当に走らせる。
 * Playwright の fixture システムを使うと test ごとに自動的に呼ばれる。
 */
export const test = base.extend<{ resetState: () => Promise<void> }>({
  // page と一緒に state を初期化する。test 関数内で `resetState` を引数で受け取ることもできるし、
  // 自動的に page よりも先に走る依存として宣言してもよい。
  // ここでは「明示的に呼ぶ」設計にして、必要なテストだけ resetState を引数化する。
  resetState: async ({ page }, use) => {
    await use(async () => {
      await resetState(page);
    });
  },
});

export { expect } from "@playwright/test";
export { loginAndGoto, loginViaMockGithub, logoutViaApi, resetState };
