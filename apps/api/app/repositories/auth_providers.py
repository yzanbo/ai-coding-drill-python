# AuthProviderRepository: auth_providers テーブルへの SQLAlchemy クエリだけを置く層。
#
# ADR 0044：戻り値は ORM オブジェクト、ビジネスロジックは Service 側。

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_providers import AuthProvider


class AuthProviderRepository:
    """auth_providers テーブルのクエリ実装。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_provider_id(
        self,
        *,
        provider: str,
        provider_id: str,
    ) -> AuthProvider | None:
        """(provider, provider_id) の複合主キーで 1 件取得。なければ None。

        GitHub 再ログイン時に「既存ユーザーと紐づくか」を判定する用途。
        """
        stmt = select(AuthProvider).where(
            AuthProvider.provider == provider,
            AuthProvider.provider_id == provider_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        provider: str,
        provider_id: str,
        user_id: UUID,
    ) -> AuthProvider:
        """新規紐付けを作って flush し、created_at が埋まった ORM を返す。

        users への INSERT と同じトランザクション内で呼ばれる前提（Service 側で
        async with session.begin() の中で呼ぶ）。
        """
        link = AuthProvider(
            provider=provider,
            provider_id=provider_id,
            user_id=user_id,
        )
        self.session.add(link)
        await self.session.flush()
        return link
