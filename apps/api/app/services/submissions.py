# SubmissionService: 解答送信のビジネスロジック層（ADR 0044）。
#
#   R1-4 スコープ：
#     - 問題が存在することを確認（ソフトデリート行も除外）
#     - submissions に 1 行 INSERT、status='pending'
#     - 202 用 Pydantic を返す
#
#   R1-5 で乗せる予定：
#     - jobs INSERT + NOTIFY new_job を同一トランザクション内で実行
#     - 採点結果取得 / 履歴一覧 / ポーリング用エンドポイント
#
# 関わる要件：
#   - docs/requirements/4-features/grading.md §API #post-submissions

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ProblemNotFoundError
from app.repositories.problems import ProblemRepository
from app.repositories.submissions import SubmissionRepository
from app.schemas.submissions import SubmissionAcceptedResponse

logger = logging.getLogger(__name__)


class SubmissionService:
    """解答送信サービス。"""

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self.submissions = SubmissionRepository(db_session)
        self.problems = ProblemRepository(db_session)

    async def submit_answer(
        self,
        *,
        user_id: UUID,
        problem_id: UUID,
        code: str,
    ) -> SubmissionAcceptedResponse:
        """解答を受け付けて submissions 行を作成する。

        振る舞い：
          1. 対象 problem が生きていることを確認（存在しない / soft delete 済みは 404）
          2. submissions に 1 行 INSERT（status='pending'、Repository 側で flush）
          3. 202 用 Pydantic を返す
        """
        async with self.db_session.begin():
            # 対象問題の存在確認。Worker が後段で読み出しに失敗するより前に弾く。
            problem = await self.problems.get_by_id(problem_id=problem_id)
            if problem is None:
                raise ProblemNotFoundError

            submission = await self.submissions.create(
                user_id=user_id,
                problem_id=problem_id,
                code=code,
            )

        # 採点ジョブ enqueue は R1-5 で乗せる。本フェーズでは pending のまま積み上がる。
        logger.info(
            "Submission accepted: user_id=%s problem_id=%s submission_id=%s",
            user_id,
            problem_id,
            submission.id,
        )

        return SubmissionAcceptedResponse(submission_id=submission.id)
