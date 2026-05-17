# このファイルの役割：
#   外部 API（GitHub OAuth 等）を叩く時に使う非同期 HTTP クライアントを
#   「アプリ全体で 1 個だけ」用意する。
#
#   1 リクエストごとに httpx.AsyncClient を新規作成すると、内部の接続プール
#   （TCP コネクション）が毎回張り直されてオーバーヘッドになる。共有 1 個に
#   すると pool が再利用され、外部 API へのレイテンシが下がる。
#
# 設計：
#   - アプリ起動時（main.py の lifespan）に open_http_client() で 1 回作る
#   - 各サービス層では get_http_client() で取り出して使い回す
#   - アプリ終了時に close_http_client() で接続を解放する
#   - パターンは core/redis.py と揃える

# httpx: 非同期 HTTP クライアント。
import httpx

# _client: モジュール変数で 1 個だけ持つ（先頭 _ は「ファイル内だけで使う印」）。
_client: httpx.AsyncClient | None = None

# timeout: 接続 / 読み / 書き / pool 待ちを別々に上限指定。
#   GitHub API などの外部呼び出しで、現象別に切り分けたいため。
_DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=2.0)


# open_http_client: 起動時に 1 回だけ呼ぶ。
async def open_http_client() -> httpx.AsyncClient:
    """アプリ起動時に httpx.AsyncClient を 1 個作って保持する。

    - 既に開いている場合は同じインスタンスを返す（idempotent）
    - 戻り値の AsyncClient は内部に接続プールを持つので、アプリ全体で
      使い回せる
    """
    # global _client: モジュール変数 _client を書き換える宣言。
    global _client
    if _client is not None:
        return _client
    _client = httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT)
    return _client


# close_http_client: 終了時に 1 回だけ呼ぶ。
async def close_http_client() -> None:
    """アプリ終了時に接続を解放する。"""
    global _client
    if _client is None:
        return
    await _client.aclose()
    _client = None


# get_http_client: 各サービス層から使うときに呼ぶ。
def get_http_client() -> httpx.AsyncClient:
    """起動時に作っておいた共有クライアントを返す。

    lifespan を通っていない場合は RuntimeError を投げて早期検知する
    （テストで lifespan を起動し忘れた等のミスをログから判別可能にする）。
    """
    if _client is None:
        raise RuntimeError(
            "HTTP client is not initialized. "
            "Call open_http_client() in app lifespan first."
        )
    return _client
