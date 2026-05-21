// R1-3 問題生成フローの E2E テスト (Playwright)。
//
// テスト方針 (problem-generation.md):
//   - フォーム入力 → /problems/generate/:requestId → 完了で /problems/:problemId に
//     自動遷移する「ブラウザを跨いだ実フロー」の存在保証に絞る
//   - 細かいバリデーションメッセージや状態分岐は Vitest 側 (form / status-view) で網羅済み
//
// Worker をどう扱うか:
//   - R1-3 時点では問題生成 Worker (apps/workers/generation) は skeleton のみで
//     LLM 呼び出しは未実装。実機 Worker に依存すると E2E が flaky / 不可能になる
//   - そのため Mock GitHub サーバ側に test 用 API
//     POST /_test/complete-generation-request/:requestId
//     POST /_test/fail-generation-request/:requestId
//     を追加し、Spec から呼び出して DB を直接 completed / failed に倒す
//   - これで Backend (FastAPI) と Frontend (Next.js) の API 越しの実フローは
//     そのまま動かしつつ、Worker 不在を回避できる

import { MOCK_GITHUB_ORIGIN } from "./_helpers/constants";
import { expect, loginAndGoto, test } from "./_helpers/test-fixtures";

// 本 spec 内のテストを serial（順次）に倒す。並列で走らせると beforeEach の
// resetState が他テストの DB / Redis を消してログイン直後にセッションが
// 飛ぶ race が起きるため。
//
// 注意：playwright.config.ts は fullyParallel: true で、ローカルは
// workers が CPU 数分立つため、本 spec と別ファイル（auth.spec.ts 等）が
// 同時並走すると同じ DB を共有してやはり race が起きる可能性がある。
// CI は workers: 1 で逐次実行なので安全。ローカル並走時の flaky は
// 別ファイル間の DB 共有という構造的な課題で、本 spec 単独では解消できない。
test.describe.configure({ mode: "serial" });

// /problems/generate/<requestId> の URL からリクエスト ID を取り出す。
// 完了押し込み API に渡すために使う。
const REQUEST_ID_PATTERN = /\/problems\/generate\/([0-9a-f-]+)/;

test.beforeEach(async ({ resetState }) => {
  // 各テスト前に DB / Redis を全消去（前テストの user / generation_requests / problems が残ると
  // /problems/:id に意図せず別の問題ページが出来て assert が崩れるため）。
  await resetState();
});

test.describe("問題生成フロー (正常系)", () => {
  test("ログイン → カテゴリ・難易度送信 → 生成ステータス画面 → 完了で問題ページへ遷移", async ({
    page,
  }) => {
    // 1. ログインしてから /problems/new に入る（helper が / 着地待ちまで面倒見る）。
    await loginAndGoto(page, "/problems/new");
    await expect(page.getByRole("heading", { name: "新しい問題を生成する" })).toBeVisible();

    // 2. カテゴリ「配列」と難易度「やさしい」を選んで送信する。
    //    ラジオは label で囲ってあるので、表示文言クリックで選択できる。
    await page.getByText("配列", { exact: true }).click();
    await page.getByText("やさしい", { exact: true }).click();
    await page.getByRole("button", { name: "問題を生成する" }).click();

    // 3. /problems/generate/:requestId に遷移して「生成中…」が見える。
    await page.waitForURL(REQUEST_ID_PATTERN);
    await expect(page.getByText("生成中…")).toBeVisible();

    // 4. URL から requestId を取り出して、Mock 側の test API で completed に押し込む。
    //    押し込み API が返した problem_id が、リダイレクト先 URL と一致するはず。
    //    waitForURL を直前に通しているため match は必ず成立する想定だが、
    //    型上は null 可能なので ?.[1] で取り出し toBeDefined() で明示 assert する。
    const requestId = page.url().match(REQUEST_ID_PATTERN)?.[1];
    expect(requestId).toBeDefined();

    const res = await page.request.post(
      `${MOCK_GITHUB_ORIGIN}/_test/complete-generation-request/${requestId}`,
    );
    expect(res.ok()).toBe(true);
    const body = (await res.json()) as { problem_id: string };
    const problemId = body.problem_id;

    // 5. 次のポーリングで status=completed を取り、router.replace で /problems/:problemId に遷移。
    //    /problems/:problemId 画面は R1-4 で実装予定で現状未配置（404 で OK）。
    //    本テストは「URL がそこに着地する」という FE の遷移ロジック検証に絞る。
    await page.waitForURL(`/problems/${problemId}`);
  });
});

test.describe("問題生成フォームのバリデーション", () => {
  test("カテゴリ・難易度を未選択のまま送信するとエラーメッセージが出て遷移しない", async ({
    page,
  }) => {
    await loginAndGoto(page, "/problems/new");

    // 何も選ばずにいきなり送信する。
    await page.getByRole("button", { name: "問題を生成する" }).click();

    // Zod スキーマで定義したエラー文が両方表示される。
    await expect(page.getByText("カテゴリを指定してください")).toBeVisible();
    await expect(page.getByText("難易度を指定してください")).toBeVisible();

    // URL は /problems/new のまま（遷移していない）。
    await expect(page).toHaveURL(/\/problems\/new$/);
  });
});

test.describe("問題生成 failed 時の再試行", () => {
  test("生成が失敗するとエラー表示 + 「再試行」で新しい /problems/generate/:id に遷移する", async ({
    page,
  }) => {
    await loginAndGoto(page, "/problems/new");

    // フォーム送信までは正常系と同じ。
    await page.getByText("再帰", { exact: true }).click();
    await page.getByText("ふつう", { exact: true }).click();
    await page.getByRole("button", { name: "問題を生成する" }).click();

    await page.waitForURL(REQUEST_ID_PATTERN);
    // waitForURL を直前に通しているため match は必ず成立する想定だが、
    // 型上は null 可能なので ?.[1] で取り出し toBeDefined() で明示 assert する。
    const requestId = page.url().match(REQUEST_ID_PATTERN)?.[1];
    expect(requestId).toBeDefined();

    // Mock 側 test API で failed に倒す。
    const res = await page.request.post(
      `${MOCK_GITHUB_ORIGIN}/_test/fail-generation-request/${requestId}`,
    );
    expect(res.ok()).toBe(true);

    // failed の表示と再試行ボタンが出る。
    await expect(page.getByText("生成に失敗しました")).toBeVisible();
    const retryButton = page.getByRole("button", { name: "再試行" });
    await expect(retryButton).toBeVisible();

    // ボタン押下で新しい generation_request の生成中画面に遷移する
    //   （/problems/generate/<新 id> に replace、旧 id と異なる）。
    //   waitForURL に REQUEST_ID_PATTERN だけ渡すと、まだ replace 前で旧 id の URL
    //   にいる時点で即マッチして抜けてしまい新 id 待ちにならない。コールバック形式で
    //   「pathname がパターンに合致し、かつ旧 id を含まない」まで待つ。
    await retryButton.click();
    await page.waitForURL(
      (url) => REQUEST_ID_PATTERN.test(url.pathname) && !url.pathname.includes(requestId ?? ""),
    );
    const newRequestId = page.url().match(REQUEST_ID_PATTERN)?.[1];
    expect(newRequestId).toBeDefined();
    expect(newRequestId).not.toBe(requestId);
  });
});
