# services/submissions.SubmissionService のユニットテスト（ADR 0044）。
#
# テスト方針：
#   - SubmissionRepository / ProblemRepository / JobRepository を AsyncMock でスタブ化
#   - session.begin() の context manager は MagicMock で擬似実装
#   - ビジネスロジック（問題存在チェック / INSERT / jobs enqueue / Pydantic 詰め替え）
#     の分岐を網羅
#
# 関わる要件：
#   - docs/requirements/4-features/grading.md §API
#   - docs/adr/0044-backend-repository-pattern-adoption.md

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ProblemNotFoundError
from app.models.jobs import Job
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
def mock_jobs_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    mock_session: MagicMock,
    mock_submissions_repo: AsyncMock,
    mock_problems_repo: AsyncMock,
    mock_jobs_repo: AsyncMock,
) -> SubmissionService:
    s = SubmissionService(mock_session)
    s.submissions = mock_submissions_repo  # type: ignore[assignment]
    s.problems = mock_problems_repo  # type: ignore[assignment]
    s.jobs = mock_jobs_repo  # type: ignore[assignment]
    return s


def _make_job(*, job_id: int = 1) -> Job:
    j = Job(queue="grading", type="submission.grade", payload={})
    j.id = job_id
    j.created_at = datetime.now(UTC)
    return j


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
    async def test_正常系_submissionsに1行INSERTされ_採点ジョブもenqueueされる(
        self,
        service: SubmissionService,
        mock_session: MagicMock,
        mock_submissions_repo: AsyncMock,
        mock_problems_repo: AsyncMock,
        mock_jobs_repo: AsyncMock,
    ) -> None:
        user_id = uuid.uuid4()
        problem_id = uuid.uuid4()
        mock_problems_repo.get_by_id.return_value = _make_problem(problem_id=problem_id)
        new_sub = _make_submission()
        mock_submissions_repo.create.return_value = new_sub
        mock_jobs_repo.enqueue.return_value = _make_job()

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
        # 採点ジョブの enqueue 契約：
        #   - queue='grading' / type='submission.grade'
        #   - payload は camelCase キーで Worker 側 quicktype 生成型と整合
        #   - traceContext は R1〜R3 暫定で traceparent=None / tracestate=""
        mock_jobs_repo.enqueue.assert_called_once()
        enqueue_kwargs = mock_jobs_repo.enqueue.call_args.kwargs
        assert enqueue_kwargs["queue"] == "grading"
        assert enqueue_kwargs["type_"] == "submission.grade"
        payload = enqueue_kwargs["payload"]
        assert payload["submissionId"] == str(new_sub.id)
        assert payload["userId"] == str(user_id)
        assert payload["problemId"] == str(problem_id)
        assert payload["code"] == "const solve = (n: number) => n * 2;"
        assert payload["traceContext"]["traceparent"] is None
        assert payload["traceContext"]["tracestate"] == ""

        # トランザクション境界が 1 回だけ開かれている契約。
        # submissions INSERT + jobs INSERT + NOTIFY を同一 tx に閉じる。
        mock_session.begin.assert_called_once_with()

        assert result.submission_id == new_sub.id
        assert result.status is SubmissionStatus.PENDING

    async def test_異常系_存在しない問題ならProblemNotFoundError_INSERTとenqueueはされない(
        self,
        service: SubmissionService,
        mock_submissions_repo: AsyncMock,
        mock_problems_repo: AsyncMock,
        mock_jobs_repo: AsyncMock,
    ) -> None:
        mock_problems_repo.get_by_id.return_value = None

        with pytest.raises(ProblemNotFoundError):
            await service.submit_answer(
                user_id=uuid.uuid4(),
                problem_id=uuid.uuid4(),
                code="x",
            )
        # 問題が無いと判定したら INSERT にも enqueue にも進まない契約。
        mock_submissions_repo.create.assert_not_called()
        mock_jobs_repo.enqueue.assert_not_called()
