# GenerationRequestRepository: generation_requests テーブルへの SQL を集約する層。
#
# ADR 0044 の方針：
#   - SQLAlchemy の select / insert を呼ぶ実装はここに集約
#   - 戻り値は ORM オブジェクト（Pydantic への詰め替えは Service）
#   - 認可・トランザクション境界は持たない

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.generation_requests import GenerationRequest


class GenerationRequestRepository:
    """generation_requests テーブルのクエリ実装。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: UUID,
        category: str,
        difficulty: str,
    ) -> GenerationRequest:
        """新規 1 行を挿入し、サーバ既定値（id / created_at / status='pending'）が
        埋まった ORM を返す。commit はしない（Service 側がトランザクション境界を握る）。
        """
        gr = GenerationRequest(
            user_id=user_id,
            category=category,
            difficulty=difficulty,
        )
        self.session.add(gr)
        # flush: ここで INSERT を送って id / created_at / status を確定させる。
        #        commit はしない（同じトランザクション内で続けて jobs INSERT を行う）。
        await self.session.flush()
        return gr

    async def get_by_id_for_user(
        self,
        *,
        request_id: UUID,
        user_id: UUID,
    ) -> GenerationRequest | None:
        """自分（user_id）の generation_request を主キーで 1 件取得。

        他人のリクエスト ID を渡された場合は None（Router 側で 404 を返す）。
        他人 ID と存在しない ID の区別は付けない（情報漏洩防止）。
        """
        stmt = select(GenerationRequest).where(
            GenerationRequest.id == request_id,
            GenerationRequest.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
