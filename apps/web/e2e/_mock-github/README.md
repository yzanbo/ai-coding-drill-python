# Mock GitHub OAuth サーバ

R1-1 GitHub OAuth ログインの E2E テスト（Playwright）で実 github.com を叩かずに OAuth フローを完走させるための mock サーバ。

## なぜ要るか

実 GitHub OAuth は E2E に向かない：

- API キー（GITHUB_CLIENT_ID / SECRET）が必須で CI に置きにくい
- レート制限・実ユーザー認証フローが必要
- 「Cancel」「state 不正」等の異常系を意図的に再現できない

Backend 側で `GITHUB_AUTHORIZE_URL` / `GITHUB_TOKEN_URL` / `GITHUB_USER_API_URL` の 3 環境変数をこの mock サーバ URL に上書きすると、Backend は OAuth フローを mock 越しに走らせる（[apps/api/app/services/github_oauth.py](../../../api/app/services/github_oauth.py) 参照）。

## エンドポイント

| メソッド | パス | 役割 |
|---|---|---|
| GET | `/login/oauth/authorize` | 認可画面の代替。即 302 で `redirect_uri?code=<...>&state=<...>` に redirect |
| POST | `/login/oauth/access_token` | code → access_token 交換 |
| GET | `/user` | access_token → user profile (id / login / name / email) |
| GET | `/_health` | Playwright globalSetup から起動確認用 |

## テスト分岐の注入方法

mock はステートレス。テストごとに異なる挙動を出すため、クエリ・code 文字列で分岐する：

| 挙動 | 呼び出し方 |
|---|---|
| Cancel（GitHub 側で拒否） | `/login/oauth/authorize?...&_mode=cancel` → `error=access_denied` |
| 既定 user で正常完走 | クエリ追加なし |
| user 変種で正常完走 | `?...&_user_variant=user_name_a` 等（[server.py](./server.py) の `_USER_VARIANTS` を参照） |
| token 交換失敗 | code が `invalid_*` で始まる |

## 起動

```bash
uv run python apps/web/e2e/_mock-github/server.py --port 18001
```

Playwright の `webServer` configuration で自動起動される（[playwright.config.ts](../../playwright.config.ts) 参照）。

## やってはいけないこと

- 本サーバを本番 / staging に向ける（E2E 専用、external bind 禁止）
- 実 GitHub の挙動と異なる仕様を勝手に追加する（mock は薄い shim に保つ）
- `_USER_VARIANTS` に PII 風の値を入れる（テスト用ダミー値のみ）
