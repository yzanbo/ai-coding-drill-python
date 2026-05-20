# services/submissions.SubmissionService のユニットテスト（ADR 0044）。
#
# テスト方針：
#   - SubmissionRepository / ProblemRepository を AsyncMock でスタブ化
#   - session.begin() の context manager は MagicMock で擬似実装
#   - ビジネスロジック（問題存在チェック / INSERT / Pydantic 詰め替え）の分岐を網羅
#
# 関わる要件：
#   - docs/requirements/4-features/grading.md §API #post-submissions
#   - docs/adr/0044-backend-repository-pattern-adoption.md

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ProblemNotFoundError
from app.models.problems import Problem
from app.models.submissions import Submission
from app.schemas.submissions import SubmissionStatus
from app.services.submissions import SubmissionService


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=None)
    cm.__aexit__ = AsyncMock(return_value=None)
    session.begin.return_value = cm
    return session


@pytest.fixture
def mock_submissions_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_problems_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    mock_session: MagicMock,
    mock_submissions_repo: AsyncMock,
    mock_problems_repo: AsyncMock,
) -> SubmissionService:
    s = SubmissionService(mock_session)
    s.submissions = mock_submissions_repo  # type: ignore[assignment]
    s.problems = mock_problems_repo  # type: ignore[assignment]
    return s


def _make_problem(*, problem_id: uuid.UUID | None = None) -> Problem:
    p = Problem(
        title="t",
        description="d",
        category="array",
        difficulty="easy",
        language="typescript",
        examples=[{"input": "", "output": ""}],
        test_cases=[{"input": "", "expected": ""}],
        reference_solution="",
        judge_scores={},
    )
    p.id = problem_id or uuid.uuid4()
    p.created_at = datetime.now(UTC)
    p.updated_at = datetime.now(UTC)
    p.deleted_at = None
    return p


def _make_submission(*, submission_id: uuid.UUID | None = None) -> Submission:
    s = Submission(
        user_id=uuid.uuid4(),
        problem_id=uuid.uuid4(),
        code="const solve = () => 1;",
    )
    s.id = submission_id or uuid.uuid4()
    s.created_at = datetime.now(UTC)
    s.status = "pending"
    return s


class TestSubmitAnswer:
    async def test_正常系_submissionsに1行INSERTされ_202レスポンスが返る(
        self,
        service: SubmissionService,
        mock_session: MagicMock,
        mock_submissions_repo: AsyncMock,
        mock_problems_repo: AsyncMock,
    ) -> None:
        user_id = uuid.uuid4()
        problem_id = uuid.uuid4()
        mock_problems_repo.get_by_id.return_value = _make_problem(problem_id=problem_id)
        new_sub = _make_submission()
        mock_submissions_repo.create.return_value = new_sub

        result = await service.submit_answer(
            user_id=user_id,
            problem_id=problem_id,
            code="const solve = (n: number) => n * 2;",
        )

        mock_problems_repo.get_by_id.assert_called_once_with(problem_id=problem_id)
        mock_submissions_repo.create.assert_called_once_with(
            user_id=user_id,
            problem_id=problem_id,
            code="const solve = (n: number) => n * 2;",
        )
        # トランザクション境界が 1 回だけ開かれている契約（R1-5 で同じ tx 内に
        # jobs INSERT + NOTIFY を増やすため、ここを 1 begin に固める）。
        mock_session.begin.assert_called_once_with()

        assert result.submission_id == new_sub.id
        assert result.status is SubmissionStatus.PENDING

    async def test_異常系_存在しない問題ならProblemNotFoundError_submissionsはINSERTされない(
        self,
        service: SubmissionService,
        mock_submissions_repo: AsyncMock,
        mock_problems_repo: AsyncMock,
    ) -> None:
        mock_problems_repo.get_by_id.return_value = None

        with pytest.raises(ProblemNotFoundError):
            await service.submit_answer(
                user_id=uuid.uuid4(),
                problem_id=uuid.uuid4(),
                code="x",
            )
        # 問題が無いと判定したら INSERT に進まない契約。
        mock_submissions_repo.create.assert_not_called()
