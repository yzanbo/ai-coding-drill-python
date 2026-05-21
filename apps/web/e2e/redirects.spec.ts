// ルート / と存在しない URL のリダイレクト挙動の E2E。
//
// 要件（ユーザー指示、2026-05-21）：
//   - / の挙動：
//     - ログイン済み → /problems に遷移
//     - 未ログイン   → / に留まりランディング画面を表示
//   - 存在しない URL（404）：
//     - ログイン済み → /problems に遷移
//     - 未ログイン   → / に遷移（ランディング画面を表示）
//
// なぜ E2E が要るか：
//   / と not-found.tsx はどちらも Server Component で cookies() を見て
//   redirect() するが、Next.js の 404 ハンドリング経路は別系統。ブラウザ越しに
//   「最終 URL がどこに着地するか」を観測しないと回帰が拾えない。

import { expect, loginViaMockGithub, test } from "./_helpers/test-fixtures";

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ resetState }) => {
  await resetState();
});

test.describe("/ の挙動", () => {
  test("未ログインで / を踏むと / に留まりランディングが表示される", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL("/");
    // ランディングの見出しが見える（認証要否の分岐の正の側）。
    await expect(page.getByRole("heading", { name: "AI Coding Drill" })).toBeVisible();
  });

  test("ログイン済みで / を踏むと /problems に着地する", async ({ page }) => {
    await loginViaMockGithub(page);
    await page.goto("/");
    await expect(page).toHaveURL("/problems");
  });
});

test.describe("404（存在しない URL）のリダイレクト", () => {
  test("未ログインで存在しない URL を踏むと / に着地する", async ({ page }) => {
    // not-found.tsx が server-side で redirect("/") を返し、未ログインなので
    // / 側でも redirect が起きずランディングが表示される。
    await page.goto("/this-route-does-not-exist");
    await expect(page).toHaveURL("/");
    await expect(page.getByRole("heading", { name: "AI Coding Drill" })).toBeVisible();
  });

  test("ログイン済みで存在しない URL を踏むと /problems に着地する", async ({ page }) => {
    await loginViaMockGithub(page);
    await page.goto("/this-route-does-not-exist");
    await expect(page).toHaveURL("/problems");
  });
});
