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
from app.core.cookies import unsign_sid
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
    signed = request.cookies.get(settings.session_cookie_name)
    if not signed:
        return None
    # Cookie の値は itsdangerous で署名してあるため、まず復号 + 検証して生 sid を得る。
    sid = unsign_sid(signed)
    if sid is None:
        return None

    session = await session_store.get(redis, sid)
    if session is None:
        return None

    # AuthService を経由するのは ADR 0044 の Repository パターン徹底のため
    # （Repository を直接呼ばず Service の get_current_user を通す）。
    service = AuthService(db_session, redis)
    # 認証ルックアップの SELECT を「明示的な短命トランザクション」で包む：
    #   SQLAlchemy 2.0 の AsyncSession は SELECT を投げた瞬間に autobegin で
    #   暗黙の tx を開始する。get_async_session が払い出した同じ session を
    #   route handler 配下の Service が後段で使う作りのため、ここで暗黙 tx を
    #   閉じておかないと、後続の Service が ADR 0044 規約どおり
    #   `async with session.begin():` を呼んだ瞬間に
    #   「A transaction is already begun on this Session」で 500 になる。
    #   ここで明示的に begin / commit して短命 tx を完結させると、後段の
    #   Service 側は常にクリーンな session を前提に書ける
    #   （pre-auth / post-auth で挙動を分けなくて済む）。
    #   SELECT のみなので tx を開く副作用は無い。AsyncSession は
    #   expire_on_commit=False（db/session.py）なので commit 後も
    #   返した User ORM の属性アクセスは継続して可能。
    async with db_session.begin():
        user = await service.get_current_user(session.user_id)
    # request.state.user に積んでおく：rate limit 用の key 関数 (deps/rate_limit.py の
    #   get_rate_limit_key) が request.state.user.id を読んでユーザー単位の counter を引く。
    #   None の時もここでセットしておくと、key 関数側で hasattr/getattr の場合分けが減る。
    request.state.user = user
    return user


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
    signed = request.cookies.get(settings.session_cookie_name)
    if not signed:
        return None
    sid = unsign_sid(signed)
    if sid is None:
        return None
    return await session_store.get(redis, sid)
