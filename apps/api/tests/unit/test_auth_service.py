# services/auth.AuthService のユニットテスト。
#
# テスト方針（ADR 0044）：
#   - UserRepository / AuthProviderRepository は AsyncMock でスタブ化
#   - DB セッションも MagicMock（async with session.begin() を素通り）
#   - Redis は fakeredis で本物相当の動作を確認（session_store の内部呼び出しまで通す）
#
# 関わる要件：
#   - authentication.md §1.1 同一プロバイダの同一外部 ID = 同一ユーザー
#   - §2.1 既存なら再ログインで profile を最新値で上書き / 新規なら users+auth_providers 作成

import uuid
from collections.abc import Awaitable
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest

from app.models.auth_providers import AuthProvider
from app.models.users import User
from app.schemas.auth import UserSyncInput
from app.services.auth import AuthService


@pytest.fixture
def mock_session() -> MagicMock:
    """async with session.begin(): を素通りさせる DB セッションのモック。

    session.begin() は coroutine ではなく同期で context manager を返す API のため
    MagicMock 側に置く。返ってきた context manager の __aenter__ / __aexit__ は
    awaitable であってほしいので AsyncMock を入れる。
    """
    session = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=None)
    cm.__aexit__ = AsyncMock(return_value=None)
    session.begin.return_value = cm
    return session


@pytest.fixture
async def redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def mock_users_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_providers_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    mock_session: MagicMock,
    redis: fakeredis.aioredis.FakeRedis,
    mock_users_repo: AsyncMock,
    mock_providers_repo: AsyncMock,
) -> AuthService:
    # AuthService(db_session, redis) で内部に Repository を生成するが、
    # 直後に AsyncMock 版で置き換えてビジネスロジックだけを観察する。
    s = AuthService(mock_session, redis)
    s.users = mock_users_repo  # type: ignore[assignment]
    s.providers = mock_providers_repo  # type: ignore[assignment]
    return s


def _make_user(user_id: uuid.UUID | None = None, name: str = "Taro") -> User:
    """ORM オブジェクトを最小フィールドで組み立てる（実 DB を経由しない）。"""
    u = User(display_name=name, email=None)
    u.id = user_id or uuid.uuid4()
    return u


def _make_provider(user_id: uuid.UUID, provider_id: str = "12345") -> AuthProvider:
    return AuthProvider(provider="github", provider_id=provider_id, user_id=user_id)


async def _hgetall(
    redis: fakeredis.aioredis.FakeRedis, key: str
) -> dict[str, str]:
    """fakeredis の hgetall を pyright に awaitable と認識させるラッパ。"""
    return await cast("Awaitable[dict[str, str]]", redis.hgetall(key))


class TestLoginWithGithubNewUser:
    async def test_正常系_既存紐付け無しならusers_create_と_providers_createを呼ぶ(
        self,
        service: AuthService,
        mock_users_repo: AsyncMock,
        mock_providers_repo: AsyncMock,
    ) -> None:
        mock_providers_repo.get_by_provider_id.return_value = None
        new_user = _make_user(name="Taro")
        mock_users_repo.create.return_value = new_user

        payload = UserSyncInput(
            provider_id="12345",
            display_name="Taro",
            email="taro@example.com",
        )
        result = await service.login_with_github(payload)

        # users.create が呼ばれる（display_name と email を渡す）。
        mock_users_repo.create.assert_called_once_with(
            display_name="Taro",
            email="taro@example.com",
        )
        # auth_providers.create が user.id 込みで呼ばれる。
        mock_providers_repo.create.assert_called_once_with(
            provider="github",
            provider_id="12345",
            user_id=new_user.id,
        )
        # update_profile は呼ばれない（新規ユーザーなので）。
        mock_users_repo.update_profile.assert_not_called()
        # 返り値の UserResponse には新規 user の情報が乗る。
        assert result.user.id == new_user.id
        assert result.user.display_name == "Taro"

    async def test_正常系_新規ユーザーのRedisセッションが作成される(
        self,
        service: AuthService,
        redis: fakeredis.aioredis.FakeRedis,
        mock_users_repo: AsyncMock,
        mock_providers_repo: AsyncMock,
    ) -> None:
        mock_providers_repo.get_by_provider_id.return_value = None
        new_user = _make_user()
        mock_users_repo.create.return_value = new_user

        result = await service.login_with_github(
            UserSyncInput(provider_id="1", display_name="X", email=None)
        )

        # Redis 上に session:<sid> が作られている。
        stored = await _hgetall(redis, f"session:{result.sid}")
        assert stored.get("user_id") == str(new_user.id)
        assert stored.get("csrf_token") == result.csrf_token


