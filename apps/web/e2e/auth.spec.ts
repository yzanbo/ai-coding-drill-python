// R1-1 GitHub OAuth ログインの E2E テスト (Playwright)。
//
// テスト方針 (authentication.md §受け入れ条件):
//   - 受け入れ条件 18 件すべてを E2E で再検証するのは過剰 (CSRF / Cookie 属性 / state 1 回使い切り
//     等は BE 117 件 / FE 64 件のユニット + 結合テストで網羅済み)
//   - E2E は「ブラウザを跨いだ実フロー」の存在保証に絞る:
//     正常系ログイン / ログアウト / 認証後の /login 再訪 / next= の外部 URL 拒否 /
//     Cancel フロー / 同一 GitHub アカウントでの再ログイン (user 一意性)
//
// 前提:
//   - Backend / Mock GitHub / Web は playwright.config.ts の webServer で並行起動
//   - 各 test は beforeEach で /_test/reset を叩いて DB / Redis をクリーン化
//   - Mock の挙動切替は e2e/_helpers/test-fixtures.ts の loginViaMockGithub を経由

import { expect, loginViaMockGithub, logoutViaApi, test } from "./_helpers/test-fixtures";

test.beforeEach(async ({ resetState }) => {
  // 各テスト前に DB users / auth_providers TRUNCATE + Redis FLUSHDB。
  // 前テストの session が残ると「ログイン済みなら /login → /」のような分岐で結果が変わる。
  await resetState();
});

test.describe("/login 画面", () => {
  test("未認証時: 「GitHub でログイン」ボタンが表示される", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("link", { name: "GitHub でログイン" })).toBeVisible();
  });
});

test.describe("ログインフロー (正常系)", () => {
  test("ボタン押下 → mock GitHub → callback → /auth/me 200 で /problems へ", async ({ page }) => {
    // mock GitHub に直接遷移 (Backend が /auth/github → mock authorize に 302)。
    await loginViaMockGithub(page);

    // callback 処理後、Backend は "/" に redirect するが、`/` がサーバ side で
    // /problems に再 redirect するため、ブラウザの最終 URL は /problems になる。
    await expect(page).toHaveURL("/problems");

    // セッション Cookie が払い出され /auth/me が 200 を返す。
    const me = await page.request.get("/auth/me");
    expect(me.status()).toBe(200);
    const body = await me.json();
    // mock の既定 user (login = "e2e-testuser", name = "E2E Test User")。
    // authentication.md §2.1 の displayName 決定ルール: name → login の順、name 在なら name。
    expect(body.displayName).toBe("E2E Test User");
  });
});

test.describe("ログアウトフロー", () => {
  test("ログイン後にログアウトすると /auth/me が 401 を返す", async ({ page }) => {
    await loginViaMockGithub(page);
    await expect(page).toHaveURL("/problems");

    // /auth/logout は POST + CSRF 必須 (double submit cookie)。
    // ブラウザ経由でヘッダーのログアウトボタンを押す方が UX 通りだが、
    // 本テストは「セッション破棄」の存在保証に絞る。CSRF token 取り出しは helper に集約。
    expect(await logoutViaApi(page)).toBe(204);

    // ログアウト後の /auth/me は 401。
    const meAfter = await page.request.get("/auth/me");
    expect(meAfter.status()).toBe(401);
  });
});

test.describe("(authed) ルートグループのガード", () => {
  test("未認証で /problems/new に直アクセスすると /login?next=/problems/new に遷移する", async ({
    page,
  }) => {
    // (authed)/layout.tsx の useEffect が router.replace("/login?next=...") を呼ぶ。
    // FE 側の早期リダイレクトの存在保証 (API の 401 が最終 SSoT、ここは UX 用)。
    await page.goto("/problems/new");

    // next クエリに元 path が encodeURIComponent 済みで載る。
    // 末尾 $ は意図的: ガードが付ける URL の形を契約として固定し、余計なクエリの混入に気付けるようにする。
    // /login 画面そのものの描画確認は `/login 画面` describe が担うので、ここでは行わない (責務分離)。
    await expect(page).toHaveURL(/\/login\?next=%2Fproblems%2Fnew$/);

    // セッションは未確立。
    const me = await page.request.get("/auth/me");
    expect(me.status()).toBe(401);
  });
});

