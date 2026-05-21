// session-cookie-name: 認証 Cookie 名の SSoT 定数だけを置くファイル。
//   Edge Runtime（src/middleware.ts）からも import できるよう、
//   `next/headers` 等の Server-only API を持たないファイルに分離している。
//   `session-cookie.ts` 側の hasSessionCookie ヘルパは `next/headers` の
//   cookies() を使うため、同居させると Edge から import した瞬間に
//   server-only モジュール解決エラーになりうる（Next.js のバージョンに
//   よっては tree-shake で逃げているだけ）。
//
//   Backend の apps/api/app/core/config.py の session_cookie_name と
//   一致させる（手動同期、Cookie 名 1 文字列の SSoT 化は YAGNI）。

export const SESSION_COOKIE_NAME = "session_id";
