// session-cookie: セッション Cookie 名の SSoT。
//   Backend の apps/api/app/core/config.py の session_cookie_name と一致させる。
//   Server Component で `cookies().get(SESSION_COOKIE_NAME)` を使う認証ガード
//   （/ / /login / /problems/:id 等）の Cookie 名を 1 箇所に集約しておくことで、
//   Cookie 名が変わった時に grep 漏れが起きないようにする。
//
//   ここは「Cookie が存在するか」の presence チェック専用。Cookie 有効性の
//   最終判定は Backend の Depends(get_current_user) が SSoT。

export const SESSION_COOKIE_NAME = "session_id";
