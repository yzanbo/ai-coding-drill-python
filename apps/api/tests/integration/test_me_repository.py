# MeRepository の結合テスト（実 Postgres）。
#
# テスト方針：
#   - 実 DB に対して aggregate_by_category の SQL 挙動を直接検証
#     （Service 単体テストでは Repository をモックしているため、Repository 自体は
#      実 DB で集計クエリの効果を観察する、ADR 0044）
#   - 採点完了行のみカウントされること、deleted_at が無視されること、
#     他人の submission が混ざらないこと、を観測する
#
# 関わる要件：
#   - docs/requirements/4-features/learning.md §API §ビジネスルール
#   - docs/requirements/3-cross-cutting/01-data-model.md（FK / ソフトデリート方針）

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.problems import Problem
from app.models.submissions import Submission
from app.repositories.me import MeRepository
from app.repositories.users import UserRepository


@pytest.fixture(autouse=True)
async def reset_submissions_problems_tables() -> AsyncIterator[None]:
    """各テスト前に submissions / problems を空にする（テスト間の独立性）。

    autouse の reset_auth_tables が users / auth_providers を消す前に
    submissions（user_id / problem_id を FK 参照）を先に消す必要がある。
    """
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Submission))
        await session.execute(delete(Problem))
        await session.commit()
    yield


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """テスト用に AsyncSession を払い出して終了時に破棄する。"""
    async with AsyncSessionLocal() as s:
        yield s


async def _create_user(session: AsyncSession, name: str = "Taro") -> uuid.UUID:
    users = UserRepository(session)
    async with session.begin():
        user = await users.create(display_name=name, email=None)
    return user.id


async def _create_problem(
    session: AsyncSession,
    *,
    category: str = "array",
    deleted: bool = False,
) -> uuid.UUID:
    """テスト用 problem を 1 件作る。category だけテストで使い分ける。"""
    async with session.begin():
        problem = Problem(
            title="t",
            description="d",
            category=category,
            difficulty="easy",
            language="typescript",
            examples=[{"input": "", "output": ""}],
            # test_cases.input は Worker 側の TestCase 契約（[]any）に合わせて配列で入れる。
            # 文字列を入れると grading Worker が json unmarshal で落ちて即 dead 行きになる。
            # 契約 SSoT: apps/workers/grading/internal/grading/generation_prompt.go の TestCase
            test_cases=[{"input": [], "expected": None}],
            reference_solution="x",
            judge_scores={},
        )
        session.add(problem)
        await session.flush()
        problem_id = problem.id
        if deleted:
            problem.deleted_at = datetime.now(UTC)
    return problem_id


async def _create_submission(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    problem_id: uuid.UUID,
    status: str = "graded",
    passed: bool | None = True,
    deleted: bool = False,
) -> uuid.UUID:
    """テスト用 submission を 1 件作る。

    passed=None なら result を None にして「採点未完了」状態を作る。
    passed が True / False なら result.passed = ... を埋めて採点完了とみなす。
    """
    async with session.begin():
        sub = Submission(user_id=user_id, problem_id=problem_id, code="x")
        sub.status = status
        if passed is None:
            sub.result = None
        else:
            # 採点完了行：result JSONB に passed を含める（Service / Worker 契約）。
            result: dict[str, Any] = {
                "passed": passed,
                "durationMs": 100,
                "testResults": [],
            }
            sub.result = result
        session.add(sub)
        await session.flush()
        sub_id = sub.id
        if deleted:
            sub.deleted_at = datetime.now(UTC)
    return sub_id


