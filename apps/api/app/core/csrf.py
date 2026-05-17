# このファイルの役割：
#   状態変更系（POST / PUT / DELETE / PATCH）の API に対して、double submit cookie
#   方式の CSRF 検証を行う Starlette middleware を提供する。
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

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core import session as session_store
from app.core.config import get_settings
from app.core.redis import get_redis

# CSRF 検証対象の HTTP メソッド。
# GET / HEAD / OPTIONS は仕様上副作用なしのためスキップ。
_PROTECTED_METHODS = frozenset({"POST", "PUT", "DELETE", "PATCH"})

# CSRF 検証から除外するパス。
# OAuth コールバックは外部からの top-level GET（厳密には POST にはならない想定）だが、
# 念のため明示的に exempt にしておく。state トークンで別途防御済み。
_EXEMPT_PATHS: frozenset[str] = frozenset(
    {
        "/auth/github",
        "/auth/github/callback",
    }
)

# ヘッダー名は固定（Frontend と合わせる、02-api-conventions.md）。
_HEADER_NAME = "X-CSRF-Token"


class CSRFMiddleware(BaseHTTPMiddleware):
    """double submit cookie 方式の CSRF 検証 middleware。

    マウント方法（main.py）::

        app.add_middleware(CSRFMiddleware)

    検証ロジック：
      - GET / HEAD / OPTIONS はスキップ
      - 除外パス（/auth/github 系）はスキップ
      - Cookie の sid が無い場合：Redis セッション未確立なので 401 を返す
        （未ログインで POST するのが筋違い）
      - sid → Redis に問い合わせて csrf_token を取得
      - X-CSRF-Token ヘッダーと一致しない / 欠落していれば 403
    """

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.method not in _PROTECTED_METHODS:
            return await call_next(request)

        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        settings = get_settings()
        sid = request.cookies.get(settings.session_cookie_name)
        if not sid:
            return _json_error(
                401,
                "認証が必要です",
            )

        redis = get_redis()
        session = await session_store.get(redis, sid)
        if session is None:
            return _json_error(
                401,
                "セッションが無効です。再度ログインしてください",
            )

        header_token = request.headers.get(_HEADER_NAME)
        if not header_token or header_token != session.csrf_token:
            return _json_error(
                403,
                "CSRF トークンが一致しません",
            )

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
