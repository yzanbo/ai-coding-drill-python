# このファイルの役割：
#   認証関連の 4 エンドポイントを束ねた APIRouter。
#
#   - GET  /auth/github           : OAuth 開始（GitHub の認可画面へリダイレクト）
#   - GET  /auth/github/callback  : OAuth コールバック（code 検証 → セッション作成）
#   - GET  /auth/me               : 現在ユーザー情報を返す
#   - POST /auth/logout           : セッション破棄
#
# 関わる要件：
#   - docs/requirements/4-features/authentication.md §1.4 / §2.3 / §2.4 / §2.5

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import state_store
from app.core.config import get_settings
from app.core.cookies import sign_sid, unsign_sid
from app.core.redis import get_redis
from app.db.session import get_async_session
from app.deps.auth import get_current_user
from app.models.users import User
from app.schemas.auth import AuthErrorKind, UserResponse
from app.services.auth import AuthService
from app.services.github_oauth import GitHubOAuthClient, GitHubOAuthError

router = APIRouter(prefix="/auth", tags=["auth"])

# DI エイリアス。Annotated + Depends を毎回書くと冗長なのでまとめる。
DbDep = Annotated[AsyncSession, Depends(get_async_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# ?next= の許容ルール：authentication.md §2.5
#   - 同一オリジンの相対パスのみ許容（"/" で始まる）
#   - "//evil.com" 形式（protocol-relative URL）と "http(s)://..." は拒否
#   - 拒否時はエラーを出さず黙ってホーム "/" にフォールバック
#
# このプロジェクトのフロント URL は frontend_base_url で固定なので、安全な next を
# そのまま Frontend オリジン上のパスとして展開する。
def _safe_next_path(next_query: str | None) -> str:
    """next= クエリを検証して安全な相対パスを返す。無効ならホーム "/" にフォールバック。"""
    if not next_query:
        return "/"
    # 異常に長い next は拒否（ログ汚染やヘッダー注入回避の軽い前段フィルタ）。
    if len(next_query) > 2048:
        return "/"
    # protocol-relative（//evil.com）は拒否。
    if next_query.startswith("//"):
        return "/"
    # 絶対パスは拒否（オープンリダイレクト防止）。
    if not next_query.startswith("/"):
        return "/"
    return next_query


def _absolute_frontend_url(path: str) -> str:
    """frontend_base_url に相対パスを連結して絶対 URL を返す。

    Backend は Frontend と別オリジン（既定 :8000 と :3000）なので、リダイレクトは
    Frontend の絶対 URL を返す必要がある。
    """
    base = get_settings().frontend_base_url.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return base + path


# Cookie 関連のヘルパ。設定と分岐を 1 箇所に集約してミスを減らす。
def _set_session_cookies(
    response: Response,
    *,
    sid: str,
    csrf_token: str,
) -> None:
    """ログイン成功時に sid Cookie（HttpOnly）と csrf_token Cookie（JS 可読）を発行。"""
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=sign_sid(sid),
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=settings.session_ttl_seconds,
        httponly=False,  # Frontend が JS で読んで X-CSRF-Token ヘッダーに詰めるため
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_session_cookies(response: Response) -> None:
    """ログアウト時に両 Cookie を Max-Age=0 で消す。"""
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=False,
        samesite="lax",
    )


# ----------------------------------------------------------------------------
# GET /auth/github : OAuth 開始
# ----------------------------------------------------------------------------
@router.get(
    "/github",
    status_code=status.HTTP_302_FOUND,
    # response_model を None にして OpenAPI には「302 リダイレクト」だけが見えるようにする。
    # RedirectResponse は body を持たないため response_model を付けるとスキーマ不一致になる。
    responses={302: {"description": "GitHub 認可画面へリダイレクト"}},
)
async def start_github_oauth(
    redis: RedisDep,
    next_: Annotated[str | None, Query(alias="next")] = None,
) -> RedirectResponse:
    """OAuth フロー開始。state を発行し GitHub の認可画面へ 302 リダイレクトする。

    クエリ:
      - next: ログイン後の戻り先（同一オリジン相対パスのみ）。callback 時に使うため
              state と一緒に Redis に格納する… のが理想だが、現状の state_store は
              値を持たない設計のため、Cookie に一時格納する方式を取る（HttpOnly + Lax）。
    """
    state = await state_store.issue(redis)
    client = GitHubOAuthClient()
    authorize_url = client.build_authorize_url(state=state)

    response = RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)
    # next を Cookie に一時保管（短命 = state と同じ 10 分）。
    # クライアントオリジンの相対パスのみ許容済み。
    safe_next = _safe_next_path(next_)
    settings = get_settings()
    if safe_next != "/":
        response.set_cookie(
            key="auth_next",
            value=safe_next,
            max_age=settings.state_ttl_seconds,
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            path="/",
        )
    return response


