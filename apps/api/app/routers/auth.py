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

from app.core import session as session_store
from app.core import state_store
from app.core.config import get_settings
from app.core.cookies import sign_sid, unsign_sid
from app.core.redis import get_redis
from app.core.session import Session
from app.db.session import get_async_session
from app.deps.auth import get_current_session, get_current_user
from app.models.users import User
from app.schemas.auth import AuthErrorKind, UserResponse
from app.services.auth import AuthService
from app.services.github_oauth import GitHubOAuthClient, GitHubOAuthError

router = APIRouter(prefix="/auth", tags=["auth"])

# DI エイリアス。Annotated + Depends を毎回書くと冗長なのでまとめる。
DbDep = Annotated[AsyncSession, Depends(get_async_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentSession = Annotated[Session | None, Depends(get_current_session)]


# ?next= の許容ルール：authentication.md §2.5
#   - 同一オリジンの相対パスのみ許容（"/" で始まる）
#   - "//evil.com" 形式（protocol-relative URL）と "http(s)://..." は拒否
#   - 拒否時はエラーを出さず黙ってホーム "/" にフォールバック
#
# FE 側にも同じ業務ルールの実装あり: apps/web/src/lib/utils/safe-next-path.ts。
# 片方を変えたら必ずもう片方も更新する（business rule の重複実装は
# authentication.md §2.5 を SSoT としている）。
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
    # domain= は本番で API / Frontend をサブドメインで分ける構成のためのオプション。
    # 未指定（None）なら host-only Cookie（発行ホストのみ）になる。set_cookie /
    # delete_cookie の domain が一致しないと delete が効かず Cookie が残る既知の罠が
    # あるため、両者で必ず同じ settings.cookie_domain を参照する。
    response.set_cookie(
        key=settings.session_cookie_name,
        value=sign_sid(sid),
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        domain=settings.cookie_domain,
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=csrf_token,
        max_age=settings.session_ttl_seconds,
        httponly=False,  # Frontend が JS で読んで X-CSRF-Token ヘッダーに詰めるため
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        domain=settings.cookie_domain,
    )


def _clear_session_cookies(response: Response) -> None:
    """ログアウト時に両 Cookie を Max-Age=0 で消す。"""
    settings = get_settings()
    # set_cookie 側と domain= を揃える（揃わないとブラウザが別 Cookie と判定して
    # 古い値が残る）。
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="lax",
        domain=settings.cookie_domain,
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=False,
        samesite="lax",
        domain=settings.cookie_domain,
    )


async def _invalidate_previous_session(request: Request, redis: Redis) -> None:
    """ログイン処理の手前で、リクエストに付いている旧 sid Cookie の Redis 側を破棄する。

    狙い：
      - 同一ブラウザで再ログイン（例：別 GitHub アカウントへの切替）した時に、
        旧セッションが TTL 切れ（最長 7 日）まで Redis に残るのを防ぐ。
      - 旧 sid を何らかの経路で取得された場合の orphan セッション乗っ取りを縮める。

    挙動：
      - sid Cookie が無い / 署名不正 / 既に Redis から消えている、いずれも no-op
        （session_store.delete 自体が「存在しない sid を渡しても何もしない」設計）。
      - Set-Cookie は呼び出し側の `_set_session_cookies` が新 sid で上書きする。
        本関数は Redis 側の状態を消すことに専念する。
    """
    settings = get_settings()
    signed = request.cookies.get(settings.session_cookie_name)
    if not signed:
        return
    old_sid = unsign_sid(signed)
    if old_sid is None:
        return
    await session_store.delete(redis, old_sid)


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
      - next: ログイン後の戻り先（同一オリジン相対パスのみ）。state レコードに
              同梱して Redis に保存し、callback 側で 1 回使い切りで取り出す。
              旧実装は別 Cookie（auth_next）で運んでいたが「state と next が
              別場所に分かれて弱く結合」する設計弱点があったため state レコード
              側に集約した。
    """
    # next の検証は state 保存前に済ませる（同一オリジン相対パスでなければ ""）。
    # 空文字は「戻り先指定なし = ホームへ」を意味する。
    safe_next = _safe_next_path(next_)
    # callback で再度ホーム判定するため、"/" は空文字に正規化する。
    payload_next = "" if safe_next == "/" else safe_next

    state = await state_store.issue(redis, next_path=payload_next)
    client = GitHubOAuthClient()
    authorize_url = client.build_authorize_url(state=state)

    return RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)


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

    # 3. state を Redis から検証 + 消費（1 回使い切り）。state レコードに同梱した
    # next_path も同時に取り出す。
    valid, raw_next = await state_store.verify_and_consume(redis, state)
    if not valid:
        return _redirect_to_login_with_error(AuthErrorKind.STATE_INVALID)

    # 4. code を GitHub に投げてユーザー情報を取得。
    client = GitHubOAuthClient()
    try:
        user_input = await client.exchange_code(code=code)
    except GitHubOAuthError:
        return _redirect_to_login_with_error(AuthErrorKind.OAUTH_FAILED)

    # 5. 既存セッションの後始末。
    #    リクエストに sid Cookie が付いていれば、ログイン処理に入る前に Redis から
    #    旧セッションを破棄する（再ログインで生まれる orphan セッションを残さない、
    #    authentication.md §1.3「ログイン時の旧セッション無効化」）。
    await _invalidate_previous_session(request, redis)

    # 6. upsert + セッション作成。
    service = AuthService(db_session, redis)
    created = await service.login_with_github(user_input)

    # 7. リダイレクト先：state に同梱した next を _safe_next_path で再検証
    # （二重防御：state を Redis に入れる時にも検証しているが、Redis の中身が
    # 何らかの理由で書き換わっても弾けるようにする）。
    target_path = _safe_next_path(raw_next) if raw_next else "/"
    target_url = _absolute_frontend_url(target_path)

    response = RedirectResponse(url=target_url, status_code=status.HTTP_302_FOUND)
    _set_session_cookies(response, sid=created.sid, csrf_token=created.csrf_token)
    return response


def _redirect_to_login_with_error(kind: AuthErrorKind) -> RedirectResponse:
    """/login?auth_error=<種別> に戻す（Frontend がトーストを出す前提）。

    kind は AuthErrorKind で型縛り。kind.value で文字列にしてクエリに乗せる
    （Enum をそのまま f-string に入れると "AuthErrorKind.OAUTH_CANCELED" の
    Python 表記が混じるため明示的に value を取る）。
    """
    url = _absolute_frontend_url(f"/login?auth_error={kind.value}")
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
    redis: RedisDep,
    db_session: DbDep,
    response: Response,
    # _user: 認証必須を表すための Depends。CSRF middleware が先に通過済み（POST 経由）。
    # current_session: deps/auth.py:get_current_session で Cookie 復号 + 検証を集約。
    #                  Router 内で Cookie 解析を再実装する重複を避ける。
    _user: CurrentUser,
    current_session: CurrentSession,
) -> Response:
    """セッションを破棄し、Cookie を Max-Age=0 で消す。

    - 内部的に Redis から `session:<sid>` を DELETE + `user:<id>:sessions` から SREM
    - 204 No Content（ボディなし）。Cookie だけがレスポンスヘッダーに残る
    """
    if current_session is not None:
        service = AuthService(db_session, redis)
        await service.logout(current_session.sid)

    # 念のため Redis 側で消えなかった場合も Cookie はクリアする。
    _clear_session_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
