# POST /api/me/generations/:id/retry のレート制限の結合テスト。
#
# 要件:
#   - docs/requirements/4-features/problem-generation.md §ビジネスルール
#     「回数上限は設けず、レート制限（1 分 5 回）で吸収する」
#   - POST /api/problems/generate と同じ閾値（5/minute）に揃える
#
# テスト方針:
#   - conftest.py で RATE_LIMIT_STORAGE_URI=memory:// が仕込まれているため Redis 不要
#   - 1 回 retry するごとに新規 failed 行を入れ直して 5 回まで 202 / 6 回目 429 を観測
#   - key 関数は user:<id> 単位（deps/rate_limit.py の get_rate_limit_key）。
#     既存 test_problems_rate_limit.py でユーザー単位カウンタ分離は検証済みのため、
#     本ファイルでは閾値 + 429 ハンドラ整合のみを担保する。

import uuid
from collections.abc import AsyncIterator

import fakeredis.aioredis
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import delete

from app.db.session import AsyncSessionLocal
from app.deps.rate_limit import limiter
from app.models.generation_requests import GenerationRequest
from app.models.jobs import Job

from ._helpers import current_user_id, login_via_github


@pytest.fixture(autouse=True)
async def reset_generation_tables() -> AsyncIterator[None]:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Job))
        await session.execute(delete(GenerationRequest))
        await session.commit()
    yield


@pytest.fixture(autouse=True)
async def reset_rate_limiter() -> AsyncIterator[None]:
    """テスト前後で slowapi カウンタを 0 に戻す（テスト独立性）。"""
    limiter.reset()
    yield
    limiter.reset()


async def _insert_failed_gr(*, user_id: uuid.UUID) -> uuid.UUID:
    """retry が叩ける failed リクエストを 1 行入れて id を返す。"""
    async with AsyncSessionLocal() as s:
        gr = GenerationRequest(
            user_id=user_id, category="array", difficulty="easy",
        )
        s.add(gr)
        await s.flush()
        gr.status = "failed"
        gr.failure_reason = "max_attempts_exceeded"
        await s.commit()
        return gr.id


class TestMeGenerationsRetryRateLimit:
    @respx.mock
    async def test_正常系_1分以内に5回までは202を返す(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """閾値 5/minute の下限：5 回までは 202 が返る。"""
        del fake_redis
        csrf = await login_via_github(client, gh_id=9101)
        user_id = await current_user_id(client)

        for i in range(5):
            gr_id = await _insert_failed_gr(user_id=user_id)
            res = await client.post(
                f"/api/me/generations/{gr_id}/retry",
                headers={"X-CSRF-Token": csrf},
            )
            assert res.status_code == 202, f"{i + 1} 回目で {res.status_code}: {res.text}"

    @respx.mock
    async def test_異常系_6回目は429を返し_日本語_detail_が付く(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """閾値 5/minute の上限：6 回目で 429 + 日本語 detail。"""
        del fake_redis
        csrf = await login_via_github(client, gh_id=9102)
        user_id = await current_user_id(client)

        # 失敗行を 6 つ用意（各 retry が違う request_id を叩いてもバケットが
        # 共有されることを検証する＝shared_limit + scope 固定で抜け穴を塞ぐ）。
        for _ in range(5):
            gr_id = await _insert_failed_gr(user_id=user_id)
            res = await client.post(
                f"/api/me/generations/{gr_id}/retry",
                headers={"X-CSRF-Token": csrf},
            )
            assert res.status_code == 202

        # 6 回目で 429 を観測
        gr_id = await _insert_failed_gr(user_id=user_id)
        res = await client.post(
            f"/api/me/generations/{gr_id}/retry",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 429
        body = res.json()
        assert "detail" in body
        # rate_limit_exceeded_handler の日本語 detail（deps/rate_limit.py）
        assert "リクエスト" in body["detail"]
