# MeGenerationsService: 問題生成履歴・状態管理（R1-7）のビジネスロジック層（ADR 0044）。
#
#   - list_history : ページネーション付きで自分の generation_requests を返す
#   - cancel       : pending のリクエストをキャンセル（jobs を dead に倒す）
#   - retry        : failed のリクエストを新規 generation_request として複製
#
#   prompt_version は jobs.payload から JOIN 取得、retry_count は WITH RECURSIVE
#   CTE で 1 クエリ取得（N+1 を避ける）。
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md §履歴・状態管理
#   - docs/requirements/4-features/problem-generation.md §API

import logging
import math
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    GenerationRequestNotCancelableError,
    GenerationRequestNotFoundError,
    GenerationRequestNotRetryableError,
)
from app.repositories.me_generations import MeGenerationsRepository
from app.schemas.me_generations import (
    ME_GENERATIONS_PAGE_SIZE,
    GenerationRequestCancelResponse,
    GenerationRequestRetryResponse,
    GenerationRequestSummary,
    MeGenerationsListResponse,
)
from app.schemas.problems import (
    ProblemCategory,
    ProblemDifficulty,
)
from app.services.problem_generation import ProblemGenerationService

logger = logging.getLogger(__name__)


class MeGenerationsService:
    """問題生成履歴 + キャンセル / 再試行のサービス。

    - 1 リクエストにつき 1 インスタンス生成
    - 再試行は ProblemGenerationService.enqueue_generation を内部で呼ぶ
      （enqueue ロジックの重複実装を避ける、backend.md §services）
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self.repo = MeGenerationsRepository(db_session)
        self.generation = ProblemGenerationService(db_session)

    async def list_history(
        self,
        *,
        user_id: UUID,
        page: int,
    ) -> MeGenerationsListResponse:
        """自分の生成リクエスト履歴を created_at DESC で 1 ページ返す。

        - 履歴ゼロは items=[] / totalPages=0 を返す（404 にはしない）
        - prompt_version は jobs.payload から JOIN 取得、消えていれば None
        - retry_count は WITH RECURSIVE で 1 クエリで取得（N+1 を避ける）
        """
        rows = await self.repo.list_for_user(
            user_id=user_id,
            page=page,
            page_size=ME_GENERATIONS_PAGE_SIZE,
        )
        total = await self.repo.count_for_user(user_id=user_id)
        total_pages = math.ceil(total / ME_GENERATIONS_PAGE_SIZE) if total > 0 else 0

        ids = [r.id for r in rows]
        prompt_versions = await self.repo.fetch_prompt_versions(generation_request_ids=ids)
        retry_depths = await self.repo.compute_retry_depths(
            user_id=user_id,
            request_ids=ids,
        )

        items = [
            GenerationRequestSummary(
                id=r.id,
                category=r.category,
                difficulty=r.difficulty,
                # status: DB の生文字列を Literal にそのまま流す。Pydantic 側で
                #   想定外値は ValidationError になり 500 として観測できる。
                status=r.status,  # type: ignore[arg-type]
                produced_problem_id=r.produced_problem_id,
                prompt_version=prompt_versions.get(r.id),
                retry_of=r.retry_of,
                retry_count=retry_depths.get(r.id, 0),
                failure_reason=r.failure_reason,
                created_at=r.created_at,
                completed_at=r.completed_at,
            )
            for r in rows
        ]
        return MeGenerationsListResponse(
            items=items,
            page=page,
            page_size=ME_GENERATIONS_PAGE_SIZE,
            total_pages=total_pages,
        )

    async def cancel(
        self,
        *,
        user_id: UUID,
        request_id: UUID,
    ) -> GenerationRequestCancelResponse:
        """pending のリクエストをキャンセルする。

        - 自分のものでない / 存在しない → GenerationRequestNotFoundError（404）
        - 自分のものだが pending でない → GenerationRequestNotCancelableError（409）
        - cancel 成功 → status='canceled' で返す
        """
        gr = await self.repo.get_for_user(
            request_id=request_id, user_id=user_id,
        )
        if gr is None:
            raise GenerationRequestNotFoundError
        if gr.status != "pending":
            raise GenerationRequestNotCancelableError(current_status=gr.status)

        async with self.db_session.begin():
            transitioned = await self.repo.cancel_pending(
                request_id=request_id,
                user_id=user_id,
            )
            if not transitioned:
                # race: 取得時点では pending だったが、cancel UPDATE 直前に
                # Worker が拾って running に進めた場合などはここに来る。
                # その時点で「キャンセル不可」を返すのが意味的に正しい。
                raise GenerationRequestNotCancelableError(current_status="running")

        logger.info(
            "Generation request canceled: user_id=%s request_id=%s",
            user_id,
            request_id,
        )
        return GenerationRequestCancelResponse(id=request_id, status="canceled")

    async def retry(
        self,
        *,
        user_id: UUID,
        request_id: UUID,
    ) -> GenerationRequestRetryResponse:
        """failed のリクエストを再試行する（新規 generation_request として複製）。

        - 自分のものでない / 存在しない → GenerationRequestNotFoundError（404）
        - 自分のものだが failed でない → GenerationRequestNotRetryableError（409）
        - retry 成功 → 新規 generation_request の id + retry_of で返す
        """
        original = await self.repo.get_for_user(
            request_id=request_id, user_id=user_id,
        )
        if original is None:
            raise GenerationRequestNotFoundError
        if original.status != "failed":
            raise GenerationRequestNotRetryableError(current_status=original.status)

        # 既存 enqueue ロジックに retry_of を渡して再利用する（同 tx で
        # generation_requests INSERT + jobs INSERT + NOTIFY）。
        accepted = await self.generation.enqueue_generation(
            user_id=user_id,
            category=ProblemCategory(original.category),
            difficulty=ProblemDifficulty(original.difficulty),
            retry_of=original.id,
        )
        return GenerationRequestRetryResponse(
            id=accepted.request_id,
            status="pending",
            retry_of=original.id,
        )
