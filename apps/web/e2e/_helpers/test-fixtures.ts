// E2E 共通の Playwright fixture 群。
//
// なぜ要るか:
//   - 各テスト前に DB / Redis を初期化したい (テスト間で user / session が
//     残ると 「同じ user で再ログイン」「ログアウト後の旧 session 401」等の
//     アサートが不安定になる)
//   - Mock GitHub OAuth サーバの /_test/reset を叩く HTTP request だけなので
//     軽量に Playwright の test.extend で実現する

import { test as base, type Page } from "@playwright/test";

// _MOCK_GITHUB_ORIGIN: playwright.config.ts と同じ値を持つ (循環参照を避けるため定数複製)。
// 将来この値が増えたら e2e/_helpers/constants.ts に切り出す。
const _MOCK_GITHUB_ORIGIN = "http://127.0.0.1:18001";

/**
 * DB (users / auth_providers) と Redis (session / state / rate limit) を全消去する。
 * 各 test の beforeEach から呼ぶ想定。
 */
async function resetState(page: Page): Promise<void> {
  const res = await page.request.post(`${_MOCK_GITHUB_ORIGIN}/_test/reset`);
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
  options: { mode?: "auto" | "cancel"; userVariant?: string } = {},
): Promise<void> {
  // /auth/github を browser で開くと Backend が mock の /authorize に 302。
  // mock は即 callback に 302、Backend が user 情報取得・session 発行、最終的に / に redirect。
  // ただし mock /authorize にクエリで _mode / _user_variant を伝える必要があり、
  // Backend が組み立てる URL に直接埋めにくいため、mock 側に存在する static endpoint で
  // 「次に呼ばれる /authorize の挙動」を上書きする仕組みは持たず、
  // 代わりに本ヘルパは /auth/github を踏まずに mock の /authorize を直接ブラウザで開く。
  // (Backend の /auth/github と等価な挙動を mock 側で完結させる)
  const mode = options.mode ?? "auto";
  const userVariant = options.userVariant ?? "";
  // Backend に state を発行させるため、まず /auth/github を踏む。
  // Backend は mock の /authorize に 302 を返すが、その URL に _mode / _user_variant が
  // 含まれないため、ブラウザのリダイレクト追従を一旦止めて URL を読み取り、
  // _mode / _user_variant を追加した URL にブラウザを誘導する。
  const initialResponse = await page.request.get("/auth/github", {
    maxRedirects: 0,
  });
  const authorizeUrl = initialResponse.headers().location;
  if (!authorizeUrl) {
    throw new Error("/auth/github did not return a redirect location");
  }
  const url = new URL(authorizeUrl);
  url.searchParams.set("_mode", mode);
  if (userVariant) url.searchParams.set("_user_variant", userVariant);
  await page.goto(url.toString());
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
export { loginViaMockGithub, resetState };
