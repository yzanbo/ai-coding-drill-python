// R1-5 採点フロー full E2E（pending → graded、issue #80）。
//
// 既存の problem-display-and-answer.spec.ts は Worker を起動しないため
// 「採点中」表示までしか観測しない。本 spec は playwright.config.ts の webServer に
// 採点 Worker（apps/workers/grading）+ サンドボックス image を追加し、submit → 採点 →
// 結果表示の全経路をブラウザ越しに確認する。
//
// テストケース：
//   - 正解コード（参照解答そのまま）を送信 → 「正解」表示
//   - 不正解コード（常に 0 を返す）を送信 → 「テスト不合格」表示
//
// 採点ロジックは Worker 側で sandbox の vitest 実行結果を見るため、ここはあくまで
// 「ブラウザを跨いだ submit → graded 表示」の存在保証に絞る（個別の failureKind 分岐は
// Vitest grading-result.test.tsx / Go orchestrator_integration_test.go で網羅）。

import { MOCK_GITHUB_ORIGIN } from "./_helpers/constants";
import { expect, loginViaMockGithub, test } from "./_helpers/test-fixtures";

// 直列化：問題行 / submissions を共有 DB に作るためレースを避ける（既存 spec と同方針）。
test.describe.configure({ mode: "serial" });

// seed-problem は test_cases=[{input:"[1,2,3]", expected:"6"}, {input:"[]", expected:"0"}] /
// reference_solution=`export const solve = (a: number[]) => a.reduce((s, n) => s + n, 0);`
// を固定で書き込む（apps/web/e2e/_mock-github/server.py 参照）。
// 採点 Worker は test_cases 配列を vitest harness に展開して sandbox で走らせる。
async function seedProblem(
  request: import("@playwright/test").APIRequestContext,
  title: string,
): Promise<string> {
  const res = await request.post(
    `${MOCK_GITHUB_ORIGIN}/_test/seed-problem?title=${encodeURIComponent(title)}`,
  );
  if (!res.ok()) {
    throw new Error(`seed-problem failed: ${res.status()} ${await res.text()}`);
  }
  const body = (await res.json()) as { problem_id: string };
  return body.problem_id;
}

// エディタに任意コードを書き込む。CodeMirror 6 の .cm-content は contenteditable。
// 全選択 → 上書きで初期テンプレを置き換える（problem-display-and-answer.spec.ts と同方針）。
async function fillEditor(page: import("@playwright/test").Page, code: string): Promise<void> {
  const editor = page.locator(".cm-content");
  await expect(editor).toBeVisible();
  await editor.click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.type(code);
}

test.beforeEach(async ({ resetState }) => {
  await resetState();
});

test.describe("採点 Worker フル E2E（pending → graded）", () => {
  // タイムアウト延長：Worker が claim → sandbox 起動 (docker run) → vitest 実行 → 結果書き戻し
  // → Frontend が 1.5s ポーリングで graded 観測、までの全経路が 1 テスト内で走る。
  // 標準 30s ではコールドスタートの docker pull 等で足りないことがある。
  test.setTimeout(120_000);

  test("正解コードを送信すると「正解」が表示される", async ({ page }) => {
    const problemId = await seedProblem(page.request, "E2E 正解パス");

    await loginViaMockGithub(page);
    await page.waitForURL("/problems");
    await page.goto(`/problems/${problemId}`);

    // 参照解答そのまま。test_cases は [1,2,3]→6 / []→0 の 2 件で両方通過する想定。
    await fillEditor(page, "export const solve = (a) => a.reduce((s, n) => s + n, 0);");

    await page.getByRole("button", { name: "実行" }).click();
    await expect(page.getByText(/採点中/)).toBeVisible();

    // graded への遷移は Worker 経由のため最大 1 分待つ（docker run 起動含む）。
    // ResultCard title="正解" は heading ではないので role 指定ではなく text 検索。
    await expect(page.getByText("正解", { exact: true })).toBeVisible({ timeout: 60_000 });
  });

  test("不正解コードを送信すると「テスト不合格」が表示される", async ({ page }) => {
    const problemId = await seedProblem(page.request, "E2E 不正解パス");

    await loginViaMockGithub(page);
    await page.waitForURL("/problems");
    await page.goto(`/problems/${problemId}`);

    // 常に 0 を返す → [1,2,3]→6 で fail、[]→0 で pass。passed=false / failureKind=test_failed。
    await fillEditor(page, "export const solve = (_a) => 0;");

    await page.getByRole("button", { name: "実行" }).click();
    await expect(page.getByText(/採点中/)).toBeVisible();

    await expect(page.getByText("テスト不合格", { exact: true })).toBeVisible({ timeout: 60_000 });
  });
});
