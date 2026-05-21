// middleware.ts のロジック単体テスト。
//
// 何を担保するか：
//   - 未ログインで PROTECTED に該当する URL に来たら /login?next=... に 307 redirect
//   - ?next= には現在 URL（クエリ含む）が encodeURIComponent で乗る
//   - Cookie あり（session_id）のリクエストはそのまま通す（next() を返す）
//   - PROTECTED でないパス（例: /、/login）は何もしないで通す
//
// 仕組み：
//   NextRequest は Web 標準の Request を継承しているため、URL とヘッダー（Cookie 含む）
//   を組み立てて直接 new NextRequest(...) でテストできる。

import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { middleware } from "./middleware";

function buildRequest(url: string, cookie?: string): NextRequest {
  const headers = new Headers();
  if (cookie) headers.set("cookie", cookie);
  return new NextRequest(new URL(url, "http://localhost:3000"), { headers });
}

describe("middleware", () => {
  describe("未ログイン（Cookie 無し）で PROTECTED URL に来た場合", () => {
    it.each([
      ["/problems", "/login?next=%2Fproblems"],
      ["/problems/abc-123", "/login?next=%2Fproblems%2Fabc-123"],
      ["/problems/new", "/login?next=%2Fproblems%2Fnew"],
      ["/problems/generate/req-1", "/login?next=%2Fproblems%2Fgenerate%2Freq-1"],
      ["/me/history", "/login?next=%2Fme%2Fhistory"],
      ["/me/stats", "/login?next=%2Fme%2Fstats"],
    ])("%s → %s に 307 redirect する", (path, expected) => {
      const res = middleware(buildRequest(path));
      expect(res.status).toBe(307);
      const location = res.headers.get("location");
      expect(location).toBeTruthy();
      const locUrl = new URL(location ?? "");
      expect(locUrl.pathname + locUrl.search).toBe(expected);
    });

    it("クエリ付き URL の場合、next にクエリも含めて載せる", () => {
      const res = middleware(buildRequest("/problems?category=array&difficulty=easy"));
      const locUrl = new URL(res.headers.get("location") ?? "");
      expect(locUrl.pathname).toBe("/login");
      expect(locUrl.searchParams.get("next")).toBe("/problems?category=array&difficulty=easy");
    });
  });

  describe("Cookie あり（session_id）で PROTECTED URL に来た場合", () => {
    it("/problems はそのまま通す（リダイレクトしない）", () => {
      const res = middleware(buildRequest("/problems", "session_id=abc"));
      // NextResponse.next() は 200 系で location ヘッダーを持たない。
      expect(res.headers.get("location")).toBeNull();
    });

    it("/me/history はそのまま通す", () => {
      const res = middleware(buildRequest("/me/history", "session_id=abc"));
      expect(res.headers.get("location")).toBeNull();
    });
  });

  describe("PROTECTED 対象外のパス", () => {
    it.each([
      "/",
      "/login",
      "/login?next=%2Fproblems",
      // /problems/abc/def: PROTECTED は :id 1 segment までで、深い path は対象外。
      //   Next.js 側に該当 page が無く 404 になるので middleware は素通りでよい。
      "/problems/abc/def",
    ])("%s は Cookie 無しでも通す", (path) => {
      const res = middleware(buildRequest(path));
      expect(res.headers.get("location")).toBeNull();
    });
  });

  describe("PROTECTED 境界", () => {
    // /me 単独：/^\/me(\/|$)/ にマッチし PROTECTED 扱い。Next.js 側に該当 page
    //   は無く 404 になるが、未ログインで /me 系を踏んだ時は /login に倒した方が
    //   「/me 系は要ログイン」という一貫性が出る。
    it("/me 単独も PROTECTED として /login に redirect する", () => {
      const res = middleware(buildRequest("/me"));
      expect(res.status).toBe(307);
      const locUrl = new URL(res.headers.get("location") ?? "");
      expect(locUrl.pathname).toBe("/login");
      expect(locUrl.searchParams.get("next")).toBe("/me");
    });

    // 非 ASCII / 特殊文字を含む next の安全性：NextRequest が URL を percent-encode
    //   した形のまま req.nextUrl.search に保持し、URLSearchParams.set が next クエリ
    //   値として安全に乗せる。/login 側 safeNextPath で同等の URL として読み戻せる。
    //   日本語は %E6%97%A5%E6%9C%AC%E8%AA%9E に、`+` は `+` のまま（クエリ文字列での
    //   `+` 解釈はパース側依存）に保たれる。
    it("非 ASCII / 特殊文字を含むクエリも next に安全に乗る", () => {
      const res = middleware(buildRequest("/problems?q=日本語&plus=a+b"));
      const locUrl = new URL(res.headers.get("location") ?? "");
      expect(locUrl.searchParams.get("next")).toBe(
        "/problems?q=%E6%97%A5%E6%9C%AC%E8%AA%9E&plus=a+b",
      );
    });
  });
});
