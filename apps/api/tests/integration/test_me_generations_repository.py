# MeGenerationsRepository の結合テスト（実 Postgres）。
#
# テスト方針：
#   - 実 DB に対して履歴クエリ / cancel UPDATE / WITH RECURSIVE CTE の挙動を直接検証
#   - jobs.payload JSONB から prompt_version を引く部分も DISTINCT ON で 1 行に絞れる
#     ことを確認
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md §履歴・状態管理 / §API

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.generation_requests import GenerationRequest
from app.models.jobs import Job
from app.repositories.generation_requests import GenerationRequestRepository
from app.repositories.me_generations import MeGenerationsRepository
from app.repositories.users import UserRepository


@pytest.fixture(autouse=True)
async def reset_generation_tables() -> AsyncIterator[None]:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Job))
        await session.execute(delete(GenerationRequest))
        await session.commit()
    yield


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as s:
        yield s


async def _create_user(session: AsyncSession, name: str = "Taro") -> uuid.UUID:
    users = UserRepository(session)
    async with session.begin():
        user = await users.create(display_name=name, email=None)
    return user.id


async def _create_gr(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    category: str = "array",
    difficulty: str = "easy",
    retry_of: uuid.UUID | None = None,
    status: str = "pending",
) -> uuid.UUID:
    repo = GenerationRequestRepository(session)
    async with session.begin():
        gr = await repo.create(
            user_id=user_id, category=category, difficulty=difficulty, retry_of=retry_of,
        )
        gr.status = status
    return gr.id


async def _create_job(
    session: AsyncSession,
    *,
    generation_request_id: uuid.UUID,
    prompt_version: str = "v1",
    state: str = "queued",
) -> int:
    async with session.begin():
        job = Job(
            queue="generation",
            type="problem.generate",
            payload={
                "generationRequestId": str(generation_request_id),
                "promptVersion": prompt_version,
            },
            state=state,
        )
        session.add(job)
        await session.flush()
        return job.id


class TestListForUser:
    async def test_正常系_created_at_DESC_でページネーション(
        self, session: AsyncSession
    ) -> None:
        user_id = await _create_user(session)
        for _ in range(5):
            await _create_gr(session, user_id=user_id)

        repo = MeGenerationsRepository(session)
        page1 = await repo.list_for_user(user_id=user_id, page=1, page_size=2)
        page2 = await repo.list_for_user(user_id=user_id, page=2, page_size=2)
        page3 = await repo.list_for_user(user_id=user_id, page=3, page_size=2)

        assert len(page1) == 2
        assert len(page2) == 2
        assert len(page3) == 1
        # DESC: page1[0] が一番新しい（一番後に作った）。
        assert page1[0].created_at >= page1[1].created_at >= page2[0].created_at

    async def test_他人の_generation_requests_は混ざらない(
        self, session: AsyncSession
    ) -> None:
        a = await _create_user(session, name="A")
        b = await _create_user(session, name="B")
        await _create_gr(session, user_id=a)
        await _create_gr(session, user_id=b)
        await _create_gr(session, user_id=b)

        repo = MeGenerationsRepository(session)
        a_rows = await repo.list_for_user(user_id=a, page=1, page_size=20)
        assert len(a_rows) == 1
        assert a_rows[0].user_id == a


class TestCountForUser:
    async def test_正常系_自分の総件数のみ(self, session: AsyncSession) -> None:
        a = await _create_user(session, name="A")
        b = await _create_user(session, name="B")
        await _create_gr(session, user_id=a)
        await _create_gr(session, user_id=a)
        await _create_gr(session, user_id=b)
        repo = MeGenerationsRepository(session)
        assert await repo.count_for_user(user_id=a) == 2
        assert await repo.count_for_user(user_id=b) == 1


