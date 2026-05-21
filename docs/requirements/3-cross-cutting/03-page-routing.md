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

- ルートは **3 系統**：完全公開（`/`、`/login`、`/problems`）/ 認証必須
  （`/problems/:id`、`/problems/new`、`/problems/generate/:requestId`、`/me/*`）/
  特殊（`404`）。
- 認証必須画面の **ガード手法は 2 種類**：
  - **`(authed)` layout** が `useGetAuthMe` で判定して `/login?next=...` に
    リダイレクトする（`/problems/new` / `/me/*`、強制ログイン誘導）
  - **`LoginRequiredMessage` 案内ページ**を返して `/login?next=...` の CTA を提示
    する（`/problems/:id` のみ、解答送信と一体の UX を保つため）
- `/` は **認証状態で挙動が分岐**：ログイン済みは `/problems` へリダイレクト、
  未ログインはランディング画面を表示。
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
>   - `非公開` ：その状態のユーザーには本来の画面を見せない。続く行が代替動作（リダイレクト or 案内ページ）
>   - `△` ：URL は留まるが、別の案内画面に差し替えて表示
>   - `→` ：別 URL にリダイレクト（矢印の後ろが着地先）
> - ガード方法の詳細は §2 を参照

| 画面名 | 経路 | 認証済 | 未認証 | ガード方法 |
|---|---|---|---|---|
| ランディング | `/` | 非公開<br>→ `/problems` | 公開 | server-side cookie + `redirect()` |
| ログイン | `/login` | 非公開<br>→ `?next` または `/` | 公開 | server-side cookie + `redirect()` |
| 問題一覧 | `/problems` | 公開 | 公開 | なし |
| 問題詳細 + 解答エディタ | `/problems/:id` | 公開 | 非公開<br>△ `LoginRequiredMessage` | server-side cookie + 案内ページ差し替え |
| 問題生成リクエスト | `/problems/new` | 公開 | 非公開<br>→ `/login?next=...` | `(authed)` layout |
| 生成ステータス | `/problems/generate/:requestId` | 公開 | 非公開<br>→ `/login?next=...` | `(authed)` layout |
| 解答履歴 | `/me/history` | 公開 | 非公開<br>→ `/login?next=...` | `(authed)` layout |
| 学習統計 | `/me/stats` | 公開 | 非公開<br>→ `/login?next=...` | `(authed)` layout |
| 弱点カテゴリ | `/me/weakness` | 公開 | 非公開<br>→ `/login?next=...` | `(authed)` layout |
| —（存在しないパス） | `404` | 非公開<br>→ `/problems` | 非公開<br>→ `/` | `app/not-found.tsx` + server-side `redirect()` |

### 補足：`/auth/*`（OAuth 経路）

`/auth/github` / `/auth/github/callback` / `/auth/logout` / `/auth/me` は
**Backend が直接捌く API** であり、FE 側ルートではない（Next.js の rewrites で
FastAPI に転送される）。本表の対象外。詳細は
[authentication.md §2 GitHub OAuth フロー](../4-features/authentication.md)。

---

## 2. ガード方法の使い分け

認証必須画面は **2 通り**のガードを使い分ける。どちらも最終的に
「未ログインユーザーをログイン経路に誘導する」目的は同じだが、
**ユーザー体験の濃淡**が異なる。

### 2.1 `(authed)` layout によるリダイレクトガード（強制誘導型）

- **使う画面**：`/problems/new`、`/problems/generate/:requestId`、`/me/*`
- **挙動**：[`apps/web/src/app/(routing)/(authed)/layout.tsx`](../../../apps/web/src/app/(routing)/(authed)/layout.tsx) が
  `useGetAuthMe` で認証状態を見て、`isUnauthenticated` なら
  `router.replace("/login?next=<元の path>")` を発火する。判定中は空表示
  （チラ見せ防止）。
- **採用理由**：これらの画面は「未ログインなら何も見せる意味がない」純粋な
  認証必須機能。問題生成リクエストや学習履歴は他人の集計値ではないため、
  ログイン前提のページに直接送ってログインさせる方が動線が短い。

### 2.2 `LoginRequiredMessage` 案内ガード（誘導 + 意図の提示型）

- **使う画面**：`/problems/:id` のみ
- **挙動**：[`apps/web/src/app/(routing)/(public)/problems/[id]/page.tsx`](../../../apps/web/src/app/(routing)/(public)/problems/[id]/page.tsx) が
  server-side で `cookies()` から `session_id` の有無を確認し、無ければ
  [`<LoginRequiredMessage next={pathname} />`](../../../apps/web/src/components/parts/login-required-message/login-required-message.tsx) を
  返す。問題本文はレンダリングされない。
- **採用理由**：`/problems/:id` は「解答送信と一体の UX」のため、未ログイン
  ユーザーには「ログインしないと使えない」ことを明示してから誘導したい。
  即リダイレクトすると「なぜ飛ばされた？」が伝わらない。問題一覧
  （`/problems`）はゲスト閲覧可のままで、詳細だけ案内に切り替える。

### 2.3 ガード方法を切り替える判断軸

下記のいずれかに該当したら **案内ガード**を選ぶ。それ以外は **リダイレクトガード**。

- ユーザーが「クリックして来た先」で意図を持って踏んでいる（一覧 → 詳細など）
- 同オリジン内の他画面と地続きで、突然 `/login` に飛ぶと文脈が断たれる
- 「ログインしてください」の理由を 1 行説明したいユースケース

それ以外（直接踏みでも意図不明 / 機能単体としてログイン必須が自明）は
リダイレクトガードで十分。

---

## 3. ガード判定の SSoT と FE / API の役割分担

- **認証要否の最終 SSoT** は **Backend の `Depends(get_current_user)`**。
  認証が必要な API エンドポイントは 401 を返す。
- **FE 側のガード** は **UX 用の早期分岐**であり、ネットワーク帯域・チラ見せ
  防止・動線整流のために置く。
  - server-side cookie presence チェック（`/`、`/login`、`/problems/:id`）
  - client-side `useGetAuthMe` 判定（`(authed)` layout）
- **Cookie の有効性チェックは行わない**。Cookie が存在するが Redis 側で
  セッションが失効しているケースは、API 呼び出しで 401 が返り、それを
  `ApiErrorProvider` がトーストで通知 + `/login` リダイレクトに繋ぐ
  （詳細は [authentication.md §認証 API が失敗した時の FE 側挙動](../4-features/authentication.md)）。
- **Cookie 名 SSoT** は [`apps/api/app/core/config.py`](../../../apps/api/app/core/config.py) の
  `session_cookie_name`（既定 `session_id`）。FE 側でこの文字列を
  ハードコードする箇所（`/` / `/problems/:id` の server-side チェック）は
  本ファイルの存在をコメントで明示する。

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
- [x] 未ログインで `/problems` を踏むと一覧画面が表示される（401 にならない）
- [x] 未ログインで `/problems/:id` を踏むと `LoginRequiredMessage` 案内が表示され、
      問題本文は読めない / CTA から `/login?next=/problems/:id` に進める
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
  - [apps/web/e2e/problem-display-and-answer.spec.ts](../../../apps/web/e2e/problem-display-and-answer.spec.ts)（`LoginRequiredMessage` E2E）
- **ADR**：
  - [ADR 0011](../../adr/0011-github-oauth-with-extensible-design.md)（GitHub OAuth）
  - [ADR 0047](../../adr/0047-session-store-on-redis.md)（セッションストア = Redis + Cookie）
- **実装ルール**：[.claude/rules/frontend.md](../../../.claude/rules/frontend.md)
