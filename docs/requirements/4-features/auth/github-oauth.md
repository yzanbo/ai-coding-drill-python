# GitHub OAuth ログイン

## ユーザーストーリー

As a **プログラミング学習者（ゲスト）**
I want **GitHub アカウントでログインしたい**
So that **別途アカウントを登録する手間を省きつつ、自分の学習履歴を保存できる状態でサービスを利用したいから**

## 受け入れ条件（Definition of Done）

**§1 認証基盤に紐づく項目**

- [ ] ログイン後、`GET /auth/me` で現在のユーザー情報が取得できる
- [ ] セッションは 7 日間有効で、ユーザーが操作するたびに延長される
- [ ] ログアウトボタン押下でセッションが破棄され、未認証状態に戻る
- [ ] セッション期限切れ後にアクセスすると、未認証として扱われ再ログインを要求される
- [ ] DB 上で `users` テーブルと `auth_providers` テーブルにデータが分離して保存される（プロバイダ ID をユーザーに直接持たせない）
- [ ] 認証要否はルーター単位の FastAPI 依存（`Depends(get_current_user)` / `Depends(get_current_user_optional)`）で制御され、デフォルトは認証必須になっている

**§2 GitHub プロバイダ実装に紐づく項目**

- [ ] ヘッダーまたは `/login` 画面に「GitHub でログイン」ボタンが表示される
- [ ] ボタン押下で GitHub の認可画面に遷移する
- [ ] 認可後、自動的にコールバック処理が走り、ログイン状態でホーム画面に遷移する
- [ ] 同じ GitHub アカウントで再ログインすると、既存ユーザーが再利用される（重複作成されない）

## 概要

GitHub OAuth を使った認証機能。プログラミング学習者がターゲットのため複数プロバイダは過剰と判断し、MVP は GitHub OAuth 1 本に絞る。ただし**将来的に Google / Email-Password 等を追加可能な拡張設計を維持する**ため、本文書は以下の 2 部構成で書く：

- **§1 認証基盤（プロバイダ非依存）**：将来 Google OAuth / Email-Password 等を追加した時にそのまま再利用される、ユーザー / セッション / 認可ガードの共通仕様
- **§2 GitHub OAuth プロバイダ実装**：§1 の基盤に乗る、GitHub に固有な OAuth フロー / GitHub API 連携

Google OAuth 等が実装される段になったら、§1 を独立ファイル（`auth/foundation.md` 等）に切り出し、GitHub / Google それぞれを別ファイルにするリファクタリングを行う。それまでは 1 ファイル内のセクション分けで「拡張余地が設計に組み込まれていること」を文書構造で示す。

## スコープ外（このスプリントでは扱わない）

- メールアドレス + パスワード認証（拡張時に新規 Strategy として追加）
- 2 要素認証（2FA）：R7 以降で必要性を再評価
- パスワードリセット機能：OAuth のみのため不要
- Google / Apple / Email-Password OAuth：拡張余地として設計上は残すが本機能の対象外
- ユーザープロフィール編集（表示名変更等）：別機能として切り出す
- アカウント削除（退会）：[01-non-functional.md](../../2-foundation/01-non-functional.md) のハードデリート方針に従い、必要になったら別機能化

---

## §1 認証基盤（プロバイダ非依存）

> このセクションは GitHub OAuth に依存しない共通仕様。将来 Google OAuth / Email-Password 等を追加した時もそのまま再利用される。

### §1.1 ビジネスルール（基盤）

- **匿名利用は不可**：問題の生成・解答送信・学習履歴の記録には認証が必須
- **問題閲覧（一覧・詳細）はゲストでも可能**：解答送信のみ認証必須（→ [problem/display-and-answer.md](../problem/display-and-answer.md)）
- **メールアドレスは取得できれば保存するが UNIQUE 制約は付けない**（プロバイダ側でメール非公開のユーザーが存在しうるため）
- **同一プロバイダの同一外部 ID = 同一ユーザー**：既存 `auth_providers.provider_id` と一致するなら既存 `users` を再利用（プロバイダごとの判定ロジックは §2 で定義）

### §1.2 データモデル

