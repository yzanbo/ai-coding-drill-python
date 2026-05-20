# deps/auth.get_current_user_optional のユニットテスト。
#
# テスト方針：
#   - get_current_user_optional は「ゲスト許容」用途。Cookie 無し / 署名不正 /
#     Redis セッション不在のいずれでも None を返すことが契約（authentication.md
#     §1.1「問題閲覧はゲストでも可能」の実装根拠）
#   - 必須版 get_current_user は _optional を呼ぶ薄いラッパなので、_optional の
#     3 つの分岐を抑えれば十分（必須版で 401 を投げる経路は integration で検証済）
#   - Redis は fakeredis、DB セッションは AsyncMock、AuthService は monkeypatch
#     で AsyncMock に差し替える
#
# 関わる要件：
#   - authentication.md §1.1 匿名利用は不可だがゲスト閲覧は許容
#   - §1.4 GET /auth/me は認証必須（必須版が 401 を投げる根拠は integration 側）

import uuid
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis
import pytest

from app.core import session as session_store
from app.core.config import get_settings
from app.core.cookies import sign_sid
from app.deps import auth as deps_auth
from app.deps.auth import get_current_user_optional
from app.models.users import User


@pytest.fixture
async def redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _mock_request_with_cookies(cookies: dict[str, str]) -> MagicMock:
    """fastapi.Request の最小モック。cookies 属性だけ持つ。"""
    req = MagicMock()
    req.cookies = cookies
    return req


class TestGetCurrentUserOptional:
    async def test_正常系_Cookieが無ければNone(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        request = _mock_request_with_cookies({})
        result = await get_current_user_optional(
            request, db_session=AsyncMock(), redis=redis
        )
        assert result is None

    async def test_正常系_署名不正のCookieならNone(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        cookie_name = get_settings().session_cookie_name
        request = _mock_request_with_cookies({cookie_name: "garbage.value"})
        result = await get_current_user_optional(
            request, db_session=AsyncMock(), redis=redis
        )
        assert result is None

    async def test_正常系_署名は通るがRedisにセッションが無ければNone(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        cookie_name = get_settings().session_cookie_name
        # session_store.create を呼ばずに sign_sid だけする = Redis 上にハッシュなし。
        request = _mock_request_with_cookies({cookie_name: sign_sid("ghost-sid")})
        result = await get_current_user_optional(
            request, db_session=AsyncMock(), redis=redis
        )
        assert result is None

    async def test_正常系_セッションが有効ならAuthService経由でUserが返る(
        self,
        redis: fakeredis.aioredis.FakeRedis,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """deps/auth.py の最終分岐：AuthService(db, redis).get_current_user(user_id)。"""
        cookie_name = get_settings().session_cookie_name

        # 事前にセッションを作っておく（fakeredis 上に hash + set が出る）。
        user_id = uuid.uuid4()
        created = await session_store.create(redis, user_id)

        # AuthService をスタブ化：get_current_user が呼ばれたら fake_user を返す。
        fake_user = User(display_name="X", email=None)
        fake_user.id = user_id

        service_stub = AsyncMock()
        service_stub.get_current_user.return_value = fake_user
        service_factory = MagicMock(return_value=service_stub)
        monkeypatch.setattr(deps_auth, "AuthService", service_factory)

        # 認証ルックアップは `async with db_session.begin():` で包まれるため、
        # session.begin() の戻り値が async context manager の interface を
        # 満たす MagicMock を渡す（test_auth_service.py / test_problem_generation_service.py
        # と同じパターン）。
        db_session_mock = MagicMock()
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=None)
        cm.__aexit__ = AsyncMock(return_value=None)
        db_session_mock.begin.return_value = cm

        request = _mock_request_with_cookies({cookie_name: sign_sid(created.sid)})
        result = await get_current_user_optional(
            request, db_session=db_session_mock, redis=redis
        )

        # 戻り値が AuthService.get_current_user の返した User。
        assert result is fake_user
        # AuthService.get_current_user に Redis 上のセッションから引いた user_id が渡る。
        service_stub.get_current_user.assert_awaited_once_with(user_id)
