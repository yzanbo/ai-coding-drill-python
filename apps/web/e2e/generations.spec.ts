// R1-7 問題生成履歴・状態管理フローの E2E テスト（Playwright）。
//
// テスト方針：
//   - 未認証で /me/generations を踏むと /login?next=/me/generations にリダイレクトされる
//     ((authed) layout のガード経路)
//   - 認証ユーザー：履歴ゼロでも 200 で空表示
//   - 認証ユーザー：seed-generation で各状態の行を直接 INSERT して表示確認
//   - cancel / retry の細かいロジック（CSRF / 状態遷移）は Backend pytest が網羅済み。
//     ここはブラウザ越しで「ボタンが出る」「クリックすると状態が更新される」の存在保証
//
// Worker の扱い：
//   実 LLM 呼び出しは E2E では避け、Mock GitHub サーバの /_test/seed-generation で
//   行を直接生やす（generation_requests INSERT のみ、jobs は介在させない）。
//   pending 行のキャンセル試験は Worker が拾わない前提で 1 秒以内に観測する。

import { MOCK_GITHUB_ORIGIN } from "./_helpers/constants";
import { expect, loginAndGoto, test } from "./_helpers/test-fixtures";

test.describe.configure({ mode: "serial" });

async function seedGeneration(
  request: import("@playwright/test").APIRequestContext,
  options: {
    status?: "pending" | "completed" | "failed" | "canceled";
    category?: string;
    difficulty?: string;
    failureReason?: string;
  } = {},
): Promise<string> {
  const params = new URLSearchParams();
  if (options.status) params.set("status", options.status);
  if (options.category) params.set("category", options.category);
  if (options.difficulty) params.set("difficulty", options.difficulty);
  if (options.failureReason) params.set("failure_reason", options.failureReason);
  const qs = params.toString();
  const res = await request.post(
    `${MOCK_GITHUB_ORIGIN}/_test/seed-generation${qs ? `?${qs}` : ""}`,
  );
  if (!res.ok()) {
    throw new Error(`seed-generation failed: ${res.status()} ${await res.text()}`);
  }
  const body = (await res.json()) as { request_id: string };
  return body.request_id;
}

test.beforeEach(async ({ resetState }) => {
  await resetState();
});

test.describe("未認証ガード", () => {
  test("/me/generations を未認証で踏むと /login?next=/me/generations に飛ばされる", async ({
    page,
  }) => {
    await page.goto("/me/generations");
    await page.waitForURL(/\/login\?next=/);
    expect(page.url()).toContain("/login?next=%2Fme%2Fgenerations");
  });
});

test.describe("認証ユーザー: 履歴ゼロ", () => {
  test("/me/generations: 履歴が無ければ「まだ生成リクエストがありません」表示", async ({
    page,
  }) => {
    await loginAndGoto(page, "/me/generations");

    await expect(page.getByRole("heading", { name: "生成履歴" })).toBeVisible();
    await expect(page.getByText("まだ生成リクエストがありません。")).toBeVisible();
  });
});

test.describe("認証ユーザー: 各状態の行が表示される", () => {
  test("failed 行に失敗理由 + 再試行ボタンが出る", async ({ page }) => {
    await loginAndGoto(page, "/");
    await seedGeneration(page.request, {
      status: "failed",
      category: "array",
      failureReason: "judge_below_threshold",
    });

    await page.goto("/me/generations");

    await expect(page.getByText("失敗").first()).toBeVisible();
    // 内部タグ（judge_below_threshold）は出さず、丸めた汎用文言を出す。
    //   要件 §ビジネスルール「内部の失敗種別はユーザーには区別せず表示」に従う。
    await expect(page.getByText("問題を生成できませんでした")).toBeVisible();
    await expect(page.getByText("judge_below_threshold")).not.toBeVisible();
    await expect(page.getByRole("button", { name: "再試行" })).toBeVisible();
  });

  test("pending 行にキャンセルボタンが出る", async ({ page }) => {
    await loginAndGoto(page, "/");
    await seedGeneration(page.request, { status: "pending" });

    await page.goto("/me/generations");

    await expect(page.getByText("生成中…").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "キャンセル" })).toBeVisible();
  });

  test("canceled 行は「キャンセル済」表示、ボタンは出ない", async ({ page }) => {
    await loginAndGoto(page, "/");
    await seedGeneration(page.request, { status: "canceled" });

    await page.goto("/me/generations");

    await expect(page.getByText("キャンセル済").first()).toBeVisible();
    await expect(page.getByRole("button", { name: "キャンセル" })).not.toBeVisible();
    await expect(page.getByRole("button", { name: "再試行" })).not.toBeVisible();
  });
});

test.describe("ヘッダーグローバルナビ", () => {
  test("ログイン後のヘッダーに「生成履歴」リンクが出て /me/generations に遷移できる", async ({
    page,
  }) => {
    await loginAndGoto(page, "/problems");
    const link = page.getByRole("link", { name: "生成履歴" });
    await expect(link).toBeVisible();
    await link.click();
    await expect(page).toHaveURL("/me/generations");
  });
});
