# このファイルの役割：
#   環境変数 / .env ファイルから設定値を読み込んで、型付き（str / int 等）で提供する共通モジュール。
#   プロジェクトに 1 個だけ用意して、session.py / 認証 / ロガー等の全体で使い回す。
#   新機能追加時にこのファイルを編集することは少なく、get_settings() を呼んで参照するだけ。
#   設定項目を増やしたい時のみ Settings クラスにフィールドを追加する。

# lru_cache: Python 標準（functools）。関数の結果をメモリにキャッシュするデコレータ。
#            2 回目以降の呼び出しは同じ結果を即返す（中の処理は再実行されない）。
from functools import lru_cache

# Field: Pydantic が提供する関数。フィールドにデフォルト値 / 説明文等のメタデータを付ける。
from pydantic import Field

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
