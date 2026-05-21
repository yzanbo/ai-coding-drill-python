// ルート / と存在しない URL のリダイレクト挙動の E2E。
//
// 要件（ユーザー指示、2026-05-21）：
//   - / は常に /problems に遷移する（ランディング廃止）
//   - 存在しない URL（404）：
//     - ログイン済み  → /problems に遷移
//     - 未ログイン    → / に遷移（実質 /problems に最終着地）
//
// なぜ E2E が要るか：
//   /（Server Component の redirect）と not-found.tsx（Client Component の
//   useEffect 経由 router.replace）は実装手段が異なる。ブラウザ越しに
//   「最終 URL がどこに着地するか」を観測しないと回帰が拾えない。

import { expect, loginViaMockGithub, test } from "./_helpers/test-fixtures";

test.describe.configure({ mode: "serial" });

test.beforeEach(async ({ resetState }) => {
  await resetState();
});

test.describe("/ のリダイレクト", () => {
  test("未ログインで / を踏むと /problems に着地する", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL("/problems");
  });

  test("ログイン済みで / を踏むと /problems に着地する", async ({ page }) => {
    await loginViaMockGithub(page);
    await page.goto("/");
    await expect(page).toHaveURL("/problems");
  });
});

test.describe("404（存在しない URL）のリダイレクト", () => {
  test("未ログインで存在しない URL を踏むと / 経由で /problems に着地する", async ({ page }) => {
    // not-found.tsx の useEffect が router.replace("/") を呼び、
    // "/" 側のサーバ side redirect が /problems に飛ばす。
    await page.goto("/this-route-does-not-exist");
    await expect(page).toHaveURL("/problems");
  });

  test("ログイン済みで存在しない URL を踏むと /problems に着地する", async ({ page }) => {
    await loginViaMockGithub(page);
    await page.goto("/this-route-does-not-exist");
    await expect(page).toHaveURL("/problems");
  });
});
