# このファイルの役割：
#   環境変数 / .env ファイルから設定値を読み込んで、型付き（str / int 等）で提供する共通モジュール。
#   プロジェクトに 1 個だけ用意して、session.py / 認証 / ロガー等の全体で使い回す。
#   新機能追加時にこのファイルを編集することは少なく、get_settings() を呼んで参照するだけ。
#   設定項目を増やしたい時のみ Settings クラスにフィールドを追加する。

# lru_cache: Python 標準（functools）。関数の結果をメモリにキャッシュするデコレータ。
#            2 回目以降の呼び出しは同じ結果を即返す（中の処理は再実行されない）。
from functools import lru_cache

# Field: Pydantic が提供する関数。フィールドにデフォルト値 / 説明文等のメタデータを付ける。
# model_validator: モデル全体の妥当性検証（複数フィールドにまたがる組み合わせチェック）に使う。
#   ここでは「本番環境なのに開発用既定値が残っていないか」を起動時に弾く用途。
from pydantic import Field, model_validator

# pydantic-settings（pydantic 公式の姉妹パッケージ）が提供する部品：
# BaseSettings:       環境変数 / .env から自動でフィールドを埋める基底クラス。
#                     継承するだけで「環境変数を読み込む設定クラス」になる。
# SettingsConfigDict: BaseSettings 用の設定を書く型（読み込み元の .env パス等を指定）。
from pydantic_settings import BaseSettings, SettingsConfigDict


# Settings: このプロジェクトで使う設定値をまとめたクラス（自作）。
#   BaseSettings を継承すると、フィールド名と同じ環境変数（大文字でも可）から
#   自動で値が埋まる。例：database_url ← DATABASE_URL
class Settings(BaseSettings):
    # model_config: BaseSettings の振る舞いを設定するクラス変数。
    #   env_file:          読み込む .env ファイルのパス（プロジェクトルート相対）。
    #   env_file_encoding: .env の文字コード。
    #   extra="ignore":    Settings クラスに未定義の環境変数があってもエラーにせず無視する。
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # app_env: 実行環境の名前。"dev" / "test" / "staging" / "production"。
    #   本番起動時に「開発用の既定値（dev-only-change-me / COOKIE_SECURE=false 等）」
    #   が残っていないかを起動時にチェックするためのフラグ。
    #   .env で APP_ENV=production を指定すると安全装置が有効化される。
    app_env: str = Field(
        default="dev",
        description="実行環境名（dev / test / staging / production）",
    )

    # Field（Pydantic が提供）:
    #   フィールドにメタデータ（デフォルト値 / 説明文 / バリデーション制約等）を付ける関数。
    #   `name: 型 = デフォルト値` の代わりに
    #   `name: 型 = Field(default=..., description=...)` と書くと、
    #   - デフォルト値を明示できる
    #   - 説明文を付けられる（OpenAPI ドキュメントや IDE のツールチップに表示される）
    #   - 数値の最小/最大値、文字列長、正規表現等の制約も指定できる（例：Field(ge=0, le=100)）
    #
    #   よく使う引数：
    #     default:     デフォルト値
    #     description: 説明文（OpenAPI / Swagger UI に表示される）
    #     ge / le:     >= / <=（数値制約）
    #     min_length / max_length: 文字列長制約
    #     pattern:     正規表現制約
    #
    # database_url: SQLAlchemy が DB に繋ぐための接続文字列。
    #   .env に DATABASE_URL=... があればその値、なければ下の default を使う。
    #   形式：postgresql+asyncpg://<user>:<pass>@<host>:<port>/<dbname>
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/ai_coding_drill",
        description="SQLAlchemy async URL（postgresql+asyncpg://...）",
    )
    # redis_url: Redis に繋ぐための接続文字列。
    #   キャッシュ / セッション / レート制限の保存先として使う（ジョブキューには使わない）。
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis 接続 URL（cache / session / rate limit 用）",
    )

    # ----- GitHub OAuth 用 -----
    # GitHub の OAuth アプリ（https://github.com/settings/developers で作成）から
    # 払い出される ID / Secret。ローカル開発と本番で別アプリを作って .env に入れる。
    # 値はリポジトリに含めない（必ず .env 経由）。
    github_client_id: str = Field(
        default="",
        description="GitHub OAuth App の Client ID",
    )
    github_client_secret: str = Field(
        default="",
        description="GitHub OAuth App の Client Secret",
    )
    # github_redirect_uri: GitHub 認可後に戻ってくる URL。OAuth App 設定の
    #   Authorization callback URL と完全一致する必要がある。
    github_redirect_uri: str = Field(
        default="http://localhost:8000/auth/github/callback",
        description="GitHub OAuth コールバック URL（GitHub App 設定と一致させる）",
    )

    # ----- セッション / Cookie -----
    # session_cookie_name: 自己ドキュメント性を優先して `session_id`（ADR 0047 の改訂方針）。
    #   主防御は HttpOnly / Secure / SameSite / 不透明値 / CSRF / 署名で完結しており、
    #   Cookie 名の obscurity に依存しない。
    session_cookie_name: str = Field(
        default="session_id",
        description="セッション ID を入れる Cookie 名",
    )
    # csrf_cookie_name: CSRF トークンを入れる別 Cookie。Frontend が JS で読むため
    #   こちらは HttpOnly を付けない（→ 02-api-conventions.md の CSRF 節）。
    csrf_cookie_name: str = Field(
        default="csrf_token",
        description="CSRF トークンを入れる Cookie 名（HttpOnly なし）",
    )
    # session_ttl_seconds: Redis 上のセッション有効期限（7 日、ADR 0047）。
    session_ttl_seconds: int = Field(
        default=604800,
        description="セッション TTL（秒）。既定 7 日",
    )
    # state_ttl_seconds: OAuth state トークン TTL（10 分、authentication.md §1.3）。
    state_ttl_seconds: int = Field(
        default=600,
        description="OAuth state トークン TTL（秒）。1 回使い切り",
    )
    # cookie_secure: True の時 Cookie は HTTPS でのみ送信される。
    #   本番は必ず True、ローカル http 開発時のみ False にする。
    cookie_secure: bool = Field(
        default=False,
        description="Cookie の Secure 属性（本番は True、ローカル http なら False）",
    )
    # session_signing_secret: itsdangerous で Cookie 値を署名する鍵。
    #   本番は十分長いランダム文字列を .env から渡す。
    session_signing_secret: str = Field(
        default="dev-only-change-me",
        description="セッション Cookie 署名用シークレット（itsdangerous）",
    )

    # ----- Frontend オリジン -----
    # frontend_base_url: ログイン後リダイレクト等で使うフロントの起点 URL。
    #   ?next= の同一オリジン検証では Backend ルート相対パスを優先するため、
    #   主にホーム / と /login への絶対 URL 組み立てに利用する。
    frontend_base_url: str = Field(
        default="http://localhost:3000",
        description="Frontend の起点 URL",
    )

    # 本番デフォルト値の事故余地を起動時に弾く安全装置。
    # APP_ENV=production の時のみ厳しくチェックする：
    #   - SESSION_SIGNING_SECRET が "dev-only-change-me" のままなら起動拒否
    #     （Cookie 署名鍵が予測可能 = セッション偽造可能になるため）
    #   - COOKIE_SECURE=false のままなら起動拒否
    #     （http で Cookie が送られてセッション盗難リスクが上がるため）
    # dev / test / staging では緩く、開発しやすさを優先する。
    @model_validator(mode="after")
    def _check_production_safety(self) -> Settings:
        if self.app_env != "production":
            return self
        if self.session_signing_secret == "dev-only-change-me":
            raise ValueError(
                "SESSION_SIGNING_SECRET must be set to a strong random value "
                "when APP_ENV=production (current value is the dev placeholder)."
            )
        if not self.cookie_secure:
            raise ValueError(
                "COOKIE_SECURE must be true when APP_ENV=production "
                "(http で Cookie が送られるとセッション盗難リスクが上がるため)."
            )
        return self


