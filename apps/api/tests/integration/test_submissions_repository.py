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

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.problems import Problem
from app.models.submissions import Submission
from app.repositories.submissions import SubmissionRepository

from ._factories import create_problem, create_submission, create_user


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


class TestGetByIdForUser:
    async def test_正常系_自分のIDなら取得できる(
        self, session: AsyncSession
    ) -> None:
        owner_id = await create_user(session)
        problem_id = await create_problem(session)
        # 採点前の生 INSERT 状態（status=pending / result=None）を観測したいので明示する。
        sub_id = await create_submission(
            session,
            user_id=owner_id,
            problem_id=problem_id,
            status="pending",
            passed=None,
        )
        repo = SubmissionRepository(session)

        loaded = await repo.get_by_id_for_user(submission_id=sub_id, user_id=owner_id)

        assert loaded is not None
        assert loaded.id == sub_id
        assert loaded.user_id == owner_id
        assert loaded.status == "pending"

    async def test_異常系_他人のIDならNone(self, session: AsyncSession) -> None:
        """情報漏洩防止：他人の id を渡しても None（存在チェックも兼ねる契約）。"""
        owner_id = await create_user(session, name="Owner")
        problem_id = await create_problem(session)
        sub_id = await create_submission(
            session, user_id=owner_id, problem_id=problem_id
        )
        # 別ユーザーを作って観測する。
        other_id = await create_user(session, name="Other")
        repo = SubmissionRepository(session)

        loaded = await repo.get_by_id_for_user(submission_id=sub_id, user_id=other_id)
        assert loaded is None

    async def test_異常系_存在しないIDならNone(self, session: AsyncSession) -> None:
        owner_id = await create_user(session)
        repo = SubmissionRepository(session)

        loaded = await repo.get_by_id_for_user(
            submission_id=uuid.uuid4(), user_id=owner_id
        )
        assert loaded is None

    async def test_異常系_ソフトデリートされたsubmissionは見えない(
        self, session: AsyncSession
    ) -> None:
        """deleted_at IS NOT NULL の行は WHERE で除外される契約。"""
        owner_id = await create_user(session)
        problem_id = await create_problem(session)
        sub_id = await create_submission(
            session, user_id=owner_id, problem_id=problem_id, deleted=True
        )
        repo = SubmissionRepository(session)

        loaded = await repo.get_by_id_for_user(submission_id=sub_id, user_id=owner_id)
        assert loaded is None


class TestListForUser:
    async def test_正常系_自分の解答のみ返り_他人の解答は混ざらない(
        self, session: AsyncSession
    ) -> None:
        owner_id = await create_user(session, name="Owner")
        other_id = await create_user(session, name="Other")
        problem_id = await create_problem(session)
        await create_submission(session, user_id=owner_id, problem_id=problem_id)
        await create_submission(session, user_id=other_id, problem_id=problem_id)
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
        owner_id = await create_user(session)
        problem_id = await create_problem(session)
        old_id = await create_submission(
            session, user_id=owner_id, problem_id=problem_id, code="old"
        )
        new_id = await create_submission(
            session, user_id=owner_id, problem_id=problem_id, code="new"
        )
        repo = SubmissionRepository(session)

        items, _ = await repo.list_for_user(user_id=owner_id, page=1, page_size=20)

        # 新着が先頭に来る契約（grading.md §JSON 例 #get-submissions）。
        assert [s.id for s in items] == [new_id, old_id]

    async def test_正常系_pageとpage_sizeでスライスされる(
        self, session: AsyncSession
    ) -> None:
        owner_id = await create_user(session)
        problem_id = await create_problem(session)
        # 3 件作って page_size=2 で 1 ページ目 / 2 ページ目を観測する。
        for _ in range(3):
            await create_submission(
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
        owner_id = await create_user(session)
        problem_id = await create_problem(session)
        await create_submission(
            session, user_id=owner_id, problem_id=problem_id, deleted=True
        )
        await create_submission(
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
        owner_id = await create_user(session)
        alive_problem_id = await create_problem(session, title="生きてる問題")
        dead_problem_id = await create_problem(
            session, title="削除済み問題", deleted=True
        )
        await create_submission(
            session, user_id=owner_id, problem_id=alive_problem_id
        )
        await create_submission(
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
        owner_id = await create_user(session)
        repo = SubmissionRepository(session)

        items, total = await repo.list_for_user(
            user_id=owner_id, page=1, page_size=20
        )

        assert items == []
        assert total == 0