test.describe("認証済みユーザーの /login 再訪", () => {
  test("ログイン済みで /login を開くと /problems にリダイレクト", async ({ page }) => {
    await loginViaMockGithub(page);
    await expect(page).toHaveURL("/problems");

    // /login にアクセスすると useEffect で router.replace("/") が走る。
    // `/` 側でサーバ side redirect が走り、最終的に /problems に着地する。
    await page.goto("/login");
    await expect(page).toHaveURL("/problems");
  });
});

test.describe("next= パラメータの外部 URL 拒否", () => {
  test("/login?next=https://evil.com でログインしても /problems に遷移する", async ({ page }) => {
    // /login に next= を付けて訪問 (未認証なのでログイン画面が表示される)。
    await page.goto("/login?next=https%3A%2F%2Fevil.com");
    await expect(page.getByRole("link", { name: "GitHub でログイン" })).toBeVisible();

    // ログイン完走後、外部 URL は弾かれて "/" → /problems に遷移しているはず。
    await loginViaMockGithub(page);
    await expect(page).toHaveURL("/problems");
  });

  test("/login?next=<2048 文字超> でログインしても /problems に遷移する", async ({ page }) => {
    // authentication.md §2.5: 異常に長い next URL は拒否してホームへフォールバックする
    // (ストレージ・ログ汚染やヘッダ肥大化への防御)。最終的に "/" → /problems に着地する。
    // "/a" の繰り返しで 2050 文字を作る (2048 文字超条件を確実に踏む)。
    const longPath = `/${"a".repeat(2049)}`;
    expect(longPath.length).toBeGreaterThan(2048);
    await page.goto(`/login?next=${encodeURIComponent(longPath)}`);
    await expect(page.getByRole("link", { name: "GitHub でログイン" })).toBeVisible();

    await loginViaMockGithub(page);
    await expect(page).toHaveURL("/problems");
  });
});

test.describe("Cancel フロー", () => {
  test("GitHub 認可画面で Cancel すると /login へ戻り /auth/me 401", async ({ page }) => {
    // mock の /authorize に ?_mode=cancel を渡して error=access_denied を返させる。
    await loginViaMockGithub(page, { mode: "cancel" });

    // Backend の callback handler は error= を受けて /login?auth_error=oauth_failed に 302 する。
    // Frontend がトーストを出す挙動は frontend ユニットで検証済みなので、
    // E2E では URL 着地点だけ確認する (toaster 描画タイミングは flaky になりやすい)。
    await expect(page).toHaveURL(/\/login(\?|$)/);
    // ?auth_error= が URL に含まれる (Frontend は読み取り後に URL から削るので、
    // テスト中の race で消えている可能性もあるため URL 全体ではなく page 状態でアサート)。
    const me = await page.request.get("/auth/me");
    expect(me.status()).toBe(401);
  });
});

test.describe("同一 GitHub アカウントの再ログイン (user 一意性)", () => {
  test("同じ mock user で 2 回ログインしても /auth/me の user_id は 1 回目と同一", async ({
    page,
  }) => {
    // 1 回目
    await loginViaMockGithub(page);
    const me1 = await page.request.get("/auth/me");
    expect(me1.status()).toBe(200);
    const body1 = await me1.json();
    const firstUserId = body1.id;
    expect(firstUserId).toBeTruthy();

    // ログアウト (CSRF token を Cookie から取り出して POST)
    await logoutViaApi(page);

    // 2 回目: 同じ mock user (同じ GitHub id) で再ログイン。
    await loginViaMockGithub(page);
    const me2 = await page.request.get("/auth/me");
    expect(me2.status()).toBe(200);
    const body2 = await me2.json();

    // user id は重複作成されず初回と同一であるべき (authentication.md §受け入れ条件 (3))。
    expect(body2.id).toBe(firstUserId);
  });
});
