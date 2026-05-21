# ProblemService: 問題閲覧（一覧 / 詳細）のビジネスロジック層（ADR 0044）。
#
#   - SQL は ProblemRepository に委譲、本 Service は Pydantic 詰め替えと
#     マスキング境界の管理に専念する
#   - 認証不要なエンドポイント（problem-display-and-answer.md §ビジネスルール）
#     のため、user_id は受け取らない
#   - マスキングの実体は schemas/problems.py の ProblemDetailResponse 側で
#     行われる（test_cases / reference_solution / judge_scores を持たない）。
#     本 Service は from_attributes=True 経由で Pydantic に詰め替えるだけで
#     必要なフィールドのみが残る
#
# 関わる要件：
#   - docs/requirements/4-features/problem-display-and-answer.md §API / §受け入れ条件

import logging
import math
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ProblemNotFoundError
from app.repositories.problems import ProblemRepository
from app.schemas.problems import (
    PROBLEMS_PAGE_SIZE,
    ProblemCategory,
    ProblemDetailResponse,
    ProblemDifficulty,
    ProblemListResponse,
    ProblemSummaryResponse,
)

logger = logging.getLogger(__name__)


class ProblemService:
    """問題閲覧サービス。読み取り専用、認証不要。"""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self.problems = ProblemRepository(db_session)

    async def list_problems(
        self,
        *,
        category: ProblemCategory | None,
        difficulty: ProblemDifficulty | None,
        page: int,
        page_size: int = PROBLEMS_PAGE_SIZE,
    ) -> ProblemListResponse:
        """フィルタ + ページングして一覧を返す。

        - 0 件でも `items=[], page, totalPages=0` を返す（404 にはしない）
        - totalPages は ceil(total / page_size)、total=0 なら 0
        """
        items, total = await self.problems.list_paginated(
            category=category.value if category is not None else None,
            difficulty=difficulty.value if difficulty is not None else None,
            page=page,
            page_size=page_size,
        )
        total_pages = math.ceil(total / page_size) if total > 0 else 0
        return ProblemListResponse(
            items=[ProblemSummaryResponse.model_validate(p) for p in items],
            page=page,
            total_pages=total_pages,
        )

    async def get_detail(self, *, problem_id: UUID) -> ProblemDetailResponse:
        """1 問の詳細を返す（テストケースの一部のみ examples として公開）。

        存在しない / ソフトデリート済みなら ProblemNotFoundError を投げる
        （Router 側で 404 に変換）。
        """
        problem = await self.problems.get_by_id(problem_id=problem_id)
        if problem is None:
            raise ProblemNotFoundError
        # from_attributes=True 経由で ORM → Pydantic に詰め替え。
        #   test_cases / reference_solution / judge_scores は Response モデルに
        #   フィールドが無いため、ここで自動的に落ちる（マスキング）。
        return ProblemDetailResponse.model_validate(problem)
