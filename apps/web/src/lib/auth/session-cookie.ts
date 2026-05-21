// session-cookie: presence チェックヘルパの置き場所。
//   Cookie 名そのもの（SESSION_COOKIE_NAME）は ./session-cookie-name に分離
//   している。理由は Edge Runtime（src/middleware.ts）から Cookie 名だけを
//   import したい時、本ファイルは `next/headers` を使う server-only モジュール
//   なので Edge から直接 import できないため。
//
//   ここは「Cookie が存在するか」の presence チェック専用。Cookie 有効性の
//   最終判定は Backend の Depends(get_current_user) が SSoT。

import { cookies } from "next/headers";

import { SESSION_COOKIE_NAME } from "./session-cookie-name";

// hasSessionCookie: 現リクエストに session_id Cookie が含まれているかを返す。
//   Server Component の認証ガードで「presence 確認 → redirect」を書く時の入口。
//   /problems / /problems/:id / /me/* など「未ログインなら /login へ」の
//   定型ガードは middleware.ts に集約しているため、本ヘルパを呼ぶのは
//   ログイン済ユーザーを別画面に飛ばす guest-only 系（/ / /login / not-found）
//   のみで残っている。
//   失効済み Cookie が残っているケースは弾けない（Redis セッションストアに問い合わせない
//   軽量ガードのため）。失効分は Backend が 401 と同時に Cookie を物理削除
//   （app/main.py の exception handler）するので、次のリクエストでは
//   Cookie 無し扱いになって本ヘルパは false を返す。
export const hasSessionCookie = async (): Promise<boolean> => {
  return (await cookies()).has(SESSION_COOKIE_NAME);
};
