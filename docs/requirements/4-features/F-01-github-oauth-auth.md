# F-01: GitHub OAuth ログイン

## ユーザーストーリー

As a **プログラミング学習者（ゲスト）**
I want **GitHub アカウントでログインしたい**
So that **別途アカウントを登録する手間を省きつつ、自分の学習履歴を保存できる状態でサービスを利用したいから**

## 受け入れ条件（Definition of Done）

- [ ] ヘッダーまたは `/login` 画面に「GitHub でログイン」ボタンが表示される
- [ ] ボタン押下で GitHub の認可画面に遷移する
- [ ] 認可後、自動的にコールバック処理が走り、ログイン状態でホーム画面に遷移する
- [ ] ログイン後、`GET /auth/me` で現在のユーザー情報が取得できる
- [ ] セッションは 7 日間有効で、ユーザーが操作するたびに延長される
- [ ] ログアウトボタン押下でセッションが破棄され、未認証状態に戻る
- [ ] セッション期限切れ後にアクセスすると、未認証として扱われ再ログインを要求される
- [ ] DB 上で `users` テーブルと `auth_providers` テーブルにデータが分離して保存される（プロバイダ ID をユーザーに直接持たせない）
- [ ] 同じ GitHub アカウントで再ログインすると、既存ユーザーが再利用される（重複作成されない）
- [ ] 認証要否は `@Public()` デコレータで制御され、デフォルトは認証必須になっている

## 概要

GitHub OAuth を使った認証機能。プログラミング学習者がターゲットのため複数プロバイダは過剰と判断し、MVP は GitHub OAuth 1 本に絞る。ただし将来的に Google / Email-Password 等を追加可能な拡張設計を維持する。

## ビジネスルール

- **想定ターゲットは GitHub アカウント所有者**（中級プログラマ）。これがそのまま認証手段になる
- **匿名利用は不可**：問題の生成・解答送信・学習履歴の記録には認証が必須
- **問題閲覧（一覧・詳細）はゲストでも可能**：解答送信のみ認証必須（→ [F-03](./F-03-problem-display-and-answer.md)）
- **同一 GitHub ID = 同一ユーザー**：既存 `auth_providers.provider_id` と一致するなら既存 `users` を再利用
- **メールアドレスは取得できれば保存するが UNIQUE 制約は付けない**（GitHub 側でメール非公開のユーザーが存在するため）

## スコープ外（このスプリントでは扱わない）

- メールアドレス + パスワード認証（拡張時に新規 Strategy として追加）
- 2 要素認証（2FA）：R7 以降で必要性を再評価
- パスワードリセット機能：OAuth のみのため不要
- Google / Apple / Email-Password OAuth：拡張余地として設計上は残すが本機能の対象外
- ユーザープロフィール編集（表示名変更等）：別機能として切り出す
- アカウント削除（退会）：[01-non-functional.md](../2-foundation/01-non-functional.md) のハードデリート方針に従い、必要になったら別機能化

## データモデル

詳細は [3-cross-cutting/01-data-model.md](../3-cross-cutting/01-data-model.md) と Drizzle スキーマ（`apps/api/src/drizzle/schema/`）を参照。

- `users`：プロバイダ非依存のユーザー情報（`id`, `email?`, `display_name`, `created_at`）
- `auth_providers`：プロバイダごとの ID マッピング（`provider='github'`, `provider_id`, `user_id` FK）
- 関係：`users 1 — N auth_providers`（同一ユーザーが将来複数プロバイダを持てる構造）

## 画面

### ログイン画面（対象：ゲスト）

- **ルート**：`/login`
- **概要**：未認証ユーザーが GitHub OAuth フローを開始するエントリポイント
- **主要コンポーネント**：`<GitHubLoginButton />`
- **使用 API**：
  - `GET /auth/github` — OAuth 開始（GitHub へリダイレクト）
- **主要インタラクション**：
  - ボタンクリックで GitHub の認可画面に遷移
  - 認可後 `/auth/github/callback` に戻り、自動でホームへ遷移

### ヘッダーのログイン状態表示（対象：全ユーザー）

