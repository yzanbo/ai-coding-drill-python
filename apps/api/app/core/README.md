# core/

## core/ とは何か

機能に紐づかない「**アプリ全体の道具箱**」フォルダ。
特定の機能（problems / submissions 等）には属さない、横断的な部品だけを置く。

> core/ は **何も他フォルダを import しない終端**。
> 全レイヤから呼ばれるが、core から業務フォルダを呼び返してはいけない（呼び返すと循環依存になる）。

## deps/ との違い（混乱しやすい）

「共通で使うもの」だけ見ると core/ と [deps/](../deps/README.md) の役割が紛らわしいので、ここで整理しておく。

| 観点 | core/ | deps/ |
|---|---|---|
| **何を置くか** | 設定値・部品クラス・鍵・例外定義など、**静的な道具** | リクエストごとに呼び出される**前処理関数** |
| **いつ使われるか** | アプリ起動時 or 必要な時に import して使う | リクエストが来るたびに FastAPI が自動実行する |
| **呼び出し方** | 普通に `from app.core.X import Y` で import | router の引数で `Depends(...)` 経由 |
| **例：OAuth** | `GitHubOAuthClient` の**設定オブジェクト**（client_id / redirect_uri 等）| **「ログイン中ユーザーを取り出す」**関数 |
| **例：Cookie 署名** | `itsdangerous` で**署名する仕組みと鍵**を持つクラス | Cookie から session_id を取り出して**検証する**関数 |
| **例：DB** | DB の URL（`settings.database_url`）| `AsyncSession` を yield する関数 |

要するに：

