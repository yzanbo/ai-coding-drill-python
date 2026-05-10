from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from app.db.session import AsyncSessionLocal
from app.main import app
from app.models import HealthCheck


@pytest.fixture
async def reset_health_check_table() -> AsyncIterator[None]:
    """各テスト前に health_check テーブルを空にする。

    integration テストは実 DB を使うため、テスト間の独立性を保つために
    fixture で前処理する。新しいテーブルが追加されたら本 fixture を拡張するか、
    機能ごとに別 fixture を切り分ける。
    """
    async with AsyncSessionLocal() as session:
        await session.execute(delete(HealthCheck))
        await session.commit()
    yield


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """ASGI in-process クライアント（外部 HTTP 不要）。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
