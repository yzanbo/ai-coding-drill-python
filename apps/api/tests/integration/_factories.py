# 統合テスト用の fixture 行を作る共通 factory。
#
# 目的:
#   - 7 ファイルに重複していた problem / submission / user の INSERT helper を 1 箇所に集約
#     （元は _insert_* と _create_* の 2 系統。命名と引数規約を create_* + session 必須 に統一）
#   - Problem / Submission のカラム追加・shape 変更を 1 ファイルの更新で吸収できるようにする
#
# 引数規約:
#   - 全 helper の第 1 引数は AsyncSession（呼び出し側でセッション境界を握る）
#   - helper 内で flush + commit までやる（id を返したいので flush は必須）
#
# 呼び出し例:
#   - API 経由のテスト（自前で session を開く）
#       async with AsyncSessionLocal() as s:
#           problem_id = await create_problem(s, title="A")
#   - Repository テスト（pytest fixture の session を渡す）
#       problem_id = await create_problem(session, category="array")

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.problems import Problem
from app.models.submissions import Submission
from app.repositories.users import UserRepository


async def create_user(session: AsyncSession, *, name: str = "Taro") -> uuid.UUID:
    """users に 1 行作って id を返す。"""
    # UserRepository.create は flush までで commit しない契約のため、
    # ここで明示的に commit して FK 参照の前提を確定させる。
    users = UserRepository(session)
    user = await users.create(display_name=name, email=None)
    await session.commit()
    return user.id


async def create_problem(
    session: AsyncSession,
    *,
    title: str = "配列の合計",
    description: str = "合計を返してください",
    category: str = "array",
    difficulty: str = "easy",
    language: str = "typescript",
    examples: list[dict] | None = None,
    test_cases: list[dict] | None = None,
    reference_solution: str = "x",
    judge_scores: dict | None = None,
    deleted: bool = False,
) -> uuid.UUID:
    """problems に 1 行作って id を返す。deleted=True ならソフトデリート印付き。"""
    problem = Problem(
        title=title,
        description=description,
        category=category,
        difficulty=difficulty,
        language=language,
        examples=(
            examples if examples is not None else [{"input": "[1,2,3]", "output": "6"}]
        ),
        test_cases=(
            test_cases
            if test_cases is not None
            else [{"input": "[1,2,3]", "expected": "6"}]
        ),
        reference_solution=reference_solution,
        judge_scores=judge_scores if judge_scores is not None else {},
    )
    session.add(problem)
    await session.flush()
    problem_id = problem.id
    if deleted:
        problem.deleted_at = datetime.now(UTC)
    await session.commit()
    return problem_id


async def create_submission(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    problem_id: uuid.UUID,
    code: str = "x",
    status: str = "graded",
    passed: bool | None = True,
    score: int | None = None,
    result: dict[str, Any] | None = None,
    graded_at: datetime | None = None,
    deleted: bool = False,
) -> uuid.UUID:
    """submissions に 1 行作って id を返す。

    採点済み状態の作り分け:
      - result を明示的に渡す → そのまま使う（test_submissions_api のような細かい状態作成用）
      - result=None かつ passed が True/False → result.passed を埋めた「採点完了」状態
      - result=None かつ passed=None → result=None の「採点未完了」状態
    """
    sub = Submission(user_id=user_id, problem_id=problem_id, code=code)
    sub.status = status
    sub.score = score
    sub.graded_at = graded_at
    if result is not None:
        sub.result = result
    elif passed is None:
        sub.result = None
    else:
        # Worker が graded 行に詰める result JSONB の最小形（grading.md §採点結果）。
        sub.result = {
            "passed": passed,
            "durationMs": 100,
            "testResults": [],
        }
    session.add(sub)
    await session.flush()
    sub_id = sub.id
    if deleted:
        sub.deleted_at = datetime.now(UTC)
    await session.commit()
    return sub_id
