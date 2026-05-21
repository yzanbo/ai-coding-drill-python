# 03. 画面ルーティングと認証ガード

> **このドキュメントの守備範囲**：サイト内の全画面ルートと、各画面における
> ログイン / 未ログインでの挙動（着地先・表示内容・ガード方法）を横断俯瞰する。
> **個別画面の詳細仕様の SSoT**：[4-features/](../4-features/) 配下の各機能 .md
> （`/me/*` は [learning.md](../4-features/learning.md)、`/problems/*` は
> [problem-display-and-answer.md](../4-features/problem-display-and-answer.md)、
> `/login` は [authentication.md](../4-features/authentication.md)）。
> **関連トピックの参照先**：
> - 認証 / セッション全般：[4-features/authentication.md](../4-features/authentication.md)
> - 採用根拠：[ADR 0011](../../adr/0011-github-oauth-with-extensible-design.md)（GitHub OAuth）
>   / [ADR 0047](../../adr/0047-session-store-on-redis.md)（セッションストア）
> - フロントエンド規約：[.claude/rules/frontend.md](../../../.claude/rules/frontend.md)

---

## TL;DR

- ルートは **3 系統**：完全公開（`/`、`/login`）/ 認証必須（`/problems`、
  `/problems/:id`、`/problems/new`、`/problems/generate/:requestId`、`/me/*`）/
  特殊（`404`）。
- 認証必須画面の **未ログイン → `/login?next=...` redirect は Next.js middleware
  に集約**（[apps/web/src/middleware.ts](../../../apps/web/src/middleware.ts)）。
  Cookie が無いリクエストを RSC レンダリングより一段早く弾く。
- `(authed)` ルートグループには **加えて** client-side `useGetAuthMe` ガードが
  残る。これは「Cookie はあるが Redis セッションが失効している」ケースを
  API 401 から拾うための二段目で、middleware の presence チェックだけでは
  代替できない。
- `/` は **認証状態で挙動が分岐**：ログイン済みは `/problems` へリダイレクト、
  未ログインはランディング画面を表示（Server Component の cookie 判定）。
- `/login` も同様に、ログイン済アクセスを `?next=` / `/problems` に倒す
  （Server Component の cookie 判定）。
- `404` も認証状態で分岐：ログイン済みは `/problems` に、未ログインは `/` に
  server-side `redirect()` する（`app/not-found.tsx`）。

---

## 1. ルート × 認証マトリクス（人間可読の SSoT）

下表は **観測可能な振る舞い**の SSoT。ルート追加 / 認証要否の変更があったら
ここを真っ先に更新し、対応する `4-features/` の個別 .md と実装を追従させる。

> 列の見方：
> - **画面名**：その URL に紐づく主要画面コンポーネント
> - **認証済 / 未認証**：その URL を直接踏んだ時の挙動。記号は下記凡例
> - **凡例**
>   - `公開` ：その状態のユーザーにそのまま画面が見える（URL も画面も変わらない）
>   - `非公開` ：その状態のユーザーには本来の画面を見せない。続く行が代替動作
>   - `→` ：別 URL にリダイレクト（矢印の後ろが着地先）
> - ガード方法の詳細は §2 を参照

| 画面名 | 経路 | 認証済 | 未認証 | ガード方法 |
|---|---|---|---|---|
| ランディング | `/` | 非公開<br>→ `/problems` | 公開 | server-side cookie + `redirect()`（guest-only） |
| ログイン | `/login` | 非公開<br>→ `?next` または `/` | 公開 | server-side cookie + `redirect()`（guest-only） |
| 問題一覧 | `/problems` | 公開 | 非公開<br>→ `/login?next=/problems` | middleware |
| 問題詳細 + 解答エディタ | `/problems/:id` | 公開 | 非公開<br>→ `/login?next=/problems/:id` | middleware |
| 問題生成リクエスト | `/problems/new` | 公開 | 非公開<br>→ `/login?next=...` | middleware + `(authed)` layout |
| 生成ステータス | `/problems/generate/:requestId` | 公開 | 非公開<br>→ `/login?next=...` | middleware + `(authed)` layout |
| 解答履歴 | `/me/history` | 公開 | 非公開<br>→ `/login?next=...` | middleware + `(authed)` layout |
| 学習統計 | `/me/stats` | 公開 | 非公開<br>→ `/login?next=...` | middleware + `(authed)` layout |
| 弱点カテゴリ | `/me/weakness` | 公開 | 非公開<br>→ `/login?next=...` | middleware + `(authed)` layout |
| 生成履歴 | `/me/generations` | 公開 | 非公開<br>→ `/login?next=...` | middleware + `(authed)` layout |
| —（存在しないパス） | `404` | 非公開<br>→ `/problems` | 非公開<br>→ `/` | `app/not-found.tsx` + server-side `redirect()` |

### 補足：`/auth/*`（OAuth 経路）

