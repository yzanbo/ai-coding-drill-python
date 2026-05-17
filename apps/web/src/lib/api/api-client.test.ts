// biome-ignore-all lint/suspicious/noDocumentCookie: テストの前提条件として
//   CSRF Cookie の状態を直接組み立てる必要があるため document.cookie への
//   直接代入を許可する。プロダクトコード側（api-client.ts）は読み取り専用。
// configureApiClient の単体テスト。
//   - 状態変更系（POST/PUT/PATCH/DELETE）の時だけ X-CSRF-Token を付与
//   - GET 等の安全メソッドには付けない
//   - csrf_token Cookie が無ければヘッダーは付かない
//
//   テスト対象は Hey API クライアント（生成物）に被せた request interceptor。
//   実際の fetch は MSW で横取りして送信ヘッダーを検証する。
//
//   注意: configureApiClient() は src/test/render-with-query.tsx で 1 度だけ
//   呼ばれている（idempotent）。本テストでは追加の初期化は不要。
import { HttpResponse, http } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { getMeAuthMeGet, logoutAuthLogoutPost } from "@/__generated__/api/sdk.gen";

import { API_BASE, server } from "../../test/msw-server";

const clearCookies = () => {
  // jsdom の document.cookie は append 形式なので、各 cookie を expires=過去 で
  //   個別に上書きすることで消す。
  for (const part of document.cookie.split(";")) {
    const name = part.split("=")[0]?.trim();
    if (name) document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
  }
};

describe("configureApiClient: CSRF ヘッダー注入", () => {
  beforeEach(() => clearCookies());
  afterEach(() => clearCookies());

  it("POST 時に csrf_token Cookie の値を X-CSRF-Token ヘッダーに乗せる", async () => {
    document.cookie = "csrf_token=test-csrf-value; path=/";
    let captured: string | null = null;
    server.use(
      http.post(`${API_BASE}/auth/logout`, ({ request }) => {
        captured = request.headers.get("x-csrf-token");
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await logoutAuthLogoutPost();

    expect(captured).toBe("test-csrf-value");
  });

  it("GET には X-CSRF-Token を付けない（GET は副作用なし扱い）", async () => {
    document.cookie = "csrf_token=should-not-leak; path=/";
    let captured: string | null = "unset";
    server.use(
      http.get(`${API_BASE}/auth/me`, ({ request }) => {
        captured = request.headers.get("x-csrf-token");
        return HttpResponse.json({ id: "u1", displayName: "u", email: null });
      }),
    );

    await getMeAuthMeGet();

    expect(captured).toBeNull();
  });

  it("csrf_token Cookie が無ければ POST でもヘッダーを付けない", async () => {
    let captured: string | null = "unset";
    server.use(
      http.post(`${API_BASE}/auth/logout`, ({ request }) => {
        captured = request.headers.get("x-csrf-token");
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await logoutAuthLogoutPost();

    expect(captured).toBeNull();
  });

  it("URL エンコードされた Cookie 値はデコードされて送られる", async () => {
    // CSRF Cookie が万一 URL エンコードで保存されていてもデコードして元の値を
    //   ヘッダーに乗せる、という readCookie の defensive 挙動を検証する。
    //   ヘッダー値は ASCII 制約があるため、ASCII の URL-special 文字（+ /）で
    //   テストする（本番の csrf_token は base64url で常に ASCII）。
    document.cookie = `csrf_token=${encodeURIComponent("a+b/c")}; path=/`;
    let captured: string | null = null;
    server.use(
      http.post(`${API_BASE}/auth/logout`, ({ request }) => {
        captured = request.headers.get("x-csrf-token");
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await logoutAuthLogoutPost();

    expect(captured).toBe("a+b/c");
  });

  it("不正な URL エンコード（decodeURIComponent が URIError）の Cookie はヘッダーを付けない", async () => {
    // 末尾 % は不正なエスケープ列。readCookie の try/catch が握り潰して
    //   undefined を返し、interceptor もヘッダーを付けない。
    document.cookie = "csrf_token=broken%E0; path=/";
    let captured: string | null = "unset";
    server.use(
      http.post(`${API_BASE}/auth/logout`, ({ request }) => {
        captured = request.headers.get("x-csrf-token");
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await logoutAuthLogoutPost();

    expect(captured).toBeNull();
  });
});
