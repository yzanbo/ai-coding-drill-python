// middleware: 認証必須パスへの未ログインアクセスを `/login?next=...` に倒す
//   共通ガード。Edge Runtime で動くため `next/headers` の cookies() ではなく
//   `req.cookies.has()` を使う。
//
// 設計：
//   - 守る対象は「未ログイン時に /login に飛ばす」画面のみ：
//     /problems / /problems/:id / /problems/new / /problems/generate/:requestId /
//     /me/*。matcher で対象を絞り、ここでさらに正規表現で確認する。
//   - 認証 Cookie の最終有効性は Backend の Depends(get_current_user) が SSoT。
//     ここは presence チェックのみで、失効済み Cookie はガード対象外
//     （遷移先 API が 401 を返してログアウト相当に倒れる）。
//   - `/` / `/login` / not-found の guest-only 系（ログイン済を別画面に飛ばす）は
//     middleware に乗せない。理由は ループ破壊：
//     `/login` を「Cookie あり → /problems」に倒すと、`(authed)` layout の
//     `useGetAuthMe` が 401 を返した時に「/me → /login → /problems → /me → …」
//     のループが起きうるため、`/login` の Cookie→redirect は Server Component
//     側にだけ残し、middleware は「未ログインを /login へ寄せる」一方向の
//     責務だけを持つ。
//   - `(authed)` layout の `useGetAuthMe` ガードは残す。middleware は「Cookie が
//     全く無い」ケースを弾くだけで、「Cookie はあるが Redis セッションが失効」
//     は client 側で API 401 を見て判定する必要がある（layout の責務）。
//
// 関連：
//   - docs/requirements/3-cross-cutting/03-page-routing.md §2
//   - Cookie 名 SSoT: src/lib/auth/session-cookie-name.ts（Edge から
//     `next/headers` 依存モジュールを引きずらないよう、Cookie 名だけを
//     独立ファイルに分離している）

import { type NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE_NAME } from "@/lib/auth/session-cookie-name";

// PROTECTED_PATTERNS: 未ログイン時に /login?next=... へ倒す URL パターン。
//   docs/requirements/3-cross-cutting/03-page-routing.md §1 のマトリクスと
//   厳密に揃える。新規認証必須画面を追加する時はこの配列に 1 行足し、同 .md の
//   マトリクスも更新する（2 箇所セットで SSoT を保つ）。
//
//   /problems/new と /problems/generate/:id は /^\/problems\/[^/]+$/ にも
//   マッチするが、いずれも PROTECTED なのでマッチ順序は不問（.some で OR）。
const PROTECTED_PATTERNS: RegExp[] = [
  /^\/problems$/,
  /^\/problems\/new$/,
  /^\/problems\/generate\/[^/]+$/,
  /^\/problems\/[^/]+$/,
  /^\/me(\/|$)/,
];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // PROTECTED 対象外は何もせず通す。matcher で大半は弾いているが、
  //   matcher は単純な glob で除外しきれない部分があり、ここで最終判定する。
  if (!PROTECTED_PATTERNS.some((re) => re.test(pathname))) {
    return NextResponse.next();
  }

  // Cookie あり：ログイン済とみなして通す。最終有効性は遷移先で確認される。
  if (req.cookies.has(SESSION_COOKIE_NAME)) {
    return NextResponse.next();
  }

  // 未ログイン：?next= に現在 URL（クエリ含む）を載せて /login へ。
  //   searchParams.set 経由でセットすることで、非 ASCII / 半角空白 / `+` 等の
  //   特殊文字を URLSearchParams が正規にエンコードする（手動 encodeURIComponent
  //   + 文字列連結だと二重エンコード差異が出やすい）。
  const loginUrl = new URL("/login", req.url);
  loginUrl.searchParams.set("next", pathname + req.nextUrl.search);
  return NextResponse.redirect(loginUrl);
}

// config.matcher: middleware を発火させる URL を Next.js 側で絞る。
//   - _next/ / api/ / auth/ 配下、/health・/healthz の完全一致、favicon・
//     拡張子付き静的ファイルを除外。除外条件は segment 境界（末尾 / または $）
//     で明示し、/auth-error のような偽陽性除外を避ける。
//   - 残り全てに発火させ、関数内で PROTECTED_PATTERNS を再評価する二段構え
//     にしているのは、matcher の正規表現は分岐や否定が弱く、PROTECTED の
//     SSoT を 1 箇所に集約したいため。
export const config = {
  matcher: ["/((?!_next/|api/|auth/|health$|healthz$|favicon|.*\\..*).*)"],
};
