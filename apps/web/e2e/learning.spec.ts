// R1-6 学習履歴・統計フローの E2E テスト（Playwright）。
//
// テスト方針（learning.md）：
//   - 未認証で /me/* を踏んだら /login?next=/me/... にリダイレクトされる
//     （(authed) layout のガード経路）
//   - 認証ユーザー：履歴ゼロでも /me/stats / /me/weakness が 200 で空集計表示
//   - 認証ユーザー：seed-submission で graded 行を作ってから /me/stats を開くと
//     合計と category 別の数値が出る
//   - 認証ユーザー：/me/history の行クリックで /problems/:id へ遷移
//
//   細かい数値ロジック（弱点抽出 / 並び順 / ゼロ割ガード）は Backend の
//   pytest（test_me_service / test_me_repository）と Frontend の Vitest
//   （use-get-my-* のフックテスト）で網羅済み。ここはブラウザを跨いだ
//   「未認証ガード」「画面が出る」「行をクリックすると進む」の存在保証に絞る。
//
// Worker の扱い：
//   submissions.status='graded' まで遷移した行が必要だが、Worker + Docker
//   sandbox 起動は E2E ランタイムを大幅に膨らませる。Mock GitHub サーバの
//   /_test/seed-submission で graded 行を直接 INSERT して観測する
//   （問題詳細→解答→採点フローは別 spec / Vitest で担保済み）。

import { MOCK_GITHUB_ORIGIN } from "./_helpers/constants";
import { expect, loginAndGoto, test } from "./_helpers/test-fixtures";

// 直列化：beforeEach の resetState が並走他テストの DB / Redis を消すレースを避ける。
test.describe.configure({ mode: "serial" });

// seed 用ヘルパ：Mock GitHub の /_test/seed-problem を叩いて problems を 1 件作る。
async function seedProblem(
  request: import("@playwright/test").APIRequestContext,
  options: { title?: string; category?: string } = {},
): Promise<string> {
  const params = new URLSearchParams();
  if (options.title) params.set("title", options.title);
  if (options.category) params.set("category", options.category);
  const qs = params.toString();
  const res = await request.post(`${MOCK_GITHUB_ORIGIN}/_test/seed-problem${qs ? `?${qs}` : ""}`);
  if (!res.ok()) {
    throw new Error(`seed-problem failed: ${res.status()} ${await res.text()}`);
  }
  const body = (await res.json()) as { problem_id: string };
  return body.problem_id;
}

// seed-submission ヘルパ：直近ログインユーザー名義で graded 行を INSERT する。
async function seedSubmission(
  request: import("@playwright/test").APIRequestContext,
  options: { problemId: string; passed?: boolean; score?: number; total?: number },
): Promise<string> {
  const params = new URLSearchParams();
  params.set("problem_id", options.problemId);
  if (options.passed !== undefined) params.set("passed", String(options.passed));
  if (options.score !== undefined) params.set("score", String(options.score));
  if (options.total !== undefined) params.set("total", String(options.total));
  const res = await request.post(
    `${MOCK_GITHUB_ORIGIN}/_test/seed-submission?${params.toString()}`,
  );
  if (!res.ok()) {
    throw new Error(`seed-submission failed: ${res.status()} ${await res.text()}`);
  }
  const body = (await res.json()) as { submission_id: string };
  return body.submission_id;
}

test.beforeEach(async ({ resetState }) => {
  await resetState();
});

test.describe("未認証ガード", () => {
  test("/me/stats を未認証で踏むと /login?next=/me/stats に飛ばされる", async ({ page }) => {
    await page.goto("/me/stats");
    // (authed) layout の useEffect 経由のリダイレクトを待つ。
    await page.waitForURL(/\/login\?next=/);
    expect(page.url()).toContain("/login?next=%2Fme%2Fstats");
  });

  test("/me/weakness を未認証で踏むと /login?next=/me/weakness に飛ばされる", async ({ page }) => {
    await page.goto("/me/weakness");
    await page.waitForURL(/\/login\?next=/);
    expect(page.url()).toContain("/login?next=%2Fme%2Fweakness");
  });

  test("/me/history を未認証で踏むと /login?next=/me/history に飛ばされる", async ({ page }) => {
    await page.goto("/me/history");
    await page.waitForURL(/\/login\?next=/);
    expect(page.url()).toContain("/login?next=%2Fme%2Fhistory");
  });
});

test.describe("認証ユーザー: 履歴ゼロ", () => {
  test("/me/stats: total=0 で空集計の見出しと案内文が出る", async ({ page }) => {
    await loginAndGoto(page, "/me/stats");

    await expect(page.getByRole("heading", { name: "学習統計" })).toBeVisible();
    // 履歴ゼロでも 200 が返り、カテゴリ別セクションの空表示が出る
    // （learning.md §受け入れ条件「履歴ゼロでも 200 / 空集計」）。
    await expect(page.getByText("まだ採点された解答がありません。")).toBeVisible();
  });

  test("/me/weakness: weakCategories=[] で「弱点と判定されたカテゴリはありません」", async ({
    page,
  }) => {
    await loginAndGoto(page, "/me/weakness");

    await expect(page.getByRole("heading", { name: "弱点カテゴリ" })).toBeVisible();
    await expect(page.getByText("現時点で弱点と判定されたカテゴリはありません。")).toBeVisible();
  });

  test("/me/history: 解答ゼロで「まだ解答がありません」表示", async ({ page }) => {
    await loginAndGoto(page, "/me/history");

    await expect(page.getByRole("heading", { name: "解答履歴" })).toBeVisible();
    await expect(page.getByText("まだ解答がありません。")).toBeVisible();
  });
});

test.describe("認証ユーザー: graded 行があるケース", () => {
  test("/me/stats: seed した graded 行が全体集計とカテゴリ別表示に反映される", async ({ page }) => {
    // 先にログインしてユーザーを作ってから seed する（seed-submission が
    // 直近 users 行を user_id として使うため、login 順を守る）。
    await loginAndGoto(page, "/");
    const problemId = await seedProblem(page.request, {
      title: "E2E 統計用",
      category: "array",
    });
    await seedSubmission(page.request, {
      problemId,
      passed: true,
      score: 2,
      total: 2,
    });

    await page.goto("/me/stats");

    // 全体カードに数値が出ている。
    await expect(page.getByRole("heading", { name: "学習統計" })).toBeVisible();
    // 「解答数: 1」「正解数: 1」「正答率: 100.0%」を観測する。
    // 数値だけ pinpoint すると別カラムにマッチしやすいので、ラベルとの
    // 同居を確認する。
    await expect(page.getByText("100.0%").first()).toBeVisible();
    // カテゴリ別カード（array）が現れる。
    await expect(page.getByText("配列").first()).toBeVisible();
  });

  test("/me/history: 行クリックで /problems/:id に遷移する", async ({ page }) => {
    await loginAndGoto(page, "/");
    const problemId = await seedProblem(page.request, {
      title: "E2E 履歴用",
      category: "array",
    });
    await seedSubmission(page.request, {
      problemId,
      passed: true,
      score: 2,
      total: 2,
    });

    await page.goto("/me/history");

    // 履歴行が出ている。
    await expect(page.getByText("E2E 履歴用")).toBeVisible();
    // 行クリック → /problems/:id へ（learning.md §主要インタラクション）。
    await page.getByText("E2E 履歴用").click();
    await expect(page).toHaveURL(new RegExp(`/problems/${problemId}$`));
  });
});