- **概要**：未認証時はログインボタン、認証時はユーザー名 + ログアウトボタンを表示
- **主要コンポーネント**：`<HeaderUserMenu />`
- **使用 API**：
  - `GET /auth/me` — 現在のユーザー情報取得
  - `POST /auth/logout` — ログアウト

## ユーザーフロー

### GitHub OAuth ログインフロー（対象：ゲスト → 認証ユーザー）

1. ゲストが `/login` または任意ページのログインボタンを押下
2. ブラウザが `GET /auth/github` にアクセス
3. NestJS が GitHub の認可 URL を生成してリダイレクト
4. ユーザーが GitHub で認可
5. GitHub が `GET /auth/github/callback?code=...` にリダイレクト
6. NestJS が code を access_token に交換し、GitHub API でユーザー情報取得
7. `auth_providers.provider_id` で既存ユーザー検索 → 既存なら再利用、新規なら `users` + `auth_providers` を同一トランザクションで作成
8. セッションを Redis に保存（TTL 7 日）、Cookie に `session_id` を HttpOnly + Secure + SameSite=Lax で発行
9. ホーム画面（`/`）にリダイレクト

### ログアウトフロー（対象：認証ユーザー）

1. ユーザーがヘッダーのログアウトボタンを押下
2. `POST /auth/logout` でセッション破棄リクエスト
3. NestJS が Redis 上のセッションを削除し、Cookie をクリア
4. ホーム画面（または `/login`）にリダイレクト、未認証状態に戻る

## API

| メソッド | パス | 用途 | 認証 |
|---|---|---|---|
| GET | `/auth/github` | OAuth 開始（GitHub へリダイレクト） | ゲスト |
| GET | `/auth/github/callback` | OAuth コールバック、セッション確立 | ゲスト |
| POST | `/auth/logout` | ログアウト（セッション破棄） | 必須 |
| GET | `/auth/me` | 現在のユーザー情報取得 | 必須 |

機械可読の最新仕様は OpenAPI（`/api/docs/openapi.json`）が SSoT。本セクションは設計意図の記録。

## バリデーション

OAuth コールバックの `code` パラメータは GitHub 側で生成されるため、サーバ側はフォーマットチェックのみ：

| フィールド | ルール | エラーメッセージ |
|---|---|---|
| `code` | 必須（クエリパラメータ） | 認証情報が不正です。再度ログインしてください |
| `state` | 必須、CSRF 対策のため事前発行値と一致 | 認証セッションが無効です。再度ログインしてください |

## 関連

- **関連 ADR**：
  - [ADR 0011: GitHub OAuth で拡張可能設計](../../adr/0011-github-oauth-with-extensible-design.md)
- **横断要件**：
  - 認証アーキテクチャ：[2-foundation/02-architecture.md](../2-foundation/02-architecture.md#backend-apinestjs)
  - セッション・レート制限：[2-foundation/01-non-functional.md](../2-foundation/01-non-functional.md)
  - 認証関連 API 仕様：[3-cross-cutting/02-api-conventions.md](../3-cross-cutting/02-api-conventions.md#認証セッション)
- **データモデル**：[3-cross-cutting/01-data-model.md](../3-cross-cutting/01-data-model.md)
- **実装ルール**：[backend.md](../../../.claude/rules/backend.md)

## ステータス

- [ ] 要件定義完了（このファイルが受け入れ条件まで埋まっている）
- [ ] バックエンド実装完了（AuthModule / AuthService / GitHubStrategy）
- [ ] フロントエンド実装完了（ログイン画面 / ヘッダーメニュー）
- [ ] ユニットテスト完了（AuthService / Strategy のモックテスト）
- [ ] E2E テスト完了（ログイン〜ログアウトの主要フロー、Playwright）
- [ ] 受け入れ条件すべて満たす
- [ ] PR マージ済み

## スプリント情報

- **対象スプリント**：Sprint 1（MVP 立ち上げ）
- **ストーリーポイント**：未確定
- **担当**：神保
- **着手日 / 完了日**：未着手 / 未完了