class TestFetchPromptVersions:
    async def test_正常系_最新jobs_を採用_消えてればNone(
        self, session: AsyncSession
    ) -> None:
        user_id = await _create_user(session)
        gr1 = await _create_gr(session, user_id=user_id)
        gr2 = await _create_gr(session, user_id=user_id)  # jobs 無し

        # gr1 に古い jobs と新しい jobs を両方作る（最新が採用される契約）
        await _create_job(session, generation_request_id=gr1, prompt_version="v1")
        await _create_job(session, generation_request_id=gr1, prompt_version="v2")

        repo = MeGenerationsRepository(session)
        result = await repo.fetch_prompt_versions(generation_request_ids=[gr1, gr2])

        assert result[gr1] == "v2"  # 最新（jobs.id が大きい方）
        assert result[gr2] is None  # jobs が無い

    async def test_境界値_空リストは空dict(self, session: AsyncSession) -> None:
        repo = MeGenerationsRepository(session)
        assert await repo.fetch_prompt_versions(generation_request_ids=[]) == {}


class TestCancelPending:
    async def test_正常系_pending_を_canceled_に倒し_jobs_も_dead_に倒す(
        self, session: AsyncSession
    ) -> None:
        user_id = await _create_user(session)
        gr_id = await _create_gr(session, user_id=user_id, status="pending")
        job_id = await _create_job(
            session, generation_request_id=gr_id, state="queued"
        )

        repo = MeGenerationsRepository(session)
        async with session.begin():
            transitioned = await repo.cancel_pending(
                request_id=gr_id, user_id=user_id
            )
        assert transitioned is True

        # 再取得して状態確認
        async with AsyncSessionLocal() as s2:
            gr = await s2.get(GenerationRequest, gr_id)
            job = await s2.get(Job, job_id)
        assert gr is not None
        assert gr.status == "canceled"
        assert gr.completed_at is not None
        assert job is not None
        assert job.state == "dead"

    async def test_異常系_pending以外は何も更新しないでFalse(
        self, session: AsyncSession
    ) -> None:
        user_id = await _create_user(session)
        gr_id = await _create_gr(session, user_id=user_id, status="running")
        repo = MeGenerationsRepository(session)
        async with session.begin():
            transitioned = await repo.cancel_pending(
                request_id=gr_id, user_id=user_id
            )
        assert transitioned is False

    async def test_異常系_他人のリクエストは更新しない(
        self, session: AsyncSession
    ) -> None:
        a = await _create_user(session, name="A")
        b = await _create_user(session, name="B")
        gr_id = await _create_gr(session, user_id=a, status="pending")
        repo = MeGenerationsRepository(session)
        async with session.begin():
            transitioned = await repo.cancel_pending(
                request_id=gr_id, user_id=b
            )
        assert transitioned is False


class TestComputeRetryDepths:
    async def test_正常系_retry_チェーンの深さを返す(
        self, session: AsyncSession
    ) -> None:
        user_id = await _create_user(session)
        original = await _create_gr(session, user_id=user_id)
        retry1 = await _create_gr(session, user_id=user_id, retry_of=original)
        retry2 = await _create_gr(session, user_id=user_id, retry_of=retry1)
        retry3 = await _create_gr(session, user_id=user_id, retry_of=retry2)

        repo = MeGenerationsRepository(session)
        depths = await repo.compute_retry_depths(
            user_id=user_id,
            request_ids=[original, retry1, retry2, retry3],
        )
        assert depths[original] == 0
        assert depths[retry1] == 1
        assert depths[retry2] == 2
        assert depths[retry3] == 3

    async def test_異常系_他人の親は辿らない(self, session: AsyncSession) -> None:
        # A の original を B が retry することは Service 側ガードで起きないが、
        # 万一直接 INSERT された場合、A の row を B の chain に含めないことを観測。
        a = await _create_user(session, name="A")
        b = await _create_user(session, name="B")
        a_original = await _create_gr(session, user_id=a)
        # 直接 retry_of に他人を指す異常データ（実装では起き得ないが防御）
        b_retry = await _create_gr(session, user_id=b, retry_of=a_original)

        repo = MeGenerationsRepository(session)
        depths = await repo.compute_retry_depths(
            user_id=b, request_ids=[b_retry]
        )
        # b 視点では a_original を辿らないので depth=0
        assert depths[b_retry] == 0
