// session-cookie: セッション Cookie 名 + presence チェックの SSoT。
//   Backend の apps/api/app/core/config.py の session_cookie_name と一致させる。
//   Cookie 名と判定ロジックを 1 箇所に集約しておくことで、
//   Cookie 名が変わった時 / 判定方法を変えたい時に grep 漏れが起きないようにする。
//
//   ここは「Cookie が存在するか」の presence チェック専用。Cookie 有効性の
//   最終判定は Backend の Depends(get_current_user) が SSoT。

import { cookies } from "next/headers";

// SESSION_COOKIE_NAME: 認証 Cookie 名。
//   middleware.ts（Edge Runtime）からも参照するため export する。Edge Runtime
//   では `next/headers` の cookies() を使えないので、middleware は名前だけ
//   受け取って `req.cookies.has(name)` を呼ぶ。
export const SESSION_COOKIE_NAME = "session_id";

// hasSessionCookie: 現リクエストに session_id Cookie が含まれているかを返す。
//   Server Component の認証ガードで「presence 確認 → redirect」を書く時の入口。
//   /problems / /problems/:id / /me/* など「未ログインなら /login へ」の
//   定型ガードは middleware.ts に集約しているため、本ヘルパを呼ぶのは
//   ログイン済ユーザーを別画面に飛ばす guest-only 系（/ / /login / not-found）
//   のみで残っている。
//   失効済み Cookie が残っているケースは弾けない（Redis セッションストアに問い合わせない
//   軽量ガードのため）。失効分は遷移先 API が 401 を返してログアウト相当に倒れる。
export const hasSessionCookie = async (): Promise<boolean> => {
  return (await cookies()).has(SESSION_COOKIE_NAME);
};
