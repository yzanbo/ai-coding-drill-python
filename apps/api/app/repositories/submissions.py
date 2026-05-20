# SubmissionRepository: submissions テーブルへの SQL を集約する層（ADR 0044）。
#
#   R1-4 では INSERT 1 メソッドのみを提供する（POST /api/submissions が呼ぶ）。
#   GET 系（自分の解答履歴 / 結果取得）は R1-5 で追加する。
#
# 関わる要件：
#   - docs/requirements/4-features/grading.md §API #post-submissions

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

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
        #        （R1-5 で同じトランザクション内に jobs INSERT + NOTIFY を続ける拡張余地を残す）。
        await self.session.flush()
        return submission
