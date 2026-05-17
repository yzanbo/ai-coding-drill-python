# integration テスト用の共通フィクスチャ。
#
# 設計方針：
#   - DB は実 Postgres を使う（docker compose 起動済み前提、conftest.py の AsyncSessionLocal）
#   - Redis は fakeredis を app.core.redis._client に直接差し込む
#     （ASGITransport は lifespan を起動しないので、auth ルートが呼ぶ get_redis() の
#      失敗を防ぐためにモジュール変数を埋める）
#   - 共有 httpx クライアントも lifespan が走らないため fixture で open/close
#   - GitHub API は respx で intercept（テスト関数側で @respx.mock + ルート設定）
#
# 関わる要件：
#   - authentication.md §1〜§2 全体

from collections.abc import AsyncIterator

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.core import redis as redis_module
from app.core.http_client import close_http_client, open_http_client
from app.db.session import AsyncSessionLocal
from app.main import app
from app.models.auth_providers import AuthProvider
from app.models.users import User


@pytest.fixture(autouse=True)
async def reset_auth_tables() -> AsyncIterator[None]:
    """各テスト前に auth_providers / users を空にする（テスト間の独立性）。"""
    async with AsyncSessionLocal() as session:
        # auth_providers が users.id を FK 参照しているので、先に auth_providers を消す。
        await session.execute(delete(AuthProvider))
        await session.execute(delete(User))
        await session.commit()
    yield


@pytest.fixture
async def fake_redis() -> AsyncIterator[fakeredis.aioredis.FakeRedis]:
    """fakeredis を app.core.redis._client にセットし、テスト後に剥がす。

    monkeypatch を使わず手動で書き換える理由：
      - app.core.redis モジュールの `_client` がモジュール変数。
        monkeypatch.setattr に文字列パスで渡せるが、auto-cleanup タイミングが
        non-async fixture と混ざると分かりにくい。明示的に setup/teardown する。
    """
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    redis_module._client = fake
    yield fake
    redis_module._client = None
    await fake.aclose()


@pytest.fixture
async def http_lifespan() -> AsyncIterator[None]:
    """services.github_oauth が呼ぶ get_http_client() のために共有 httpx を開閉する。

    respx は httpx の transport をフックして intercept するため、実 httpx クライアント
    で問題ない（外向き通信は発生しない）。
    """
    await open_http_client()
    yield
    await close_http_client()


@pytest.fixture
async def client(
    fake_redis: fakeredis.aioredis.FakeRedis,
    http_lifespan: None,
) -> AsyncIterator[AsyncClient]:
    """auth ルートを叩くための ASGI in-process クライアント。

    fake_redis / http_lifespan に依存することで、ASGITransport が lifespan を
    起動しなくても auth ルートに必要なモジュール singleton が揃う。
    """
    del fake_redis, http_lifespan  # 依存だけ取って参照は不要
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=False,  # 302 を観測したいのでリダイレクト追従しない
    ) as ac:
        yield ac