`/auth/github` / `/auth/github/callback` / `/auth/logout` / `/auth/me` は
**Backend が直接捌く API** であり、FE 側ルートではない（Next.js の rewrites で
FastAPI に転送される）。本表の対象外。詳細は
[authentication.md §2 GitHub OAuth フロー](../4-features/authentication.md)。

---

## 2. ガード方法の使い分け

認証必須画面のガードは **3 階層**に分かれる。すべて未ログインの最終着地は
`/login?next=...` で揃うが、果たす責務がそれぞれ異なる。

### 2.1 middleware（Edge Runtime、全認証必須パスの 1 段目）

- **使う画面**：`/problems`、`/problems/:id`、`/problems/new`、
  `/problems/generate/:requestId`、`/me/*`
- **実装**：[apps/web/src/middleware.ts](../../../apps/web/src/middleware.ts)。
  `req.cookies.has("session_id")` で presence チェックし、無ければ
  `/login?next=<pathname+search>` に 307 redirect する。
- **採用理由**：
  - RSC レンダリングが始まる前に Edge 層で確定する（コスト・レイテンシ最小）
  - 認証必須画面の追加コストが「`PROTECTED_PATTERNS` に正規表現を 1 行足す」だけ
  - 画面ごとの冒頭ガード（`if (!await hasSessionCookie()) redirect(...)`）の
    重複が消える
- **境界**：「Cookie の有無」しか見ない。Redis セッション失効は `(authed)` layout
  または ApiErrorProvider が拾う。
- **stale Cookie ループ防止**：Backend は 401 を返す時、リクエストに `session_id`
  Cookie が付いていれば Max-Age=0 で物理削除する（[apps/api/app/main.py](../../../apps/api/app/main.py)
  の `clear_stale_session_cookie_on_401` middleware）。これにより
  「Cookie あり + Redis 失効」状態のリクエストが 1 回 401 を返した時点で
  Cookie が消え、次の `/login` 訪問では Cookie 無し扱いとなって LoginForm が
  表示される（`/login` Server の `hasSessionCookie` → redirect ループに陥らない）。

### 2.2 `(authed)` layout（Client Component 経路の 2 段目）

- **使う画面**：`/problems/new`、`/problems/generate/:requestId`、`/me/*`
- **実装**：[`apps/web/src/app/(routing)/(authed)/layout.tsx`](../../../apps/web/src/app/(routing)/(authed)/layout.tsx)。
  `useGetAuthMe` で `/auth/me` を呼び、`isUnauthenticated` なら
  `router.replace("/login?next=<pathname>")` を発火。判定中は空表示。
- **採用理由**：middleware の presence チェックでは「Cookie はあるが Redis 側で
  失効」を検知できない。`useGetAuthMe` が API 401 を見て補完する。
- **middleware との関係**：middleware が `/me/*` 等で先に 307 を返すため、
  Cookie の無い純粋な未ログインは layout に到達しない。layout で見るのは
  Cookie あり + 失効 / 通信障害のケースのみ。

### 2.3 server-side cookie + `redirect()`（guest-only 系の Server Component）