class TestAggregateByCategory:
    async def test_正常系_カテゴリ別にattempts_correctが集計される(
        self, session: AsyncSession
    ) -> None:
        user_id = await _create_user(session)
        # array: 3 件中 2 件正解 / recursion: 2 件中 0 件正解。
        array_problem = await _create_problem(session, category="array")
        recursion_problem = await _create_problem(session, category="recursion")
        await _create_submission(
            session, user_id=user_id, problem_id=array_problem, passed=True
        )
        await _create_submission(
            session, user_id=user_id, problem_id=array_problem, passed=True
        )
        await _create_submission(
            session, user_id=user_id, problem_id=array_problem, passed=False
        )
        await _create_submission(
            session, user_id=user_id, problem_id=recursion_problem, passed=False
        )
        await _create_submission(
            session, user_id=user_id, problem_id=recursion_problem, passed=False
        )

        repo = MeRepository(session)
        rows = await repo.aggregate_by_category(user_id=user_id)

        # category ASC で並ぶ契約。array → recursion。
        assert [r.category for r in rows] == ["array", "recursion"]
        assert rows[0].attempts == 3
        assert rows[0].correct == 2
        assert rows[1].attempts == 2
        assert rows[1].correct == 0

    async def test_異常系_pendingやfailedはattemptsにカウントされない(
        self, session: AsyncSession
    ) -> None:
        """採点完了行（status='graded'）のみが母数になる契約。

        learning.md §ビジネスルールに追加した「採点完了行のみ集計」を
        SQL レベルで担保していることを観測する。
        """
        user_id = await _create_user(session)
        problem_id = await _create_problem(session, category="array")
        await _create_submission(
            session, user_id=user_id, problem_id=problem_id, passed=True
        )
        # pending（採点中、result NULL）は対象外。
        await _create_submission(
            session,
            user_id=user_id,
            problem_id=problem_id,
            status="pending",
            passed=None,
        )
        # failed（インフラ起因失敗）は正答判定不能のため対象外。
        await _create_submission(
            session,
            user_id=user_id,
            problem_id=problem_id,
            status="failed",
            passed=None,
        )

        repo = MeRepository(session)
        rows = await repo.aggregate_by_category(user_id=user_id)

        # graded 1 件だけが残る。
        assert len(rows) == 1
        assert rows[0].category == "array"
        assert rows[0].attempts == 1
        assert rows[0].correct == 1

    async def test_他人のsubmissionは混ざらない(self, session: AsyncSession) -> None:
        owner_id = await _create_user(session, name="Owner")
        other_id = await _create_user(session, name="Other")
        problem_id = await _create_problem(session, category="array")
        await _create_submission(
            session, user_id=owner_id, problem_id=problem_id, passed=True
        )
        await _create_submission(
            session, user_id=other_id, problem_id=problem_id, passed=False
        )

        repo = MeRepository(session)
        rows = await repo.aggregate_by_category(user_id=owner_id)

        # owner の 1 件のみ。other の 1 件は無関係。
        assert len(rows) == 1
        assert rows[0].attempts == 1
        assert rows[0].correct == 1

    async def test_ソフトデリート行も統計には含まれる(
        self, session: AsyncSession
    ) -> None:
        """learning.md §ビジネスルール：
        統計クエリは deleted_at を無視して全行を集計する（履歴永続保存）。

        submission 側 / problem 側どちらの deleted_at も無視されることを観測する。
        """
        user_id = await _create_user(session)
        alive_problem = await _create_problem(session, category="array")
        dead_problem = await _create_problem(
            session, category="recursion", deleted=True
        )
        # 生きてる submission（生きてる問題）。
        await _create_submission(
            session, user_id=user_id, problem_id=alive_problem, passed=True
        )
        # 削除済み submission（生きてる問題）。
        await _create_submission(
            session,
            user_id=user_id,
            problem_id=alive_problem,
            passed=False,
            deleted=True,
        )
        # 生きてる submission（削除済み問題）。
        await _create_submission(
            session, user_id=user_id, problem_id=dead_problem, passed=False
        )

        repo = MeRepository(session)
        rows = await repo.aggregate_by_category(user_id=user_id)

        # 3 件すべてが集計対象。array 2 件 / recursion 1 件。
        by_cat = {r.category: r for r in rows}
        assert by_cat["array"].attempts == 2
        assert by_cat["array"].correct == 1
        assert by_cat["recursion"].attempts == 1
        assert by_cat["recursion"].correct == 0

    async def test_履歴ゼロのユーザーは空配列(self, session: AsyncSession) -> None:
        user_id = await _create_user(session)
        repo = MeRepository(session)

        rows = await repo.aggregate_by_category(user_id=user_id)

        assert rows == []
