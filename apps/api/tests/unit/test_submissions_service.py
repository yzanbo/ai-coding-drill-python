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

from app.core.exceptions import ProblemNotFoundError, SubmissionNotFoundError
from app.models.jobs import Job
from app.models.problems import Problem
from app.models.submissions import Submission
from app.schemas.submissions import SubmissionFailureKind, SubmissionStatus
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
        # test_cases.input は Worker 側の TestCase 契約（[]any）に合わせて配列で入れる。
        # 文字列を入れると grading Worker が json unmarshal で落ちて即 dead 行きになる。
        # 契約 SSoT: apps/workers/grading/internal/grading/generation_prompt.go の TestCase
        test_cases=[{"input": [], "expected": None}],
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


class TestGetSubmission:
    async def test_正常系_pendingの間はscore_totalCount_result_gradedAtがNone(
        self,
        service: SubmissionService,
        mock_submissions_repo: AsyncMock,
    ) -> None:
        user_id = uuid.uuid4()
        sub = _make_submission()
        # pending: Worker が UPDATE する前の状態。result / score / graded_at は未設定。
        sub.status = "pending"
        sub.result = None
        sub.score = None
        sub.graded_at = None
        mock_submissions_repo.get_by_id_for_user.return_value = sub

        res = await service.get_submission(user_id=user_id, submission_id=sub.id)

        mock_submissions_repo.get_by_id_for_user.assert_called_once_with(
            submission_id=sub.id,
            user_id=user_id,
        )
        assert res.id == sub.id
        assert res.status is SubmissionStatus.PENDING
        assert res.score is None
        assert res.total_count is None
        assert res.result is None
        assert res.graded_at is None

    async def test_正常系_graded時にresult_JSONBが詰め替えられ_testResults件数がtotalCount(
        self,
        service: SubmissionService,
        mock_submissions_repo: AsyncMock,
    ) -> None:
        user_id = uuid.uuid4()
        sub = _make_submission()
        graded_at = datetime.now(UTC)
        # Worker が書き込んだ想定の result JSONB（camelCase キー、ADR 0006 の Worker 境界）。
        sub.status = "graded"
        sub.score = 2
        sub.graded_at = graded_at
        sub.result = {
            "passed": False,
            "durationMs": 1340,
            "failureKind": "test_failed",
            "testResults": [
                {"name": "case1", "passed": True, "durationMs": 120},
                {
                    "name": "case2",
                    "passed": False,
                    "durationMs": 80,
                    "expected": "6",
                    "actual": "7",
                    "message": "AssertionError",
                },
                {"name": "case3", "passed": True, "durationMs": 100},
            ],
        }
        mock_submissions_repo.get_by_id_for_user.return_value = sub

        res = await service.get_submission(user_id=user_id, submission_id=sub.id)

        assert res.status is SubmissionStatus.GRADED
        assert res.score == 2
        # total_count は result.testResults の件数から派生（カラム化していない）。
        assert res.total_count == 3
        assert res.graded_at == graded_at
        assert res.result is not None
        assert res.result.passed is False
        assert res.result.duration_ms == 1340
        assert res.result.failure_kind is SubmissionFailureKind.TEST_FAILED
        assert len(res.result.test_results) == 3
        assert res.result.test_results[1].expected == "6"
        assert res.result.test_results[1].actual == "7"

    async def test_異常系_他人の解答や存在しないIDはSubmissionNotFoundError(
        self,
        service: SubmissionService,
        mock_submissions_repo: AsyncMock,
    ) -> None:
        # Repository が None を返す = 他人の id or 存在しない id（区別しない契約）。
        mock_submissions_repo.get_by_id_for_user.return_value = None

        with pytest.raises(SubmissionNotFoundError):
            await service.get_submission(
                user_id=uuid.uuid4(),
                submission_id=uuid.uuid4(),
            )

    async def test_異常系_DBに異常なstatus値が入っているとValueError(
        self,
        service: SubmissionService,
        mock_submissions_repo: AsyncMock,
    ) -> None:
        sub = _make_submission()
        # SubmissionStatus に存在しない値が DB に残っているケース（運用事故想定）。
        sub.status = "unknown_status"
        mock_submissions_repo.get_by_id_for_user.return_value = sub

        with pytest.raises(ValueError):
            await service.get_submission(
                user_id=uuid.uuid4(),
                submission_id=sub.id,
            )


class TestListSubmissions:
    async def test_正常系_problem_titleが含まれtotal_pagesが計算される(
        self,
        service: SubmissionService,
        mock_submissions_repo: AsyncMock,
    ) -> None:
        user_id = uuid.uuid4()
        sub1 = _make_submission()
        sub1.status = "graded"
        sub1.score = 5
        sub1.graded_at = datetime.now(UTC)
        sub1.result = {
            "passed": True,
            "durationMs": 100,
            "testResults": [
                {"name": "c1", "passed": True, "durationMs": 50},
                {"name": "c2", "passed": True, "durationMs": 50},
            ],
        }
        sub2 = _make_submission()
        sub2.status = "pending"
        sub2.result = None

        # Repository は Submission ORM の配列を返す契約（ADR 0044）。
        # 各 ORM は problem 関連が contains_eager で事前ロードされている前提で、
        # Mock では Problem を作って .problem 属性にベタ詰めする。
        sub1.problem = _make_problem()
        sub1.problem.title = "二倍にして返す"
        sub2.problem = _make_problem()
        sub2.problem.title = "合計を返す"
        mock_submissions_repo.list_for_user.return_value = (
            [sub1, sub2],
            42,  # 全件数：page_size=20 なら 3 ページ
        )

        res = await service.list_submissions(
            user_id=user_id,
            page=1,
            page_size=20,
        )

        mock_submissions_repo.list_for_user.assert_called_once_with(
            user_id=user_id,
            page=1,
            page_size=20,
        )
        assert res.page == 1
        assert res.page_size == 20
        # total_pages = ceil(42 / 20) = 3
        assert res.total_pages == 3
        assert len(res.items) == 2
        # problem_title が JOIN 取得分から詰まる。
        assert res.items[0].problem_title == "二倍にして返す"
        assert res.items[1].problem_title == "合計を返す"
        # graded 側は result.testResults 件数で total_count が算出される。
        assert res.items[0].status is SubmissionStatus.GRADED
        assert res.items[0].total_count == 2
        assert res.items[0].score == 5
        # pending 側は result が None なので total_count も None。
        assert res.items[1].status is SubmissionStatus.PENDING
        assert res.items[1].total_count is None
        assert res.items[1].score is None

    async def test_正常系_空でもtotal_pagesは1(
        self,
        service: SubmissionService,
        mock_submissions_repo: AsyncMock,
    ) -> None:
        # 解答 0 件のユーザーでも total_pages=1（空ページ）を返す契約。
        mock_submissions_repo.list_for_user.return_value = ([], 0)

        res = await service.list_submissions(
            user_id=uuid.uuid4(),
            page=1,
            page_size=20,
        )

        assert res.items == []
        assert res.page == 1
        assert res.page_size == 20
        assert res.total_pages == 1