- **使う画面**：`/`、`/login`、`app/not-found.tsx`
- **挙動**：Server Component で [`cookies()`](https://nextjs.org/docs/app/api-reference/functions/cookies) から
  `session_id` の有無を見て、ログイン済なら別画面に倒す（`/` / `/login` →
  `/problems`、not-found → `/problems` or `/`）。
- **middleware に乗せない理由**：これらは「ログイン済を別画面に倒す」逆方向
  の分岐。`/login` を middleware で「Cookie あり → /problems」に倒すと、
  `(authed)` layout の 401 → `/login?next=/me/*` → `/problems` → /me/* の
  ループが発生しうる。`/login` の Cookie→redirect は Server Component に
  閉じ込めることで、middleware の責務を「未ログインを `/login` へ寄せる」
  一方向に保ち、ループを構造的に断ち切る。

---

## 3. ガード判定の SSoT と FE / API の役割分担

- **認証要否の最終 SSoT** は **Backend の `Depends(get_current_user)`**。
  認証が必要な API エンドポイントは 401 を返す。
- **FE 側のガード** は **UX 用の早期分岐**であり、ネットワーク帯域・チラ見せ
  防止・動線整流のために置く。
  - middleware の Cookie presence チェック（`/problems` / `/problems/:id` /
    `/problems/new` / `/problems/generate/:requestId` / `/me/*`）
  - client-side `useGetAuthMe` 判定（`(authed)` layout、Cookie 失効を補完）
  - server-side cookie presence チェック（`/`、`/login`、`not-found.tsx` の
    guest-only / 認証分岐）
- **Cookie の有効性チェックは行わない**。Cookie が存在するが Redis 側で
  セッションが失効しているケースは、API 呼び出しで 401 が返り、それを
  `ApiErrorProvider` がトーストで通知 + `/login` リダイレクトに繋ぐ
  （詳細は [authentication.md §認証 API が失敗した時の FE 側挙動](../4-features/authentication.md)）。
- **Cookie 名 SSoT** は [`apps/api/app/core/config.py`](../../../apps/api/app/core/config.py) の
  `session_cookie_name`（既定 `session_id`）。FE 側は 2 ファイルに分けて配置：
  - [`apps/web/src/lib/auth/session-cookie-name.ts`](../../../apps/web/src/lib/auth/session-cookie-name.ts)：
    Cookie 名定数 `SESSION_COOKIE_NAME` のみを置く（`next/headers` 非依存）。
    Edge Runtime の [`src/middleware.ts`](../../../apps/web/src/middleware.ts) はこちらから import する。
  - [`apps/web/src/lib/auth/session-cookie.ts`](../../../apps/web/src/lib/auth/session-cookie.ts)：
    `hasSessionCookie()` ヘルパ（`next/headers` 依存、Server Component 専用）を置く。
    すべての guest-only ガード経路（`/` / `/login` / `not-found.tsx`）で
    このヘルパを import して使う。
  - 物理ファイルを分ける理由：Edge Runtime（middleware）から `next/headers` を
    間接 import すると Next.js の server-only 制約に抵触するため、Cookie 名定数
    だけを `next/headers` 非依存ファイルに切り出している。

---

## 4. グローバルナビゲーション

ヘッダー（[`SiteHeader`](../../../apps/web/src/components/parts/site-header/site-header.tsx)）は
**ログイン済みユーザーにのみ**グローバルナビを表示する。

| ラベル | 遷移先 |
|---|---|
| 問題一覧 | `/problems` |
| 解答履歴 | `/me/history` |
| 学習統計 | `/me/stats` |
| 弱点 | `/me/weakness` |
| 生成履歴 | `/me/generations` |

> 表示順 / ラベル / 遷移先の SSoT は `SiteHeader` 内の `GLOBAL_NAV_LINKS` 定数。
> 増減があったらまずそこを更新し、本表もあわせて更新する。

未ログインユーザーにはナビを出さない（リンク先がいずれも認証必須のため、
押しても `/login` に追い返されて動線として無効になる）。

---

## 5. 受け入れ条件（観測可能な振る舞い）

ルート / 認証ガードに関する横断的な受け入れ条件。個別画面の受け入れ条件は
各機能 .md にある。**振る舞いを変更した時は本節を更新し、対応する E2E
（[apps/web/e2e/redirects.spec.ts](../../../apps/web/e2e/redirects.spec.ts)）を直す**。

- [x] 未ログインで `/` を踏むとランディング画面が表示され、URL は `/` のまま
- [x] ログイン済みで `/` を踏むと `/problems` に遷移する
- [x] 未ログインで `/problems` を踏むと `/login?next=/problems` にリダイレクトされる
- [x] 未ログインで `/problems/:id` を踏むと `/login?next=/problems/:id` にリダイレクトされる
- [x] 未ログインで `/me/*` / `/problems/new` を踏むと `/login?next=...` に
      クライアントサイドリダイレクトされる
- [x] 未ログインで存在しないパスを踏むと `/` に着地しランディングが出る
- [x] ログイン済みで存在しないパスを踏むと `/problems` に着地する
- [x] ヘッダーのグローバルナビ（問題一覧 / 解答履歴 / 学習統計 / 弱点）は
      ログイン時のみ表示される

---

## 6. 関連

- **個別機能 .md**：
  - [4-features/authentication.md](../4-features/authentication.md)（`/login` / セッション管理）
  - [4-features/problem-display-and-answer.md](../4-features/problem-display-and-answer.md)（`/problems` / `/problems/:id`）
  - [4-features/problem-generation.md](../4-features/problem-generation.md)（`/problems/new` / `/problems/generate/:requestId`）
  - [4-features/learning.md](../4-features/learning.md)（`/me/*`）
- **テスト**：
  - [apps/web/e2e/redirects.spec.ts](../../../apps/web/e2e/redirects.spec.ts)（`/` と 404 の認証分岐 E2E）
  - [apps/web/e2e/auth.spec.ts](../../../apps/web/e2e/auth.spec.ts)（`(authed)` layout ガード E2E）
  - [apps/web/e2e/problem-display-and-answer.spec.ts](../../../apps/web/e2e/problem-display-and-answer.spec.ts)（`/problems` / `/problems/:id` の認証ガード E2E）
- **ADR**：
  - [ADR 0011](../../adr/0011-github-oauth-with-extensible-design.md)（GitHub OAuth）
  - [ADR 0047](../../adr/0047-session-store-on-redis.md)（セッションストア = Redis + Cookie）
- **実装ルール**：[.claude/rules/frontend.md](../../../.claude/rules/frontend.md)
