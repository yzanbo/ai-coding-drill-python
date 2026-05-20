# GenerationRequestRepository の結合テスト（実 Postgres）。
#
# テスト方針：
#   - 実 DB に対して SQL 挙動を直接検証（Service 単体テストでは Repository を
#     モックしていたので、Repository 自体は実 DB で SQL の効果を検証する、ADR 0044）
#   - generation_requests は users.id FK を持つので、テストごとに先に users を作る
#   - integration/conftest.py の reset_auth_tables（autouse）で users / auth_providers
#     はクリアされるが、generation_requests は別途消す必要があるので独自 fixture を追加
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md
#   - docs/requirements/3-cross-cutting/01-data-model.md（FK / ハードデリート方針）

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.generation_requests import GenerationRequest
from app.repositories.generation_requests import GenerationRequestRepository
from app.repositories.users import UserRepository


@pytest.fixture(autouse=True)
async def reset_generation_requests_table() -> AsyncIterator[None]:
    """各テスト前に generation_requests を空にする（テスト間の独立性）。

    integration/conftest.py の reset_auth_tables は users を消す前に
    auth_providers だけ消しているが、generation_requests も users.id を
    FK 参照しているので、users 削除と並走して FK 違反になる前に先に消す。
    """
    async with AsyncSessionLocal() as session:
        await session.execute(delete(GenerationRequest))
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


class TestCreate:
    async def test_正常系_INSERTで_id_created_at_updated_at_status_pending_が埋まる(
        self, session: AsyncSession
    ) -> None:
        user_id = await _create_user(session)
        repo = GenerationRequestRepository(session)

        async with session.begin():
            gr = await repo.create(
                user_id=user_id,
                category="array",
                difficulty="easy",
            )

        # サーバ側 default が反映される。
        assert gr.id is not None
        assert gr.created_at is not None
        assert gr.updated_at is not None
        assert gr.status == "pending"
        assert gr.produced_problem_id is None
        # 入力した値はそのまま保存される。
        assert gr.user_id == user_id
        assert gr.category == "array"
        assert gr.difficulty == "easy"

    async def test_正常系_同じユーザーで複数件作っても全て別IDで保存される(
        self, session: AsyncSession
    ) -> None:
        user_id = await _create_user(session)
        repo = GenerationRequestRepository(session)

        async with session.begin():
            a = await repo.create(user_id=user_id, category="string", difficulty="easy")
            b = await repo.create(user_id=user_id, category="array", difficulty="hard")

        # gen_random_uuid() で別 ID。
        assert a.id != b.id


class TestGetByIdForUser:
    async def test_正常系_自分のIDで作成直後の行を引ける(
        self, session: AsyncSession
    ) -> None:
        user_id = await _create_user(session)
        repo = GenerationRequestRepository(session)

        async with session.begin():
            created = await repo.create(
                user_id=user_id, category="string", difficulty="medium"
            )

        loaded = await repo.get_by_id_for_user(
            request_id=created.id, user_id=user_id
        )
        assert loaded is not None
        assert loaded.id == created.id
        assert loaded.category == "string"
        assert loaded.difficulty == "medium"

    async def test_異常系_他人のリクエストIDを引こうとするとNone(
        self, session: AsyncSession
    ) -> None:
        """情報漏洩防止：他人 ID は「存在しない」と同じ扱いで None を返す。"""
        owner_id = await _create_user(session, name="owner")
        other_id = await _create_user(session, name="other")
        repo = GenerationRequestRepository(session)

        async with session.begin():
            created = await repo.create(
                user_id=owner_id, category="async", difficulty="hard"
            )

        # 別ユーザーから引くと None（行は存在するが見えない）。
        loaded = await repo.get_by_id_for_user(
            request_id=created.id, user_id=other_id
        )
        assert loaded is None

    async def test_異常系_存在しないrequest_idならNone(
        self, session: AsyncSession
    ) -> None:
        user_id = await _create_user(session)
        repo = GenerationRequestRepository(session)

        loaded = await repo.get_by_id_for_user(
            request_id=uuid.uuid4(), user_id=user_id
        )
        assert loaded is None

    async def test_異常系_存在しないuser_idならNone(
        self, session: AsyncSession
    ) -> None:
        """request_id 自体は存在しても、user_id が違えば None。"""
        owner_id = await _create_user(session)
        repo = GenerationRequestRepository(session)

        async with session.begin():
            created = await repo.create(
                user_id=owner_id, category="recursion", difficulty="medium"
            )

        loaded = await repo.get_by_id_for_user(
            request_id=created.id, user_id=uuid.uuid4()
        )
        assert loaded is None