詳細は [3-cross-cutting/01-data-model.md](../../3-cross-cutting/01-data-model.md) と SQLAlchemy 2.0 model（`apps/api/app/models/`、`Mapped[T]` 方式、→ [ADR 0037](../../../adr/0037-sqlalchemy-alembic-for-database.md)）を参照。

- `users`：プロバイダ非依存のユーザー情報（`id`, `email?`, `display_name`, `created_at`）
- `auth_providers`：プロバイダごとの ID マッピング（`provider` 列挙、`provider_id`, `user_id` FK）
- 関係：`users 1 — N auth_providers`（同一ユーザーが将来複数プロバイダを持てる構造）

### §1.3 セッション

- 保存先：**Redis**（→ [ADR 0047](../../../adr/0047-session-store-on-redis.md)）、TTL 7 日
- クライアント：Cookie に `session_id` を `HttpOnly` + `Secure` + `SameSite=Lax` で発行
- 延長ポリシー：ユーザー操作のたびに TTL リセット（rolling session）
- CSRF 対策：状態を持つフローでは `state` パラメータを Redis に事前格納してコールバックで照合（具体的な扱いは §2 のプロバイダごとに定義）

### §1.4 認証ガード（FastAPI 依存性注入）

- 全ルートデフォルト認証必須：`get_current_user` を APIRouter の `dependencies=[Depends(...)]` でグローバル適用
- public ルートは個別 router で `dependencies=[]` で上書き
- 401 セマンティクスは [3-cross-cutting/02-api-conventions.md](../../3-cross-cutting/02-api-conventions.md#認証セッション) を参照

### §1.5 共通 API

| メソッド | パス | 用途 | 認証 |
|---|---|---|---|
| POST | `/auth/logout` | ログアウト（セッション破棄） | 必須 |
| GET | `/auth/me` | 現在のユーザー情報取得 | 必須 |

機械可読の最新仕様は OpenAPI（`apps/api/openapi.json`、ランタイムは FastAPI の `/openapi.json`）が SSoT。本セクションは設計意図の記録（→ [ADR 0006](../../../adr/0006-json-schema-as-single-source-of-truth.md)）。

### §1.6 共通画面コンポーネント

#### ヘッダーのログイン状態表示（対象：全ユーザー）

- **概要**：未認証時はログインボタン、認証時はユーザー名 + ログアウトボタンを表示
- **主要コンポーネント**：`<HeaderUserMenu />`
- **使用 API**：
  - `GET /auth/me` — 現在のユーザー情報取得
  - `POST /auth/logout` — ログアウト

### §1.7 共通フロー

#### ログアウトフロー（対象：認証ユーザー）

1. ユーザーがヘッダーのログアウトボタンを押下
2. `POST /auth/logout` でセッション破棄リクエスト
3. FastAPI が Redis 上のセッションを削除し、Cookie をクリア
4. ホーム画面（または `/login`）にリダイレクト、未認証状態に戻る

---

## §2 GitHub OAuth プロバイダ実装

> このセクションは §1 の基盤に乗る、GitHub に固有な部分のみ。Google OAuth 等を追加するときは本セクションと並列に別セクション / 別ファイルを作る。

### §2.1 ビジネスルール（GitHub 固有）

- **想定ターゲットは GitHub アカウント所有者**（中級プログラマ）。これがそのまま認証手段になる
- **GitHub の `id`（数値）を `auth_providers.provider_id` として `provider='github'` で保存**：既存 `auth_providers` と一致するなら既存 `users` を再利用、新規なら `users` + `auth_providers` を同一トランザクションで作成
- **GitHub からの取得情報**：`id`（必須）、`login`（display_name にフォールバック利用）、`email`（公開していれば保存）

### §2.2 ログイン画面（対象：ゲスト）

- **ルート**：`/login`
- **概要**：未認証ユーザーが GitHub OAuth フローを開始するエントリポイント
- **主要コンポーネント**：`<GitHubLoginButton />`
- **使用 API**：
  - `GET /auth/github` — OAuth 開始（GitHub へリダイレクト）
- **主要インタラクション**：
  - ボタンクリックで GitHub の認可画面に遷移
  - 認可後 `/auth/github/callback` に戻り、自動でホームへ遷移

### §2.3 GitHub OAuth フロー（対象：ゲスト → 認証ユーザー）

1. ゲストが `/login` または任意ページのログインボタンを押下
2. ブラウザが `GET /auth/github` にアクセス
3. FastAPI が GitHub の認可 URL を生成、`state` を Redis に事前格納してリダイレクト
4. ユーザーが GitHub で認可
5. GitHub が `GET /auth/github/callback?code=...&state=...` にリダイレクト
6. FastAPI が `state` を Redis 上の事前格納値と照合（CSRF 対策）
7. `code` を access_token に交換し、GitHub API でユーザー情報取得（`httpx.AsyncClient` 等の async クライアントを利用）
8. `auth_providers.provider_id` で既存ユーザー検索 → 既存なら再利用、新規なら `users` + `auth_providers` を同一トランザクションで作成（SQLAlchemy 2.0 async セッション）
9. セッションを §1.3 の仕様に従って Redis に保存、Cookie を発行
10. ホーム画面（`/`）にリダイレクト

### §2.4 GitHub 固有 API

| メソッド | パス | 用途 | 認証 |
|---|---|---|---|
| GET | `/auth/github` | OAuth 開始（GitHub へリダイレクト） | ゲスト |
| GET | `/auth/github/callback` | OAuth コールバック、セッション確立 | ゲスト |

### §2.5 バリデーション

OAuth コールバックの `code` / `state` パラメータは GitHub 側 / Redis 側で生成・保存されるため、サーバ側はフォーマットチェックのみ：

| フィールド | ルール | エラーメッセージ |
|---|---|---|
| `code` | 必須（クエリパラメータ） | 認証情報が不正です。再度ログインしてください |
| `state` | 必須、Redis 上の事前発行値と一致 | 認証セッションが無効です。再度ログインしてください |

---

## 関連

- **関連 ADR**：
  - [ADR 0011: GitHub OAuth で拡張可能設計](../../../adr/0011-github-oauth-with-extensible-design.md)
  - [ADR 0033: バックエンドを Python に転換](../../../adr/0033-backend-language-pivot-to-python.md)
  - [ADR 0034: バックエンドフレームワークに FastAPI](../../../adr/0034-fastapi-for-backend.md)
  - [ADR 0037: SQLAlchemy 2.0 + Alembic](../../../adr/0037-sqlalchemy-alembic-for-database.md)
  - [ADR 0047: Redis セッションストア](../../../adr/0047-session-store-on-redis.md)
- **横断要件**：
  - 認証アーキテクチャ：[2-foundation/02-architecture.md](../../2-foundation/02-architecture.md#backend-apifastapi--python)
  - セッション・レート制限：[2-foundation/01-non-functional.md](../../2-foundation/01-non-functional.md)
  - 認証関連 API 仕様：[3-cross-cutting/02-api-conventions.md](../../3-cross-cutting/02-api-conventions.md#認証セッション)
- **データモデル**：[3-cross-cutting/01-data-model.md](../../3-cross-cutting/01-data-model.md)
- **実装ルール**：[backend.md](../../../../.claude/rules/backend.md)

## ステータス

- [ ] 要件定義完了（このファイルが受け入れ条件まで埋まっている）
- [ ] バックエンド実装完了（FastAPI auth ルーター / セッションサービス / GitHub OAuth クライアント）
- [ ] フロントエンド実装完了（ログイン画面 / ヘッダーメニュー）
- [ ] ユニットテスト完了（pytest：auth サービス / GitHub クライアントのモックテスト、→ [ADR 0038](../../../adr/0038-test-frameworks.md)）
- [ ] E2E テスト完了（ログイン〜ログアウトの主要フロー、Playwright）
- [ ] 受け入れ条件すべて満たす
- [ ] PR マージ済み

## スプリント情報

- **対象スプリント**：Sprint 1（MVP 立ち上げ）
- **ストーリーポイント**：未確定
- **担当**：神保
- **着手日 / 完了日**：未着手 / 未完了
