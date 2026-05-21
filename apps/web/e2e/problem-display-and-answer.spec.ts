// R1-4 / R1-5 / R1-6 問題表示・解答入力フローの E2E テスト（Playwright）。
//
// テスト方針（problem-display-and-answer.md / grading.md）：
//   - 未ログイン：/problems / /problems/:id どちらも /login?next=... に
//     server-side redirect される（R1-6 で認証必須化）
//   - 認証ユーザー：/problems 一覧 → /problems/:id 詳細遷移
//   - 認証ユーザー：「実行」ボタン → POST /api/submissions が受け付けられ、
//     GradingResult が mount されて「採点中」表示まで遷移する
//   - フィルタ：URL クエリと <select> の双方向同期
//
//   細かい入力検証 / フックの分岐は Vitest 側（problems-filter-form / answer-workspace /
//   grading-result / use-get-submission）で網羅済み。ここはブラウザを跨いだ「触れる」
//   「叩ける」「進む」の存在保証に絞る。
//
// Worker をどう扱うか：
//   POST /api/submissions は同 tx で jobs に grading ジョブを積む（R1-5）。
//   採点完了（pending → graded）まで観測するには Worker + Docker sandbox を
//   playwright.config.ts に追加で起動する必要がある（Docker daemon 依存・ビルド時間で
//   E2E ランタイムが膨らむ）。本 spec は「採点中」(pending) 表示まで確認し、
//   graded 遷移は Worker 側 Go test (orchestrator_integration_test.go) で別途担保する。

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

test.describe("未ログインガード", () => {
  test("未ログインで /problems を踏むと /login?next=/problems に server-side redirect される", async ({
    page,
  }) => {
    // /problems 自体が認証必須（R1-6 で変更）。フィルタやページ番号も next に
    // 保持される実装だが、本テストはクエリ無しで挙動の存在保証だけ取る。
    await page.goto("/problems");

    await expect(page).toHaveURL(/\/login\?next=/);
    expect(page.url()).toContain("/login?next=%2Fproblems");
  });

  test("未ログインで /problems?category=array を踏むとフィルタが next に保持される", async ({
    page,
  }) => {
    // /problems はカテゴリ別アコーディオン化に伴いページネーションを撤去したため、
    //   保持対象は category / difficulty のフィルタのみ（page は型ごと削除済み）。
    await page.goto("/problems?category=array");

    await expect(page).toHaveURL(/\/login\?next=/);
    expect(page.url()).toContain(`/login?next=${encodeURIComponent("/problems?category=array")}`);
  });

  test("未ログインで /problems/:id を踏むと /login?next=/problems/:id に server-side redirect される", async ({
    page,
  }) => {
    const problemId = await seedProblem(page.request);

    await page.goto(`/problems/${problemId}`);

    await expect(page).toHaveURL(/\/login\?next=/);
    expect(page.url()).toContain(`/login?next=${encodeURIComponent(`/problems/${problemId}`)}`);
  });
});

test.describe("認証ユーザー：解答送信", () => {
  test("ログイン後に /problems → 詳細 → 「実行」で採点中表示になる (R1-5)", async ({ page }) => {
    const problemId = await seedProblem(page.request, {
      title: "E2E 配列の合計",
      category: "array",
      difficulty: "easy",
    });

    // ログイン → 一覧で seed した問題タイトルが見える → 詳細へ遷移。
    //   "/" は /problems にサーバ side redirect されるため、終端着地は /problems。
    await loginViaMockGithub(page);
    await page.waitForURL("/problems");
    await expect(page.getByRole("heading", { name: "問題一覧" })).toBeVisible();
    const card = page.getByRole("link", { name: /E2E 配列の合計/ });
    await expect(card).toBeVisible();
    await card.click();
    await expect(page).toHaveURL(new RegExp(`/problems/${problemId}$`));

    // 認証 me 完了を待つ：ボタンが enabled になるはず。
    const runButton = page.getByRole("button", { name: "実行" });
    await expect(runButton).toBeEnabled();

    await runButton.click();

    // submit 成功 → GradingResult が mount → 1.5s ポーリングで status='pending' を
    //   観測。本 E2E では Worker を起動しないため pending のまま「採点中」表示が
    //   維持される。Worker による graded 遷移は Go test 側で担保。
    await expect(page.getByText(/採点中/)).toBeVisible();
  });
});

test.describe("localStorage 復元", () => {
  test("エディタに書いた内容はリロード後も復元される", async ({ page }) => {
    const problemId = await seedProblem(page.request);

    // /problems/:id は認証必須化（R1-6）。未ログインだと /login に redirect される
    //   ためエディタが描画されない。ログイン後に詳細ページへ進む。
    //   "/" は /problems にサーバ side redirect されるため、終端着地は /problems。
    await loginViaMockGithub(page);
    await page.waitForURL("/problems");
    await page.goto(`/problems/${problemId}`);

    // CodeMirror 6 の入力面は contenteditable な .cm-content（aria-label の
    //   ラッパ section ではなく内部要素）。focus → 全選択 → 入力で初期テンプレを
    //   置き換える。Playwright の type は contenteditable に対しても動く。
    const editor = page.locator(".cm-content");
    await expect(editor).toBeVisible();
    await editor.click();
    // 全選択 → 上書き入力。CodeMirror は CodeMirror 標準のキーバインドで Ctrl/Cmd+A を解釈する。
    //   plat 差を避けるため、JS で doc を直接 select する代わりにキー入力を 2 段で送る。
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.type("const restored = 42;");

    // localStorage に書かれるのは useEffect の deps に code を入れた直後。
    //   ボタンの押下を介さず、入力が反映されているかを localStorage で直接観測する。
    await expect
      .poll(async () =>
        page.evaluate(
          (id) => window.localStorage.getItem(`ai-coding-drill:answer:${id}`),
          problemId,
        ),
      )
      .toContain("const restored = 42;");

    // リロードして、エディタ内容が復元されることを確認する。
    //   CodeMirror の表示テキストは .cm-content の textContent。
    await page.reload();
    await expect(page.locator(".cm-content")).toContainText("const restored = 42;");
  });
});

test.describe("一覧フィルタ", () => {
  test("?category=array で絞ると array の問題だけが表示される", async ({ page }) => {
    await seedProblem(page.request, { title: "配列の問題A", category: "array" });
    await seedProblem(page.request, { title: "文字列の問題B", category: "string" });

    // /problems は認証必須化（R1-6）。ログイン後にフィルタ URL に直接遷移する。
    //   "/" は /problems にサーバ side redirect されるため、終端着地は /problems。
    await loginViaMockGithub(page);
    await page.waitForURL("/problems");
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