- **core/** = 「**何**を使うか」（部品・設定・鍵）の定義
- **deps/** = 「**いつ・どう**使うか」（リクエスト時の組み立て方）の定義

deps/ の関数は内部で core/ の部品を使う、という呼び出し関係になる。

## core/ で扱える機能パターン一覧

### 🟢 このプロジェクトで使うパターン

#### 1. アプリ設定値の管理（`config.py`）

**何のために**：`.env` ファイルや環境変数から読み込んだ設定値を、型付きの Python オブジェクトとして一元管理するため。

DB の接続文字列・Redis URL・GitHub OAuth の client_id / secret・Sentry の DSN 等は、
全アプリで同じ値を参照する必要がある。各所で `os.environ["X"]` を散らかすと、設定漏れに気付かない／型エラーが実行時まで分からない、という事故が起きる。

`Settings` クラス（pydantic-settings 利用）1 つに集めておけば、起動時に値の存在と型を一度に検証できる。

#### 2. ドメイン例外クラス（`exceptions.py`）

**何のために**：「業務的なエラー（リソースが見つからない / 権限が足りない 等）」を、HTTP の文脈から独立した形で表現するため。

services 側で `raise HTTPException(404, "...")` と直接書くと、services が HTTP 層に依存してしまい、テストやバッチ処理（Worker など）から呼びにくくなる。

代わりに `ResourceNotFoundError` のようなドメイン例外を core/ で定義し、services はそれを投げるだけにする。core/ の例外ハンドラが「ResourceNotFoundError → 404」のような変換を 1 箇所で受け持つ。

#### 3. Cookie 署名の道具と秘密鍵（`security.py`）

**何のために**：Cookie に保存する session_id が**改ざんされていないこと**を保証するための「道具と鍵」を 1 箇所に集めるため。

session_id の生のままを Cookie に入れると、悪意あるユーザーが別の値に書き換えて他人のセッションを乗っ取れる可能性がある。
`itsdangerous` で署名（秘密鍵で HMAC を付ける）しておけば、ブラウザから返ってきた時に検証して改ざん検知できる。

core/ に置くのは**署名する仕組みと秘密鍵を持つオブジェクト**だけ。実際の **「届いた Cookie を毎リクエスト検証する関数」は [deps/auth.py](../deps/README.md) 側**にある（道具と段取りの分担）。
署名（ログイン成功時の Cookie 生成）は [services/](../services/README.md) 側がこの道具を使う。services / deps の両方から使うので、core/ に置く必要がある。

#### 4. OAuth クライアントの設定（`oauth.py` または `security.py`）

**何のために**：GitHub OAuth の `client_id` / `client_secret` / `redirect_uri` / スコープ等の**設定を 1 箇所に集める**ため。

[ADR 0011](../../../../docs/adr/0011-github-oauth-with-extensible-design.md) で「Strategy パターンで将来 Google OAuth 等を追加できる構造」を採用しているため、
`GitHubOAuthClient` を独立したモジュールとして core/ に置く。
将来 `GoogleOAuthClient` を追加する時もこのフォルダにファイルが 1 つ増えるだけになる。

#### 5. 共通レスポンス型（`schemas/common/` または `core/responses.py`）

**何のために**：`PaginationMeta` / `Page[T]` / `ErrorResponse` のような**全 API で共通の応答形**を 1 箇所で定義するため。

問題一覧・履歴一覧などのページング型レスポンスは構造が共通（`data` / `meta.total` / `meta.page` 等）。
各 schemas ファイルで個別に書くと書き方がブレるので、ジェネリック型として 1 度だけ定義する。

#### 6. 共通定数（`constants.py`）

**何のために**：「ジョブの状態名」「カテゴリのリスト」のような**マジックストリングを排除**するため。

`"queued"` / `"running"` / `"completed"` のような文字列をコード中に直書きすると、typo に気付けない。
定数として core/ に集めておけば、IDE 補完が効き、状態追加時にも core/ を見るだけで全候補が分かる。

#### 7. タイムゾーン定義（`timezones.py` または `config.py` 内）

**何のために**：「DB は UTC、表示は JST」のような**時刻取り扱いポリシー**を 1 箇所に固定するため。

`zoneinfo.ZoneInfo("Asia/Tokyo")` を各所で書き散らすと、誤って UTC のまま画面に出す事故が起きる。
core/ に「JST = ZoneInfo('Asia/Tokyo')」のような定数を置き、表示時の変換は必ずこれを使うルールにすると一貫する。

### 🔴 このプロジェクトでは使わなさそうなパターン

参考までに「core/ に置くケースがあるけどこのプロジェクトでは出番がない」パターンも挙げておく。

#### 1. DI コンテナ（`dependency-injector` / `punq` 等）

**何のために**：Spring / Angular 風の本格的な依存性注入コンテナを使い、サービスの組み立てを宣言的に書くため。

このプロジェクトは **FastAPI の `Depends` で完結**するため、別途 DI ライブラリは導入しない。

#### 2. メッセージブローカー抽象（`MessageBus` / `EventBus`）

**何のために**：RabbitMQ / Kafka / SNS 等の複数メッセージブローカーを差し替え可能に抽象化するため。

このプロジェクトのジョブキューは **Postgres + LISTEN/NOTIFY** で完結しており、ブローカー切替の要件がないため不要（[ADR 0004](../../../../docs/adr/0004-postgres-as-job-queue.md)）。

#### 3. KMS / 鍵管理サービス抽象

**何のために**：AWS KMS / Vault 等で暗号鍵を厳密に管理し、ローテーションを自動化するため。

このプロジェクト規模では `.env` の環境変数で十分。本番デプロイ時も AWS SSM Parameter Store / Secrets Manager で完結する。

#### 4. メール送信抽象（`MailService`）

**何のために**：SendGrid / SES / Postmark 等のメール送信プロバイダを差し替え可能に抽象化するため。

このプロジェクトは MVP 段階でメール通知機能を持たない（[.claude/rules/backend.md](../../../../.claude/rules/backend.md) に明記）。R6 以降で必要になれば導入する。

#### 5. キャッシュ抽象レイヤ（`Cache` インタフェース）

**何のために**：Redis / Memcached / インメモリ等のキャッシュ実装を差し替え可能に抽象化するため。

このプロジェクトは Redis 1 つに固定する前提（キャッシュ・セッション・レート制限の用途）で、複数キャッシュ実装を切り替える要件がない。`redis-py` を直接使えば足りるため、抽象レイヤは導入しない。

#### 6. マルチテナント設定（`TenantContext`）

**何のために**：1 つのアプリが複数の組織のデータを扱う時、リクエストごとに「どの組織か」を決定するため。

このプロジェクトは個人ユーザー単位の単一テナントのため不要。

#### 7. ロケール / i18n 基盤

**何のために**：英語・日本語・中国語など複数言語のメッセージファイルを管理し、ユーザーの言語設定に応じて切り替えるため。

このプロジェクトは日本語のみで運用するため不要。

#### 8. 機能フラグ（`FeatureFlags` / LaunchDarkly 抽象）

**何のために**：「特定ユーザーだけに新機能を見せる」「機能を即座にオフにする」をコード変更なしで行うため。

このプロジェクトは個人開発で A/B テストや段階リリースを行わないため不要。必要になれば DB の `users.flags` JSONB で十分。

#### 9. 監査ログ機構（`AuditLogger`）

**何のために**：誰がいつ何を変更したか、を法令遵守目的で全て記録するため。

このプロジェクトは個人学習用途で監査要件がないため不要。Loki への通常ログで十分。

## core/ の機能まとめ（カテゴリ別）

| カテゴリ | 何のために | 例 |
|---|---|---|
| **設定値の集約** | 散らばりがちな環境変数を 1 箇所に集めて型検証する | `Settings`（DB URL / OAuth キー / Redis URL） |
| **例外の定義** | 業務エラーを HTTP に依存せず表現する | `ResourceNotFoundError` / `PermissionDeniedError` |
| **暗号 / 署名の道具** | 鍵を 1 箇所に集めて改ざん検知の仕組みを提供 | Cookie 署名（`itsdangerous`）／ OAuth state 検証 |
| **外部サービスのクライアント設定** | 外部 API を呼ぶ準備（接続情報・スコープ）を集中管理 | `GitHubOAuthClient` |
| **共通レスポンス / 定数** | 全 API で共通の形を 1 度だけ定義する | `Page[T]` / `PaginationMeta` / 状態名定数 |
| **時刻 / タイムゾーン** | 「DB は UTC、表示は JST」を 1 箇所で固定 | `JST = ZoneInfo("Asia/Tokyo")` |

## 置くもの

- `config.py`：`.env` から読み込んだ設定値（DB URL / OAuth キー / Redis URL 等）
- `security.py`（予定）：セッション署名 / OAuth クライアントの構築
- `exceptions.py`（予定）：ドメイン例外クラス + HTTP エラー変換ハンドラ

置かないもの：機能ごとの業務ロジック（それは [services/](../services/README.md) に書く）。
