# SubmissionRepository: submissions テーブルへの SQL を集約する層（ADR 0044）。
#
#   - create               : 解答送信時に 1 行 INSERT（POST /api/submissions）
#   - get_by_id_for_user   : ownership 込みで 1 件取得（GET /api/submissions/:id）
#   - list_for_user        : 自分の解答履歴をページングで返す（GET /api/submissions）
#
# 関わる要件：
#   - docs/requirements/4-features/grading.md §API

from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import contains_eager

from app.models.problems import Problem
from app.models.submissions import Submission


class SubmissionRepository:
    """submissions テーブルのクエリ実装。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: UUID,
        problem_id: UUID,
        code: str,
    ) -> Submission:
        """新規 1 行を挿入し、サーバ既定値（id / created_at / status='pending'）を
        含む ORM を返す。commit はしない（Service 側がトランザクション境界を握る）。
        """
        submission = Submission(
            user_id=user_id,
            problem_id=problem_id,
            code=code,
        )
        self.session.add(submission)
        # flush: ここで INSERT を送り id / created_at / status を確定させる
        #        （Service が同じ tx で jobs INSERT + NOTIFY を続けるため id を要する）。
        await self.session.flush()
        return submission

    async def get_by_id_for_user(
        self,
        *,
        submission_id: UUID,
        user_id: UUID,
    ) -> Submission | None:
        """主キーで 1 件取得。ただし「自分のもの」だけを返す。

        他人の id を渡しても None を返す（Service 側で 404 に変換）。
        「他人」と「存在しない」を区別しないことで情報漏洩を防ぐ
        （grading.md §受け入れ条件「他ユーザーの submissions/:id には 403 / 404」）。
        ソフトデリート済み（deleted_at IS NOT NULL）も None として扱う。
        """
        stmt = select(Submission).where(
            Submission.id == submission_id,
            Submission.user_id == user_id,
            Submission.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
    ) -> tuple[list[Submission], int]:
        """自分の解答履歴をページングして items と総件数を返す。

        items は Submission ORM の配列。各要素は problem 関連（Problem）が
        contains_eager で事前読み込みされており、`submission.problem.title` で
        問題タイトルを取得できる（一覧 UI で問題名を併記する要件
        grading.md §JSON 例 #get-submissions）。

        並び順は created_at DESC（新着順）。tie-break は id DESC で deterministic に。
        ソフトデリート済みの行（自分 / 問題どちら側でも）は含めない。
        """
        # 共通の WHERE 群（items 側 / count 側で再利用）。
        #   自分のもの + ソフトデリート除外 + 問題側もソフトデリート除外。
        conditions: list[ColumnElement[bool]] = [
            Submission.user_id == user_id,
            Submission.deleted_at.is_(None),
            Problem.deleted_at.is_(None),
        ]

        # 件数取得は別クエリで COUNT(*)。
        #   total を返すために items クエリと分ける（ページ内 0 件でも total が要る）。
        count_stmt = (
            select(func.count())
            .select_from(Submission)
            .join(Problem, Problem.id == Submission.problem_id)
            .where(*conditions)
        )
        total = (await self.session.execute(count_stmt)).scalar_one()

        # items 本体クエリ。
        #   JOIN で Problem を引きつつ、contains_eager で「この JOIN の結果を
        #   submission.problem 関連にそのまま詰めて良い」と SQLAlchemy に教える。
        #   結果、追加クエリなしで submission.problem.title が読める。
        items_stmt = (
            select(Submission)
            .join(Problem, Problem.id == Submission.problem_id)
            .options(contains_eager(Submission.problem))
            .where(*conditions)
            .order_by(Submission.created_at.desc(), Submission.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        items = (await self.session.execute(items_stmt)).scalars().all()
        return list(items), total