# ----------------------------------------------------------------------------
# GET /auth/github/callback : OAuth コールバック
# ----------------------------------------------------------------------------
@router.get(
    "/github/callback",
    status_code=status.HTTP_302_FOUND,
    responses={302: {"description": "ログイン成功はホーム /、失敗は /login へリダイレクト"}},
)
async def github_callback(
    request: Request,
    db_session: DbDep,
    redis: RedisDep,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """GitHub からのコールバック。

    成功時：Set-Cookie で sid / csrf_token を発行してホーム（または ?next= 指定先）へ 302。
    state 不一致 / 期限切れ / 再使用：/login?auth_error=state_invalid へ 302。
    GitHub が ?error= を返した時：/login?auth_error=oauth_canceled へ 302。
    その他例外：/login?auth_error=oauth_failed へ 302。
    """
    # 1. GitHub が ?error= で戻してきたケース（ユーザーが Cancel 等）。
    #    code は来ない想定。state は来ても来なくても /login へ戻すだけ。
    if error:
        return _redirect_to_login_with_error(AuthErrorKind.OAUTH_CANCELED)

    # 2. code / state が揃っていることを確認。
    if not code or not state:
        return _redirect_to_login_with_error(AuthErrorKind.STATE_INVALID)

    # 3. state を Redis から検証 + 消費（1 回使い切り）。
    if not await state_store.verify_and_consume(redis, state):
        return _redirect_to_login_with_error(AuthErrorKind.STATE_INVALID)

    # 4. code を GitHub に投げてユーザー情報を取得。
    client = GitHubOAuthClient()
    try:
        user_input = await client.exchange_code(code=code)
    except GitHubOAuthError:
        return _redirect_to_login_with_error(AuthErrorKind.OAUTH_FAILED)

    # 5. upsert + セッション作成。
    service = AuthService(db_session, redis)
    created = await service.login_with_github(user_input)

    # 6. リダイレクト先：auth_next Cookie を優先、無ければホーム /。
    next_cookie = request.cookies.get("auth_next")
    target_path = _safe_next_path(next_cookie)
    target_url = _absolute_frontend_url(target_path)

    response = RedirectResponse(url=target_url, status_code=status.HTTP_302_FOUND)
    _set_session_cookies(response, sid=created.sid, csrf_token=created.csrf_token)
    # auth_next は使い切ったので削除。
    response.delete_cookie(key="auth_next", path="/")
    return response


def _redirect_to_login_with_error(kind: str) -> RedirectResponse:
    """/login?auth_error=<種別> に戻す（Frontend がトーストを出す前提）。"""
    url = _absolute_frontend_url(f"/login?auth_error={kind}")
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


# ----------------------------------------------------------------------------
# GET /auth/me : 現在ユーザー情報
# ----------------------------------------------------------------------------
@router.get("/me", response_model=UserResponse)
async def get_me(user: CurrentUser) -> User:
    """ログイン中のユーザー情報を返す。未認証なら 401（get_current_user が投げる）。"""
    return user


# ----------------------------------------------------------------------------
# POST /auth/logout : セッション破棄
# ----------------------------------------------------------------------------
@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={204: {"description": "ログアウト成功（ボディなし）"}},
)
async def logout(
    request: Request,
    redis: RedisDep,
    db_session: DbDep,
    response: Response,
    # 認証必須にすると未認証時 401。CSRF middleware が先に通過済み（POST 経由）。
    _user: CurrentUser,
) -> Response:
    """セッションを破棄し、Cookie を Max-Age=0 で消す。

    - 内部的に Redis から `session:<sid>` を DELETE + `user:<id>:sessions` から SREM
    - 204 No Content（ボディなし）。Cookie だけがレスポンスヘッダーに残る
    """
    settings = get_settings()
    signed = request.cookies.get(settings.session_cookie_name)
    sid = unsign_sid(signed) if signed else None

    if sid:
        service = AuthService(db_session, redis)
        await service.logout(sid)

    # 念のため Redis 側で消えなかった場合も Cookie はクリアする。
    _clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
