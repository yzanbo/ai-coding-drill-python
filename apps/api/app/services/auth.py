# AuthService: 認証ドメインのビジネスロジック層。
#
# ADR 0044：
#   - SQLAlchemy を直接呼ばず Repository に委譲
#   - トランザクション境界（async with session.begin()）はここで握る
#   - ORM オブジェクト → Pydantic（UserResponse）への詰め替えもここで行う
#
# 主な責務：
#   1. GitHub から取得したユーザー情報で users / auth_providers を upsert
#      （既存ユーザーは display_name / email を最新値で上書き、authentication.md §2.1）
#   2. ログイン成功時に Redis セッションを作成 + CSRF トークン発行
#   3. ログアウト時に Redis セッションを破棄
#   4. リクエストごとに sid からユーザー情報を取り出す（deps/auth.py から利用）

import logging
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import session as session_store
from app.models.users import User
from app.repositories.auth_providers import AuthProviderRepository
from app.repositories.users import UserRepository
from app.schemas.auth import CreatedSession, UserResponse, UserSyncInput

# プロバイダ識別子。auth_providers.provider に入れる値。
# 将来 Google を追加するなら "google" 等を別 Service で扱う。
_PROVIDER_GITHUB = "github"

logger = logging.getLogger(__name__)


class AuthService:
    """認証ドメインのサービス。

    - 1 リクエストにつき 1 インスタンス生成（Router の Depends で組み立てる）
    - session（AsyncSession）と redis（Redis）の両方を受け取って組み合わせる
    """

    def __init__(self, db_session: AsyncSession, redis: Redis) -> None:
        self.db_session = db_session
        self.redis = redis
        self.users = UserRepository(db_session)
        self.providers = AuthProviderRepository(db_session)

    async def login_with_github(self, payload: UserSyncInput) -> CreatedSession:
        """GitHub のユーザー情報から upsert + セッション作成を一気に行う。

        振る舞い：
          1. (provider="github", provider_id=...) で既存紐付けを探す
          2. あれば既存 users を再利用 + display_name / email を最新値で上書き
             （authentication.md §2.1：「再ログイン時は GitHub の最新値で上書き」）
          3. なければ users を新規作成 + auth_providers に紐付けを INSERT
             （同一トランザクション内、authentication.md §2.1）
          4. その user_id で Redis にセッションを作成（複数端末ログイン許容のため
             既存セッションは消さない、authentication.md §1.1）
        """
        # async with session.begin():
        #   このブロック内で行われた DB 変更（INSERT / UPDATE）を 1 つのトランザクション
        #   として扱う。ブロックを抜けるときに自動 commit、例外なら rollback。
        async with self.db_session.begin():
            existing_link = await self.providers.get_by_provider_id(
                provider=_PROVIDER_GITHUB,
                provider_id=payload.provider_id,
            )
            if existing_link is not None:
                # 既存ユーザーの再ログイン：profile を最新値で上書き。
                await self.users.update_profile(
                    user_id=existing_link.user_id,
                    display_name=payload.display_name,
                    email=payload.email,
                )
                # 上書き後の最新 ORM を取り直して詰め替え元にする。
                user = await self.users.get_by_id(existing_link.user_id)
                if user is None:
                    # CASCADE 削除と並走した極稀なレース。新規ユーザー作成にフォールバック
                    # するより、明示エラーで再ログインを促す方が後段の振る舞いが読みやすい。
                    raise RuntimeError(
                        "User row missing despite auth_providers exists"
                    )
            else:
                # 新規ユーザー：users + auth_providers を同じトランザクション内で INSERT。
                user = await self.users.create(
                    display_name=payload.display_name,
                    email=payload.email,
                )
                await self.providers.create(
                    provider=_PROVIDER_GITHUB,
                    provider_id=payload.provider_id,
                    user_id=user.id,
                )

        # ここで DB トランザクションは閉じている。続けて Redis にセッションを作る。
        # （DB と Redis を 1 トランザクションにまとめることはできないが、
        #  失敗時は「DB だけ作られて Redis なし」となり、ユーザーは再ログインで復旧可能。
        #  ADR 0047 §「失っても致命的でない」設計と整合）
        new_session = await session_store.create(self.redis, user.id)

        # sid 全体をログに出すと、ログ閲覧者がセッションを乗っ取れてしまう
        # （秘密情報の平文記録）。先頭 8 文字 + "..." だけ残せば、
        # 「どのセッションの話か」を識別する用途には足りる。
        logger.info(
            "User logged in via GitHub: user_id=%s sid_prefix=%s new_user=%s",
            user.id,
            new_session.sid[:8] + "...",
            existing_link is None,
        )

        return CreatedSession(
            sid=new_session.sid,
            csrf_token=new_session.csrf_token,
            user=UserResponse.model_validate(user),
        )

    async def logout(self, sid: str) -> None:
        """セッションを破棄する。

        - Redis からセッション削除（user:<id>:sessions set からも該当 sid を SREM）
        - Cookie のクリアは Router 側で Set-Cookie: Max-Age=0 を返して行う
        """
        await session_store.delete(self.redis, sid)

    async def get_current_user(self, user_id: UUID) -> User | None:
        """sid → user_id を session.py で引いた後、その user_id から User ORM を取得する。

        ※ Pydantic への詰め替えはしない。Router 側で UserResponse.model_validate する。
        """
        return await self.users.get_by_id(user_id)
