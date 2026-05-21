// session-cookie: セッション Cookie 名 + presence チェックの SSoT。
//   Backend の apps/api/app/core/config.py の session_cookie_name と一致させる。
//   Server Component の認証ガード（/ / /login / /problems / /problems/:id /
//   not-found）の Cookie 名と判定ロジックを 1 箇所に集約しておくことで、
//   Cookie 名が変わった時 / 判定方法を変えたい時に grep 漏れが起きないようにする。
//
//   ここは「Cookie が存在するか」の presence チェック専用。Cookie 有効性の
//   最終判定は Backend の Depends(get_current_user) が SSoT。

import { cookies } from "next/headers";

// SESSION_COOKIE_NAME はモジュール内で hasSessionCookie のみが使う想定で
// export していない。Cookie 名を直接知りたい呼び出し元は将来出てきた段階で
// export に切り替える（YAGNI）。
const SESSION_COOKIE_NAME = "session_id";

// hasSessionCookie: 現リクエストに session_id Cookie が含まれているかを返す。
//   Server Component の認証ガードで「presence 確認 → redirect」を書く時の入口。
//   失効済み Cookie が残っているケースは弾けない（Redis セッションストアに問い合わせない
//   軽量ガードのため）。失効分は遷移先 API が 401 を返してログアウト相当に倒れる。
export const hasSessionCookie = async (): Promise<boolean> => {
  return (await cookies()).has(SESSION_COOKIE_NAME);
};
