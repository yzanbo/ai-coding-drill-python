# ProblemRepository: problems テーブルへの SQL を集約する層（ADR 0044）。
#
#   - 読み取り専用 2 メソッド（list / get_by_id）を提供
#   - INSERT は Worker（generation / grading）の責務、本 Repository には書かない
#   - 戻り値は ORM オブジェクト（list[Problem] / Problem | None）。
#     Pydantic への詰め替えは Service が行う
#   - ソフトデリート（ADR 0048）：WHERE deleted_at IS NULL を明示的に書く
#
# 関わる要件：
#   - docs/requirements/4-features/problem-display-and-answer.md §API

from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.problems import Problem


class ProblemRepository:
    """problems テーブルのクエリ実装。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_paginated(
        self,
        *,
        category: str | None,
        difficulty: str | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Problem], int]:
        """フィルタ + ページングして items と総件数を返す。

        並び順は `created_at DESC`（新着問題が先頭）。
        category / difficulty は None なら未指定（フィルタしない）。
        """
        # 共通の WHERE 群。
        #   deleted_at IS NULL: ソフトデリート除外（ADR 0048、暗黙フィルタは使わない）。
        #   category / difficulty: 指定があれば等価フィルタ。
        conditions: list[ColumnElement[bool]] = [Problem.deleted_at.is_(None)]
        if category is not None:
            conditions.append(Problem.category == category)
        if difficulty is not None:
            conditions.append(Problem.difficulty == difficulty)

        # 件数取得は別クエリで COUNT(*)。
        #   ページ内 0 件でも total を返したいので items クエリと分ける。
        count_stmt = select(func.count()).select_from(Problem).where(*conditions)
        total = (await self.session.execute(count_stmt)).scalar_one()

        # items 本体クエリ。
        #   created_at DESC で固定。tie-break は id にして deterministic に。
        items_stmt = (
            select(Problem)
            .where(*conditions)
            .order_by(Problem.created_at.desc(), Problem.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = list((await self.session.execute(items_stmt)).scalars().all())
        return items, total

    async def get_by_id(self, *, problem_id: UUID) -> Problem | None:
        """主キーで 1 件取得。ソフトデリート済みは見えなくする。"""
        stmt = select(Problem).where(
            Problem.id == problem_id,
            Problem.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