class TestLoginWithGithubExistingUser:
    async def test_正常系_既存紐付けありならupdate_profileを呼ぶ(
        self,
        service: AuthService,
        mock_users_repo: AsyncMock,
        mock_providers_repo: AsyncMock,
    ) -> None:
        existing_user = _make_user(name="Taro old")
        link = _make_provider(existing_user.id)
        mock_providers_repo.get_by_provider_id.return_value = link

        updated_user = _make_user(user_id=existing_user.id, name="Taro new")
        mock_users_repo.update_profile.return_value = updated_user

        payload = UserSyncInput(
            provider_id="12345",
            display_name="Taro new",
            email="new@example.com",
        )
        result = await service.login_with_github(payload)

        mock_users_repo.update_profile.assert_called_once_with(
            user_id=existing_user.id,
            display_name="Taro new",
            email="new@example.com",
        )
        # 新規ユーザー側のクエリは呼ばれない。
        mock_users_repo.create.assert_not_called()
        mock_providers_repo.create.assert_not_called()
        # 返り値は更新後の display_name。
        assert result.user.display_name == "Taro new"

    async def test_異常系_provider_link有り_users更新でNoneならRuntimeError(
        self,
        service: AuthService,
        mock_users_repo: AsyncMock,
        mock_providers_repo: AsyncMock,
    ) -> None:
        """CASCADE 削除と並走する稀ケース。新規作成にフォールバックせず明示エラー。"""
        link = _make_provider(uuid.uuid4())
        mock_providers_repo.get_by_provider_id.return_value = link
        mock_users_repo.update_profile.return_value = None

        with pytest.raises(RuntimeError):
            await service.login_with_github(
                UserSyncInput(provider_id="1", display_name="x", email=None)
            )


class TestLogout:
    async def test_正常系_logoutでRedis上のセッションが消える(
        self,
        service: AuthService,
        redis: fakeredis.aioredis.FakeRedis,
        mock_users_repo: AsyncMock,
        mock_providers_repo: AsyncMock,
    ) -> None:
        # 事前にセッションを作る。
        mock_providers_repo.get_by_provider_id.return_value = None
        mock_users_repo.create.return_value = _make_user()
        created = await service.login_with_github(
            UserSyncInput(provider_id="1", display_name="X", email=None)
        )

        # ログアウト後は Redis から消える。
        await service.logout(created.sid)
        stored = await _hgetall(redis, f"session:{created.sid}")
        assert stored == {}


class TestGetCurrentUser:
    async def test_正常系_users_get_by_idに委譲する(
        self, service: AuthService, mock_users_repo: AsyncMock
    ) -> None:
        user = _make_user()
        mock_users_repo.get_by_id.return_value = user

        result = await service.get_current_user(user.id)

        mock_users_repo.get_by_id.assert_called_once_with(user.id)
        assert result is user

    async def test_正常系_存在しないuser_idならNoneを返す(
        self, service: AuthService, mock_users_repo: AsyncMock
    ) -> None:
        mock_users_repo.get_by_id.return_value = None

        result = await service.get_current_user(uuid.uuid4())
        assert result is None
