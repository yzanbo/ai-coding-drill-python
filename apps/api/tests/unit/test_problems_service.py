# services/problems.ProblemService のユニットテスト。
#
# テスト方針（ADR 0044）：
#   - ProblemRepository を AsyncMock でスタブ化
#   - ビジネスロジック（フィルタ → Repository 呼び出し / Pydantic 詰め替え /
#     マスキング境界 / total_pages 計算）の分岐を網羅
#
# 関わる要件：
#   - docs/requirements/4-features/problem-display-and-answer.md §API / §受け入れ条件
#   - docs/adr/0044-backend-repository-pattern-adoption.md

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import ProblemNotFoundError
from app.models.problems import Problem
from app.schemas.problems import (
    PROBLEMS_PAGE_SIZE,
    ProblemCategory,
    ProblemDifficulty,
)
from app.services.problems import ProblemService


@pytest.fixture
def mock_session() -> MagicMock:
    # ProblemService は session.begin() を呼ばない読み取り専用のため、
    # MagicMock で十分（メソッドアクセスがあっても素通り）。
    return MagicMock()


@pytest.fixture
def mock_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_session: MagicMock, mock_repo: AsyncMock) -> ProblemService:
    s = ProblemService(mock_session)
    s.problems = mock_repo  # type: ignore[assignment]
    return s


def _make_problem(
    *,
    problem_id: uuid.UUID | None = None,
    title: str = "配列の合計を返す",
    category: str = "array",
    difficulty: str = "easy",
    description: str = "数値配列を受け取り、その合計を返す関数 solve を実装してください。",
    examples: list[dict] | None = None,
    test_cases: list[dict] | None = None,
    reference_solution: str = "const solve = (a: number[]) => a.reduce((s, n) => s + n, 0);",
) -> Problem:
    """ORM オブジェクトを最小フィールドで組み立てる（実 DB を経由しない）。"""
    p = Problem(
        title=title,
        description=description,
        category=category,
        difficulty=difficulty,
        language="typescript",
        examples=examples or [{"input": "[1,2,3]", "output": "6"}],
        # test_cases は意図的に複数件用意して、レスポンスに漏れないことを別テストで確認。
        # input は Worker 側 TestCase 契約に合わせて配列で入れる
        # （文字列を入れると grading Worker が json unmarshal で落ちて即 dead 行きになる）。
        test_cases=test_cases
        or [
            {"input": [[1, 2, 3]], "expected": 6},
            {"input": [[]], "expected": 0},
            {"input": [[-1, 1]], "expected": 0},
        ],
        reference_solution=reference_solution,
        judge_scores={"correctness": 5, "difficulty_fit": 5},
    )
    p.id = problem_id or uuid.uuid4()
    p.created_at = datetime.now(UTC)
    p.updated_at = datetime.now(UTC)
    p.deleted_at = None
    return p


class TestListProblems:
    async def test_正常系_フィルタなしで先頭ページが返り_total_pages_が件数から計算される(
        self,
        service: ProblemService,
        mock_repo: AsyncMock,
    ) -> None:
        problems = [_make_problem() for _ in range(3)]
        # total=45 件 → ceil(45 / 20) = 3 ページ。
        mock_repo.list_paginated.return_value = (problems, 45)

        res = await service.list_problems(
            category=None, difficulty=None, page=1, page_size=PROBLEMS_PAGE_SIZE
        )

        mock_repo.list_paginated.assert_called_once_with(
            category=None,
            difficulty=None,
            page=1,
            page_size=PROBLEMS_PAGE_SIZE,
        )
        assert len(res.items) == 3
        assert res.page == 1
        assert res.total_pages == 3

    async def test_正常系_カテゴリと難易度はEnumの値文字列でRepositoryに渡る(
        self,
        service: ProblemService,
        mock_repo: AsyncMock,
    ) -> None:
        mock_repo.list_paginated.return_value = ([], 0)

        await service.list_problems(
            category=ProblemCategory.TYPE_PUZZLE,
            difficulty=ProblemDifficulty.HARD,
            page=2,
            page_size=PROBLEMS_PAGE_SIZE,
        )

        mock_repo.list_paginated.assert_called_once_with(
            category="type-puzzle",
            difficulty="hard",
            page=2,
            page_size=PROBLEMS_PAGE_SIZE,
        )

    async def test_正常系_0件ならtotal_pagesは0で返る(
        self,
        service: ProblemService,
        mock_repo: AsyncMock,
    ) -> None:
        mock_repo.list_paginated.return_value = ([], 0)

        res = await service.list_problems(
            category=None, difficulty=None, page=1, page_size=PROBLEMS_PAGE_SIZE
        )

        assert res.items == []
        assert res.page == 1
        # 0 件 → ceil(0/20) は 0 だが「最低 1 ページ」とは扱わない契約（要件 §API JSON 例）。
        assert res.total_pages == 0

    async def test_正常系_page_size_を渡すと_Repositoryとtotal_pages計算に使われる(
        self,
        service: ProblemService,
        mock_repo: AsyncMock,
    ) -> None:
        # 全件取得用途を想定（apps/web の問題一覧画面が大きな page_size を渡す）。
        problems = [_make_problem() for _ in range(10)]
        mock_repo.list_paginated.return_value = (problems, 10)

        res = await service.list_problems(
            category=None, difficulty=None, page=1, page_size=1000
        )

        mock_repo.list_paginated.assert_called_once_with(
            category=None,
            difficulty=None,
            page=1,
            page_size=1000,
        )
        # total=10 / page_size=1000 → ceil = 1。
        assert res.total_pages == 1
        assert len(res.items) == 10


class TestGetDetail:
    async def test_正常系_詳細が返り_test_cases_は含まれない(
        self,
        service: ProblemService,
        mock_repo: AsyncMock,
    ) -> None:
        """マスキング契約：レスポンス Pydantic は test_cases / reference_solution /
        judge_scores を持たないため、ORM に値があっても表に出ない（schemas/problems.py）。
        """
        problem_id = uuid.uuid4()
        problem = _make_problem(problem_id=problem_id)
        mock_repo.get_by_id.return_value = problem

        res = await service.get_detail(problem_id=problem_id)

        mock_repo.get_by_id.assert_called_once_with(problem_id=problem_id)
        assert res.id == problem_id
        assert res.title == problem.title
        # examples は公開対象。本物の Problem には 1 件入っている。
        assert len(res.examples) == 1
        # response モデルのキー集合を確認（test_cases / reference_solution /
        # judge_scores が漏れていないことを by_alias の dump で検証）。
        dumped = res.model_dump(by_alias=True)
        for forbidden in ("testCases", "test_cases", "referenceSolution", "judgeScores"):
            assert forbidden not in dumped, f"漏洩禁止のキーが含まれている: {forbidden}"

    async def test_異常系_存在しないIDならProblemNotFoundError(
        self,
        service: ProblemService,
        mock_repo: AsyncMock,
    ) -> None:
        mock_repo.get_by_id.return_value = None

        with pytest.raises(ProblemNotFoundError):
            await service.get_detail(problem_id=uuid.uuid4())
