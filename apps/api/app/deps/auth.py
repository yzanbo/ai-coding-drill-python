# このファイルの役割：
#   リクエストの Cookie からセッションを引いて「現在のユーザー」を FastAPI の Depends で
#   注入できるようにする。
#
#   2 種類用意する：
#     - get_current_user           : 必須。未認証なら 401 を返す（保護されたルート用）
#     - get_current_user_optional  : 任意。未認証なら None を返す
#       （ゲスト閲覧可な機能で「ログイン中なら追加情報を出す」分岐に使う）
#
# 関わる要件：
#   - docs/requirements/4-features/authentication.md §1.1 「匿名利用は不可」
#   - docs/requirements/3-cross-cutting/02-api-conventions.md 「認証要否の制御」

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import session as session_store
from app.core.config import get_settings
from app.core.redis import get_redis
from app.db.session import get_async_session
from app.models.users import User
from app.services.auth import AuthService


# get_current_user_optional: Cookie に sid が無い / 期限切れ / DB に user が
#   見つからない場合は None を返す。例外は投げない。
async def get_current_user_optional(
    request: Request,
    db_session: Annotated[AsyncSession, Depends(get_async_session)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> User | None:
    """セッションが有効なら User、無効なら None を返す（ゲスト許容）。

    使い方：
        UserOptional = Annotated[User | None, Depends(get_current_user_optional)]

        @router.get("/...")
        async def handler(user: UserOptional):
            if user is None: ... # ゲスト動作
    """
    settings = get_settings()
    sid = request.cookies.get(settings.session_cookie_name)
    if not sid:
        return None

    session = await session_store.get(redis, sid)
    if session is None:
        return None

    # AuthService を経由するのは ADR 0044 の Repository パターン徹底のため
    # （Repository を直接呼ばず Service の get_current_user を通す）。
    service = AuthService(db_session, redis)
    return await service.get_current_user(session.user_id)


# get_current_user: 必須版。未認証なら 401。
async def get_current_user(
    user: Annotated[User | None, Depends(get_current_user_optional)],
) -> User:
    """セッションが有効なら User、無効なら 401（必須）。

    使い方：
        CurrentUser = Annotated[User, Depends(get_current_user)]

        @router.get("/...")
        async def handler(user: CurrentUser):
            ...

    エンドポイント全体を必須にしたい時は APIRouter の dependencies=[...] に
    Depends(get_current_user) を渡し、ルーター単位で適用する。
    """
    if user is None:
        # detail は日本語。RFC 7807 形式への整形は将来 core/exceptions.py の
        # ハンドラで行う（現状はそのまま FastAPI の既定 JSON 形式）。
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="認証が必要です",
        )
    return user


# get_current_session: CSRF middleware や 「ログアウト時に sid を Redis から消す」
#   等で「セッション本体（sid / csrf_token 等）」が欲しい時に使う。
async def get_current_session(
    request: Request,
    redis: Annotated[Redis, Depends(get_redis)],
) -> session_store.Session | None:
    """Cookie の sid から Session 値オブジェクトを返す。無効なら None。

    ロギング情報以外を含むため、レスポンスに直接返してはいけない。
    """
    settings = get_settings()
    sid = request.cookies.get(settings.session_cookie_name)
    if not sid:
        return None
    return await session_store.get(redis, sid)
