// R1-4 問題表示・解答入力フローの E2E テスト（Playwright）。
//
// テスト方針（problem-display-and-answer.md）：
//   - ゲスト：問題一覧 / 問題詳細を 401 なく閲覧できることを保証
//   - ゲスト：「実行」ボタン → /login?next=/problems/:id へのリダイレクト
//   - 認証ユーザー：「実行」ボタン → POST /api/submissions が受け付けられ、
//     submissionId のフィードバックが表示される（採点結果ポーリングは R1-5）
//   - フィルタ：URL クエリと <select> の双方向同期
//
//   細かい入力検証 / フックの分岐は Vitest 側（problems-filter-form / answer-workspace）で
//   網羅済み。ここはブラウザを跨いだ「触れる」「叩ける」「進む」の存在保証に絞る。
//
// Worker をどう扱うか：
//   POST /api/submissions 自身は R1-4 で実装済（status='pending' で 202 を返すだけ）。
//   採点フロー（pending → graded）は R1-5 のスコープなので、本 spec では検証しない。

import { MOCK_GITHUB_ORIGIN } from "./_helpers/constants";
import { expect, loginViaMockGithub, test } from "./_helpers/test-fixtures";

// 直列化：beforeEach の resetState が並走他テストの DB / Redis を消すレースを避ける。
test.describe.configure({ mode: "serial" });

// seed 用ヘルパ：Mock GitHub の /_test/seed-problem を叩いて problems に 1 行 INSERT。
//   戻り値 problem_id を以後の URL 組み立てに使う。
async function seedProblem(
  request: import("@playwright/test").APIRequestContext,
  options: { title?: string; category?: string; difficulty?: string } = {},
): Promise<string> {
  const params = new URLSearchParams();
  if (options.title) params.set("title", options.title);
  if (options.category) params.set("category", options.category);
  if (options.difficulty) params.set("difficulty", options.difficulty);
  const qs = params.toString();
  const res = await request.post(`${MOCK_GITHUB_ORIGIN}/_test/seed-problem${qs ? `?${qs}` : ""}`);
  if (!res.ok()) {
    throw new Error(`seed-problem failed: ${res.status()} ${await res.text()}`);
  }
  const body = (await res.json()) as { problem_id: string };
  return body.problem_id;
}

test.beforeEach(async ({ resetState }) => {
  await resetState();
});

test.describe("ゲスト閲覧", () => {
  test("ゲストでも /problems が 200 で開き、シードした問題が一覧に出る", async ({ page }) => {
    const problemId = await seedProblem(page.request, {
      title: "E2E 配列の合計",
      category: "array",
      difficulty: "easy",
    });

    // ゲストのまま /problems を直接踏む（loginせず）。
    await page.goto("/problems");

    await expect(page.getByRole("heading", { name: "問題一覧" })).toBeVisible();
    // タイトルがカードとして見える。クリックで詳細に進める。
    const card = page.getByRole("link", { name: /E2E 配列の合計/ });
    await expect(card).toBeVisible();
    await card.click();
    await expect(page).toHaveURL(new RegExp(`/problems/${problemId}$`));
  });

  test("ゲストでも /problems/:id が 200 で開き、コードエディタが表示される", async ({ page }) => {
    const problemId = await seedProblem(page.request);

    await page.goto(`/problems/${problemId}`);

    // 問題本文セクションと解答エディタが両方ある。
    await expect(page.getByRole("heading", { name: /E2E 配列の合計/ })).toBeVisible();
    await expect(page.getByLabel("解答コードエディタ")).toBeVisible();
    // 実行ボタンも表示される（ゲストでも押せる UI、押下時に login へ飛ばす設計）。
    await expect(page.getByRole("button", { name: "実行" })).toBeVisible();
  });

  test("ゲストが「実行」を押すと /login?next=/problems/:id にリダイレクトされる", async ({
    page,
  }) => {
    const problemId = await seedProblem(page.request);
    await page.goto(`/problems/${problemId}`);

    await page.getByRole("button", { name: "実行" }).click();

    // クエリ含む URL（next エンコード済み）を一致確認。
    //   /login?next=%2Fproblems%2F<uuid> を末尾一致で検証する。
    //   URL.pathname + URL.search で組み立ててから endsWith する方が
    //   regex の二重エスケープ事故を起こさない。
    const expectedSuffix = `/login?next=${encodeURIComponent(`/problems/${problemId}`)}`;
    await expect.poll(() => page.url().endsWith(expectedSuffix)).toBe(true);
  });
});

test.describe("認証ユーザー：解答送信", () => {
  test("ログイン後に「実行」を押すと submissionId が表示される（採点結果は R1-5）", async ({
    page,
  }) => {
    const problemId = await seedProblem(page.request);

    // ログイン → 詳細ページ。
    await loginViaMockGithub(page);
    await page.waitForURL("/");
    await page.goto(`/problems/${problemId}`);

    // 認証 me 完了を待つ：ボタンが enabled になるはず。
    const runButton = page.getByRole("button", { name: "実行" });
    await expect(runButton).toBeEnabled();

    await runButton.click();

    // 受付メッセージ（submissionId は UUID なので部分一致で検出）。
    await expect(page.getByText(/submissionId:/)).toBeVisible();
    // R1-5 で実装予定であることを明示するメッセージも一緒に出る。
    await expect(page.getByText(/R1-5 で実装予定/)).toBeVisible();
  });
});

test.describe("一覧フィルタ", () => {
  test("?category=array で絞ると array の問題だけが表示される", async ({ page }) => {
    await seedProblem(page.request, { title: "配列の問題A", category: "array" });
    await seedProblem(page.request, { title: "文字列の問題B", category: "string" });

    await page.goto("/problems?category=array");

    await expect(page.getByText("配列の問題A")).toBeVisible();
    await expect(page.getByText("文字列の問題B")).not.toBeVisible();

    // フィルタクリアで両方見える状態に戻る。
    await page.getByRole("button", { name: "フィルタをクリア" }).click();
    await expect(page).toHaveURL(/\/problems$/);
    await expect(page.getByText("配列の問題A")).toBeVisible();
    await expect(page.getByText("文字列の問題B")).toBeVisible();
  });
});
