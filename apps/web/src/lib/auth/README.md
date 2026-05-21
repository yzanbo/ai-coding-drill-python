## auth/

Server Component の **認証ガード補助**を集める場所。
具体的には「セッション Cookie が来ているか」を判定する小物が入る。
Cookie 名や `cookies().has(...)` の使い方を呼び出し側に晒さず、
ヘルパ 1 つで意図を表す。

### 何を置くか

| ファイル | 役目 |
|---|---|
| `session-cookie.ts` | `hasSessionCookie()` ヘルパ（`session_id` Cookie が現リクエストに来ているかを `boolean` で返す）。Cookie 名は内部実装に隠蔽 |

### どこから呼ぶか

`/`、`/login`、`/problems`、`/problems/:id`、`not-found.tsx` の各 Server Component の
認証ガード経路。詳細は
[docs/requirements/3-cross-cutting/03-page-routing.md §2 ガード方法の使い分け](../../../../../docs/requirements/3-cross-cutting/03-page-routing.md)。

### ここで判定しないこと

- **Cookie の有効性**は判定しない（presence のみ）。失効した Cookie が残っていても
  `hasSessionCookie()` は `true` を返す。最終的な有効性判定は Backend の
  `Depends(get_current_user)` が SSoT。失効分は遷移先 API の 401 で
  ログアウト相当に倒れる
- **Client Component の認証判定**は対象外（あちらは `useGetAuthMe` + `(authed)` layout
  の経路で行う）

### Cookie 名の同期先

Backend の [apps/api/app/core/config.py](../../../../../apps/api/app/core/config.py) の
`session_cookie_name`（既定 `session_id`）と一致させる。Backend 側を変えたら
本ヘルパ内の `SESSION_COOKIE_NAME` も合わせて直す。
