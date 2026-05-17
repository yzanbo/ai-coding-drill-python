# UserRepository / AuthProviderRepository の結合テスト（実 Postgres）。
#
# テスト方針：
#   - 実 DB に対して SQL 挙動を直接検証（Service 単体テストでは Repository を
#     モックしていたので、Repository 自体は実 DB で SQL の効果を検証する、ADR 0044）
#   - reset_auth_tables（conftest.py）で各テスト前にテーブルを空にする
#   - トランザクションは Service が握る契約のため、Repository テスト側で
#     async with session.begin(): をラップして実コミットを発生させる
#
# 関わる要件：
#   - authentication.md §1.1 同一プロバイダの同一外部 ID = 同一ユーザー
#   - §2.1 既存なら再ログインで profile を最新値で上書き
#   - 01-data-model.md（複合主キー / CASCADE）

import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.repositories.auth_providers import AuthProviderRepository
from app.repositories.users import UserRepository


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """テスト用に AsyncSession を払い出して終了時に破棄する。"""
    async with AsyncSessionLocal() as s:
        yield s


class TestUserRepository:
    async def test_正常系_createでINSERTされid_created_atが埋まる(
        self, session: AsyncSession
    ) -> None:
        repo = UserRepository(session)
        async with session.begin():
            user = await repo.create(display_name="Taro", email="taro@example.com")

        # gen_random_uuid() / NOW() の server_default が反映される。
        assert user.id is not None
        assert user.created_at is not None
        assert user.display_name == "Taro"
        assert user.email == "taro@example.com"

    async def test_正常系_get_by_idで作成直後のユーザーを引ける(
        self, session: AsyncSession
    ) -> None:
        repo = UserRepository(session)
        async with session.begin():
            created = await repo.create(display_name="A", email=None)

        loaded = await repo.get_by_id(created.id)
        assert loaded is not None
        assert loaded.id == created.id
        assert loaded.display_name == "A"

    async def test_異常系_get_by_idで存在しないUUIDならNone(
        self, session: AsyncSession
    ) -> None:
        repo = UserRepository(session)
        loaded = await repo.get_by_id(uuid.uuid4())
        assert loaded is None

    async def test_正常系_update_profileでdisplay_nameとemailが上書きされる(
        self, session: AsyncSession
    ) -> None:
        repo = UserRepository(session)
        async with session.begin():
            user = await repo.create(display_name="old", email="old@example.com")

        async with session.begin():
            updated = await repo.update_profile(
                user_id=user.id,
                display_name="new",
                email="new@example.com",
            )

        assert updated is not None
        assert updated.id == user.id
        assert updated.display_name == "new"
        assert updated.email == "new@example.com"

    async def test_正常系_update_profileのemailをNoneに更新できる(
        self, session: AsyncSession
    ) -> None:
        """GitHub の email 公開設定を OFF に変えた再ログインで email を消す挙動。"""
        repo = UserRepository(session)
        async with session.begin():
            user = await repo.create(display_name="x", email="x@example.com")

        async with session.begin():
            updated = await repo.update_profile(
                user_id=user.id,
                display_name="x",
                email=None,
            )

        assert updated is not None
        assert updated.email is None

    async def test_異常系_update_profileで存在しないUUIDならNone(
        self, session: AsyncSession
    ) -> None:
        """CASCADE 削除と並走する稀ケースで Service が RuntimeError を投げる根拠。"""
        repo = UserRepository(session)
        async with session.begin():
            updated = await repo.update_profile(
                user_id=uuid.uuid4(),
                display_name="x",
                email=None,
            )
        assert updated is None


class TestAuthProviderRepository:
    async def test_正常系_create_と_get_by_provider_idのround_trip(
        self, session: AsyncSession
    ) -> None:
        users = UserRepository(session)
        providers = AuthProviderRepository(session)

        async with session.begin():
            user = await users.create(display_name="x", email=None)
            await providers.create(
                provider="github",
                provider_id="12345",
                user_id=user.id,
            )

        link = await providers.get_by_provider_id(provider="github", provider_id="12345")
        assert link is not None
        assert link.provider == "github"
        assert link.provider_id == "12345"
        assert link.user_id == user.id

    async def test_異常系_get_by_provider_idで未登録の組み合わせはNone(
        self, session: AsyncSession
    ) -> None:
        providers = AuthProviderRepository(session)
        link = await providers.get_by_provider_id(provider="github", provider_id="no-such")
        assert link is None

    async def test_正常系_異なるproviderの同じprovider_idは別レコードとして共存(
        self, session: AsyncSession
    ) -> None:
        """複合主キー (provider, provider_id) の片方が違えば別ユーザー。"""
        users = UserRepository(session)
        providers = AuthProviderRepository(session)

        async with session.begin():
            u1 = await users.create(display_name="a", email=None)
            u2 = await users.create(display_name="b", email=None)
            await providers.create(provider="github", provider_id="100", user_id=u1.id)
            await providers.create(provider="google", provider_id="100", user_id=u2.id)

        gh = await providers.get_by_provider_id(provider="github", provider_id="100")
        gg = await providers.get_by_provider_id(provider="google", provider_id="100")
        assert gh is not None
        assert gg is not None
        assert gh.user_id != gg.user_id