# @lru_cache（Python 標準 / functools が提供）:
#   関数の戻り値をメモリに**キャッシュ**するデコレータ。
#   lru = Least Recently Used（最近使われていないものから捨てる）方式のキャッシュ。
#   同じ引数で関数を呼ぶと、2 回目以降は中の処理を再実行せず、保存済みの戻り値をそのまま返す。
#
#   挙動：
#     - 引数の組み合わせをキーにして戻り値を保存（タプルでハッシュ化）
#     - 引数なしの関数の場合は、初回の戻り値を 1 個だけ覚えて、以後はそれを返す
#     - maxsize= で上限指定可能（デフォルト 128）。@lru_cache（引数なし）または @lru_cache() で OK
#
#   制御メソッド（デコレータが関数に追加で生やす）：
#     - get_settings.cache_clear() : キャッシュを全消去（テスト時に使う）
#     - get_settings.cache_info()  : ヒット率等の統計を取得
#
#   他言語との対応：JavaScript の memoize / Ruby の Memoize / Java の Caffeine 等と
#   同じ「メモ化」概念。
#
# get_settings: Settings インスタンスをキャッシュ付きで返す関数。
#   @lru_cache が付いているので、初回呼び出し時だけ Settings() を作って .env を読み込み、
#   2 回目以降は同じインスタンスを即返す（.env を毎回読み直さない）。
#
# なぜ関数で包むのか：
#   - キャッシュをかけて起動コストを抑える
#   - テスト時に get_settings.cache_clear() でリセットしたり、依存性注入で差し替えやすい
#   - import 時に評価せず、必要な時に評価する（遅延初期化）
@lru_cache
def get_settings() -> Settings:
    return Settings()
