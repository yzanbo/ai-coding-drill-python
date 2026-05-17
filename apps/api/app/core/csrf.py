# このファイルの役割：
#   状態変更系（POST / PUT / DELETE / PATCH）の API に対して、double submit cookie
#   方式の CSRF 検証を行う ASGI middleware（関数形式）を提供する。
#
#   フロー：
#     1. ログイン時に SessionStore が `csrf_token` を Redis のセッション hash に保存し、
#        同時に `csrf_token` Cookie（HttpOnly なし）として配信する
#     2. Frontend は状態変更リクエストを送る時に Cookie の値をコピーして
#        `X-CSRF-Token` ヘッダーに付ける
#     3. 本 middleware は Cookie の sid → Redis セッション → 保存済み csrf_token を
#        引き、X-CSRF-Token ヘッダーと一致するか検証する
#
# 関わる要件：
#   - docs/requirements/3-cross-cutting/02-api-conventions.md「CSRF 対策（double submit cookie）」
#   - docs/adr/0047-session-store-on-redis.md §CSRF 対策
#
# 実装メモ：
#   FastAPI の @app.middleware("http") デコレータで登録する関数形式を採用する。
#   starlette の BaseHTTPMiddleware を継承するクラス形式もあるが、deptry の DEP003
#   （transitive dependency 直接 import）を避けるため fastapi.Request /
#   fastapi.Response 経由で揃える。

import hmac
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.core import session as session_store
from app.core.config import get_settings
from app.core.cookies import unsign_sid
from app.core.redis import get_redis

# CSRF 検証対象の HTTP メソッド。
# GET / HEAD / OPTIONS は仕様上副作用なしのためスキップ。
_PROTECTED_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})

# CSRF 検証から除外するパス。
# - /auth/github/callback：OAuth コールバック。state トークンで別途防御済み
#   （仕様 SSoT: 02-api-conventions.md の CSRF 対策節）。
#   OAuth 2.0（RFC 6749 §3.1.2）/ GitHub の redirect_uri は GET 固定で
#   POST 化されることはないため、ここでの個別列挙は仕様意図の明示として残す
#   （exempt が無くても GET 規則で素通りするので挙動同一）。
# - /health：疎通確認用の public POST。DB 接続生存確認のため認証不要、
#   行を 1 つ insert するだけで副作用が事実上ないため CSRF も不要
#   （/healthz / /readyz は GET なので _PROTECTED_METHODS で素通り）
_EXEMPT_PATHS: frozenset[str] = frozenset(
    {
        "/auth/github/callback",
        "/health",
    }
)

# ヘッダー名は固定（Frontend と合わせる、02-api-conventions.md）。
_HEADER_NAME = "X-CSRF-Token"

# 型エイリアス：FastAPI の middleware 関数のシグネチャ。
# call_next は次の handler を呼ぶ非同期関数で、Response を返す。
_CallNext = Callable[[Request], Awaitable[Response]]


async def verify_csrf(request: Request, call_next: _CallNext) -> Response:
    """double submit cookie 方式の CSRF 検証関数 middleware。

    使い方（main.py）::

        app.middleware("http")(verify_csrf)
        # または
        @app.middleware("http")
        async def csrf_middleware(request, call_next):
            return await verify_csrf(request, call_next)

    検証ロジック：
      - GET / HEAD / OPTIONS はスキップ
      - 除外パス（/auth/github 系）はスキップ
      - Cookie の sid が無い / 署名が無効：401（未ログインで POST するのが筋違い）
      - sid → Redis に問い合わせて csrf_token を取得（セッション期限切れなら 401）
      - X-CSRF-Token ヘッダーと一致しない / 欠落していれば 403
    """
    if request.method not in _PROTECTED_METHODS:
        return await call_next(request)

    if request.url.path in _EXEMPT_PATHS:
        return await call_next(request)

    settings = get_settings()
    signed = request.cookies.get(settings.session_cookie_name)
    if not signed:
        return _json_error(401, "認証が必要です")

    # 署名検証に失敗した時は未認証として扱う（Redis に問い合わせる前に弾く）。
    sid = unsign_sid(signed)
    if sid is None:
        return _json_error(401, "セッションが無効です。再度ログインしてください")

    redis = get_redis()
    session = await session_store.get(redis, sid)
    if session is None:
        return _json_error(401, "セッションが無効です。再度ログインしてください")

    header_token = request.headers.get(_HEADER_NAME)
    # hmac.compare_digest: 文字列を 1 文字ずつ「最後まで」比較する関数。
    #   普通の == は早期に return するので、一致した文字数で処理時間が変わる
    #   （タイミング攻撃で 1 文字ずつ正解を推測される余地ができる）。
    #   CSRF トークンは 256 bit の CSPRNG で実害は極小だが、秘密値の比較は
    #   プロジェクト全体で constant-time に揃える（itsdangerous も内部で同じ関数を使う）。
    if not header_token or not hmac.compare_digest(header_token, session.csrf_token):
        return _json_error(403, "CSRF トークンが一致しません")

    # 検証通過。下流のハンドラに進む。
    return await call_next(request)


def _json_error(status_code: int, message: str) -> JSONResponse:
    """middleware からエラーレスポンスを返す時の共通組み立て。

    本来は core/exceptions.py の RFC 7807 形式に揃えるべきだが、
    本 middleware はハンドラより前に走るため、最小限の JSON でクライアントに返す。
    後で例外ハンドラ整備時に共通化する。
    """
    return JSONResponse(
        status_code=status_code,
        content={"detail": message},
    )
