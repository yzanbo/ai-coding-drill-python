# このファイルの役割：
#   Redis に非同期で接続するクライアントを「アプリ全体で 1 個だけ」用意し、
#   FastAPI のリクエスト処理から使えるように依存性注入（Depends）の関数も提供する。
#
#   用途は cache / session / rate limit（ジョブキュー用途では使わない、ADR 0005）。
#   今は GitHub OAuth ログインの state トークンとセッション本体の保存先として使う。
#
# 設計：
#   - アプリ起動時（main.py の lifespan）に open_redis() で接続を 1 回作る
#   - 各リクエストでは get_redis() を Depends で呼んで使い回す（新規接続を作らない）
#   - アプリ終了時に close_redis() でコネクションを解放する
#   - redis-py の Redis オブジェクトは内部に接続プールを持っているので、
#     アプリ全体で 1 個共有して問題ない（DB 用 AsyncEngine と同じ思想）。

# redis.asyncio.Redis（redis-py >=5）:
#   redis 非同期クライアントの本体クラス。内部に接続プールを持ち、
#   await を付けて get / set / hset / expire 等のコマンドを実行できる。
from redis.asyncio import Redis

# get_settings: .env / 環境変数から読み込んだ設定をまとめて返す関数（中身は config.py）。
from app.core.config import get_settings

# _client（先頭 _ は「このファイル内だけで使う印」）:
#   Redis クライアントを保持するモジュール変数。
#   None で初期化し、open_redis() で値が入る。get_redis() で取り出す時に
#   None ならエラーを出して「lifespan を通っていない」ミスを早期検知する。
_client: Redis | None = None


# open_redis: 起動時に 1 回だけ呼ぶ「Redis 接続を開く」関数。
#   FastAPI の lifespan（main.py で設定）から起動直後に呼ばれる。
#   2 回目以降の呼び出しは既存クライアントをそのまま返す（多重接続を防ぐ）。
async def open_redis() -> Redis:
    """アプリ起動時に Redis クライアントを 1 個作って保持する。

    - 既に開いている場合は同じインスタンスを返す（idempotent）
    - 戻り値の `Redis` は内部に接続プールを持つので、アプリ全体で使い回せる
    """
    # global _client: この関数の中から「モジュール変数 _client」を書き換える宣言。
    #   global を書かないと、関数内で _client = ... と書いた瞬間に新しいローカル変数が
    #   作られてモジュール変数は変わらないため、明示する必要がある。
    global _client
    if _client is not None:
        return _client

    settings = get_settings()
    # Redis.from_url:
    #   redis://... 形式の URL からクライアントを作るショートカット。
    #   decode_responses=True:
    #     コマンドの戻り値を str として返してもらう設定（bytes ではなく）。
    #     セッション ID / state トークン / CSRF トークン等の文字列を扱うので便利。
    #     binary を扱いたいキーがあれば、その時だけ別クライアントを用意する。
    #   max_connections は redis-py 既定（50）で十分なので明示しない。
    _client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


# close_redis: 終了時に 1 回だけ呼ぶ「Redis 接続を閉じる」関数。
#   FastAPI の lifespan からアプリ停止時に呼ばれる。
async def close_redis() -> None:
    """アプリ終了時にコネクションを解放する。"""
    global _client
    if _client is None:
        return
    # aclose（async close）: 非同期で接続プール全体を閉じる。
    #   redis-py 5.x で .close() の後継として推奨されている呼び方。
    await _client.aclose()
    _client = None


# get_redis: 各リクエストから Redis を使うときに呼ぶ依存性注入用の関数。
#   FastAPI の Depends と組み合わせて使う：
#     async def handler(redis: Annotated[Redis, Depends(get_redis)]):
#         await redis.set(...)
#
#   get_async_session（db/session.py）と違って async with でくるまない理由：
#     - DB セッションは「リクエスト単位の使い捨て」が前提（commit / rollback）
#     - Redis クライアントは「接続プールを内包した長生きオブジェクト」で
#       各コマンドが自前で接続を借りて返すため、リクエスト境界で開閉する必要がない
def get_redis() -> Redis:
    """FastAPI 依存性注入用：起動時に作っておいた Redis クライアントを返す。

    使い方（Annotated 形式、B008 ruff 規約に準拠）：
        RedisDep = Annotated[Redis, Depends(get_redis)]

        @router.get("/...")
        async def handler(redis: RedisDep):
            await redis.set("key", "value")
    """
    if _client is None:
        # lifespan を通らずに get_redis を呼んだ場合のフェイルファスト。
        # テストで lifespan を起動し忘れた等の問題を即座に発見できる。
        raise RuntimeError(
            "Redis client is not initialized. Call open_redis() in app lifespan first."
        )
    return _client
