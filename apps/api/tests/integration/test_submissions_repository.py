# SubmissionRepository の結合テスト（実 Postgres）。
#
# テスト方針：
#   - 実 DB に対して SQL 挙動を直接検証（Service 単体テストでは Repository を
#     モックしていたので、Repository 自体は実 DB で SQL の効果を検証する、ADR 0044）
#   - submissions は users / problems の FK を持つので、テストごとに先に両方を作る
#   - integration/conftest.py の reset_auth_tables（autouse）で users / auth_providers
#     はクリアされるが、submissions / problems は別途消す必要があるので独自 fixture を
#     追加（test_generation_requests_repository.py と同じパターン）
#
# 関わる要件：
#   - docs/requirements/4-features/grading.md §API
#   - docs/requirements/3-cross-cutting/01-data-model.md（FK / ソフトデリート方針）

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.problems import Problem
from app.models.submissions import Submission
from app.repositories.submissions import SubmissionRepository
from app.repositories.users import UserRepository


@pytest.fixture(autouse=True)
async def reset_submissions_problems_tables() -> AsyncIterator[None]:
    """各テスト前に submissions / problems を空にする（テスト間の独立性）。

    submissions が users.id / problems.id を FK 参照するため、users が
    autouse の reset_auth_tables で消される前に submissions を先に消す。
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
    """テスト用ユーザーを 1 件作って id を返す（FK 制約を満たすため）。"""
    users = UserRepository(session)
    async with session.begin():
        user = await users.create(display_name=name, email=None)
    return user.id


async def _create_problem(
    session: AsyncSession,
    *,
    title: str = "配列の合計",
    deleted: bool = False,
) -> uuid.UUID:
    """テスト用 problem を 1 件作って id を返す。deleted=True ならソフトデリート印を付ける。"""
    async with session.begin():
        problem = Problem(
            title=title,
            description="合計を返してください",
            category="array",
            difficulty="easy",
            language="typescript",
            examples=[{"input": "[1,2,3]", "output": "6"}],
            test_cases=[{"input": "[1,2,3]", "expected": "6"}],
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
    code: str = "x",
    deleted: bool = False,
) -> uuid.UUID:
    """テスト用 submission を 1 件作って id を返す。"""
    async with session.begin():
        sub = Submission(user_id=user_id, problem_id=problem_id, code=code)
        session.add(sub)
        await session.flush()
        sub_id = sub.id
        if deleted:
            sub.deleted_at = datetime.now(UTC)
    return sub_id


class TestGetByIdForUser:
    async def test_正常系_自分のIDなら取得できる(
        self, session: AsyncSession
    ) -> None:
        owner_id = await _create_user(session)
        problem_id = await _create_problem(session)
        sub_id = await _create_submission(
            session, user_id=owner_id, problem_id=problem_id
        )
        repo = SubmissionRepository(session)

        loaded = await repo.get_by_id_for_user(submission_id=sub_id, user_id=owner_id)

        assert loaded is not None
        assert loaded.id == sub_id
        assert loaded.user_id == owner_id
        assert loaded.status == "pending"

    async def test_異常系_他人のIDならNone(self, session: AsyncSession) -> None:
        """情報漏洩防止：他人の id を渡しても None（存在チェックも兼ねる契約）。"""
        owner_id = await _create_user(session, name="Owner")
        problem_id = await _create_problem(session)
        sub_id = await _create_submission(
            session, user_id=owner_id, problem_id=problem_id
        )
        # 別ユーザーを作って観測する。
        other_id = await _create_user(session, name="Other")
        repo = SubmissionRepository(session)

        loaded = await repo.get_by_id_for_user(submission_id=sub_id, user_id=other_id)
        assert loaded is None

    async def test_異常系_存在しないIDならNone(self, session: AsyncSession) -> None:
        owner_id = await _create_user(session)
        repo = SubmissionRepository(session)

        loaded = await repo.get_by_id_for_user(
            submission_id=uuid.uuid4(), user_id=owner_id
        )
        assert loaded is None

    async def test_異常系_ソフトデリートされたsubmissionは見えない(
        self, session: AsyncSession
    ) -> None:
        """deleted_at IS NOT NULL の行は WHERE で除外される契約。"""
        owner_id = await _create_user(session)
        problem_id = await _create_problem(session)
        sub_id = await _create_submission(
            session, user_id=owner_id, problem_id=problem_id, deleted=True
        )
        repo = SubmissionRepository(session)

        loaded = await repo.get_by_id_for_user(submission_id=sub_id, user_id=owner_id)
        assert loaded is None


class TestListForUser:
    async def test_正常系_自分の解答のみ返り_他人の解答は混ざらない(
        self, session: AsyncSession
    ) -> None:
        owner_id = await _create_user(session, name="Owner")
        other_id = await _create_user(session, name="Other")
        problem_id = await _create_problem(session)
        await _create_submission(session, user_id=owner_id, problem_id=problem_id)
        await _create_submission(session, user_id=other_id, problem_id=problem_id)
        repo = SubmissionRepository(session)

        items, total = await repo.list_for_user(
            user_id=owner_id, page=1, page_size=20
        )

        assert total == 1
        assert len(items) == 1
        # contains_eager で problem 関連が事前ロードされており、追加 SQL なしで
        # submission.problem.title が読める契約。
        sub = items[0]
        assert sub.user_id == owner_id
        assert sub.problem.title == "配列の合計"

    async def test_正常系_並び順はcreated_at_DESC(
        self, session: AsyncSession
    ) -> None:
        owner_id = await _create_user(session)
        problem_id = await _create_problem(session)
        old_id = await _create_submission(
            session, user_id=owner_id, problem_id=problem_id, code="old"
        )
        new_id = await _create_submission(
            session, user_id=owner_id, problem_id=problem_id, code="new"
        )
        repo = SubmissionRepository(session)

        items, _ = await repo.list_for_user(user_id=owner_id, page=1, page_size=20)

        # 新着が先頭に来る契約（grading.md §JSON 例 #get-submissions）。
        assert [s.id for s in items] == [new_id, old_id]

    async def test_正常系_pageとpage_sizeでスライスされる(
        self, session: AsyncSession
    ) -> None:
        owner_id = await _create_user(session)
        problem_id = await _create_problem(session)
        # 3 件作って page_size=2 で 1 ページ目 / 2 ページ目を観測する。
        for _ in range(3):
            await _create_submission(
                session, user_id=owner_id, problem_id=problem_id
            )
        repo = SubmissionRepository(session)

        page1, total1 = await repo.list_for_user(
            user_id=owner_id, page=1, page_size=2
        )
        page2, total2 = await repo.list_for_user(
            user_id=owner_id, page=2, page_size=2
        )

        # 全件数は同じ。
        assert total1 == 3
        assert total2 == 3
        # 1 ページ目は 2 件、2 ページ目は 1 件。
        assert len(page1) == 2
        assert len(page2) == 1

    async def test_異常系_ソフトデリートされたsubmissionは履歴に出ない(
        self, session: AsyncSession
    ) -> None:
        owner_id = await _create_user(session)
        problem_id = await _create_problem(session)
        await _create_submission(
            session, user_id=owner_id, problem_id=problem_id, deleted=True
        )
        await _create_submission(
            session, user_id=owner_id, problem_id=problem_id
        )
        repo = SubmissionRepository(session)

        items, total = await repo.list_for_user(
            user_id=owner_id, page=1, page_size=20
        )

        # deleted_at IS NULL のものだけ残る。
        assert total == 1
        assert len(items) == 1

    async def test_異常系_ソフトデリートされたproblemの解答は履歴に出ない(
        self, session: AsyncSession
    ) -> None:
        """JOIN 側（problems）の deleted_at も WHERE で除外される契約。

        問題が消えた後でも履歴に出すと title が陳腐化するため、両側で除外する。
        """
        owner_id = await _create_user(session)
        alive_problem_id = await _create_problem(session, title="生きてる問題")
        dead_problem_id = await _create_problem(
            session, title="削除済み問題", deleted=True
        )
        await _create_submission(
            session, user_id=owner_id, problem_id=alive_problem_id
        )
        await _create_submission(
            session, user_id=owner_id, problem_id=dead_problem_id
        )
        repo = SubmissionRepository(session)

        items, total = await repo.list_for_user(
            user_id=owner_id, page=1, page_size=20
        )

        assert total == 1
        assert len(items) == 1
        assert items[0].problem.title == "生きてる問題"

    async def test_正常系_0件なら空配列とtotal0(self, session: AsyncSession) -> None:
        owner_id = await _create_user(session)
        repo = SubmissionRepository(session)

        items, total = await repo.list_for_user(
            user_id=owner_id, page=1, page_size=20
        )

        assert items == []
        assert total == 0
