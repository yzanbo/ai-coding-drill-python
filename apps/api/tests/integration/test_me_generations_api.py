# /api/me/generations 系ルーター（GET / cancel / retry）の結合テスト。
#
# テスト方針：
#   - 実 FastAPI + 実 Postgres + fakeredis + GitHub OAuth スタブで実セッションを作る
#   - GET   : 自分のみ表示、prompt_version JOIN、retry_count、ページネーション
#   - cancel: pending → 200 + canceled、他人 / 不存在 → 404、pending 以外 → 409
#   - retry : failed → 202 + 新規 generation_request + retry_of リンク、他状態 → 409
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md §履歴・状態管理 / §API

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import fakeredis.aioredis
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.generation_requests import GenerationRequest
from app.models.jobs import Job
from app.models.problems import Problem

from ._helpers import current_user_id, login_via_github


@pytest.fixture(autouse=True)
async def reset_generation_tables() -> AsyncIterator[None]:
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Job))
        await session.execute(delete(GenerationRequest))
        await session.execute(delete(Problem))
        await session.commit()
    yield


async def _insert_gr(
    *,
    user_id: uuid.UUID,
    status: str = "pending",
    category: str = "array",
    difficulty: str = "easy",
    retry_of: uuid.UUID | None = None,
    failure_reason: str | None = None,
    completed: bool = False,
) -> uuid.UUID:
    async with AsyncSessionLocal() as s:
        gr = GenerationRequest(
            user_id=user_id, category=category, difficulty=difficulty, retry_of=retry_of,
        )
        s.add(gr)
        await s.flush()
        gr.status = status
        if failure_reason is not None:
            gr.failure_reason = failure_reason
        if completed:
            gr.completed_at = datetime.now(UTC)
        await s.commit()
        return gr.id


async def _insert_job(
    *,
    generation_request_id: uuid.UUID,
    prompt_version: str = "v1",
    state: str = "queued",
) -> None:
    async with AsyncSessionLocal() as s:
        s.add(
            Job(
                queue="generation",
                type="problem.generate",
                payload={
                    "generationRequestId": str(generation_request_id),
                    "promptVersion": prompt_version,
                },
                state=state,
            )
        )
        await s.commit()


# ----------------------------------------------------------------------------
# GET /api/me/generations
# ----------------------------------------------------------------------------
class TestGetGenerationsHistory:
    async def test_異常系_未認証なら401(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del fake_redis
        res = await client.get("/api/me/generations")
        assert res.status_code == 401

    @respx.mock
    async def test_正常系_履歴ゼロは200_空items_totalPages0(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del fake_redis
        await login_via_github(client)
        res = await client.get("/api/me/generations")
        assert res.status_code == 200
        body = res.json()
        assert body["items"] == []
        assert body["totalPages"] == 0

    @respx.mock
    async def test_正常系_自分の履歴のみ表示_prompt_version_もJOINで取得(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del fake_redis
        await login_via_github(client)
        user_id = await current_user_id(client)

        gr = await _insert_gr(user_id=user_id, status="completed", completed=True)
        await _insert_job(generation_request_id=gr, prompt_version="v3")

        res = await client.get("/api/me/generations")
        assert res.status_code == 200
        body = res.json()
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["id"] == str(gr)
        assert item["status"] == "completed"
        assert item["promptVersion"] == "v3"
        assert item["retryCount"] == 0
        assert item["completedAt"] is not None

    @respx.mock
    async def test_正常系_他人の履歴は混ざらない(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del fake_redis
        # A としてログイン → A の履歴を作る
        await login_via_github(client, gh_id=1)
        a_id = await current_user_id(client)
        await _insert_gr(user_id=a_id)

        # B に切り替えて履歴を 2 件作る
        await login_via_github(client, gh_id=2)
        b_id = await current_user_id(client)
        await _insert_gr(user_id=b_id)
        await _insert_gr(user_id=b_id)

        res = await client.get("/api/me/generations")
        assert res.status_code == 200
        # B 視点では 2 件のみ
        assert len(res.json()["items"]) == 2

    @respx.mock
    async def test_正常系_retry_チェーンの深さが_retryCount_に反映される(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del fake_redis
        await login_via_github(client)
        user_id = await current_user_id(client)
        original = await _insert_gr(user_id=user_id, status="failed")
        retry1 = await _insert_gr(user_id=user_id, retry_of=original)
        await _insert_gr(user_id=user_id, retry_of=retry1)

        res = await client.get("/api/me/generations")
        items = res.json()["items"]
        # created_at DESC で並ぶ → 一番後に作った retry2 が先頭
        counts = {it["id"]: it["retryCount"] for it in items}
        assert counts[str(original)] == 0
        assert counts[str(retry1)] == 1


# ----------------------------------------------------------------------------
# POST /api/me/generations/:id/cancel
# ----------------------------------------------------------------------------
class TestCancelGeneration:
    @respx.mock
    async def test_正常系_pending_を_canceled_に倒す(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del fake_redis
        csrf = await login_via_github(client)
        user_id = await current_user_id(client)
        gr = await _insert_gr(user_id=user_id, status="pending")
        await _insert_job(generation_request_id=gr, state="queued")

        res = await client.post(
            f"/api/me/generations/{gr}/cancel",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 200
        assert res.json() == {"id": str(gr), "status": "canceled"}

        # jobs も dead に倒れている
        async with AsyncSessionLocal() as s:
            jobs = (await s.execute(select(Job))).scalars().all()
        assert all(j.state == "dead" for j in jobs)

    @respx.mock
    async def test_異常系_pending以外は409(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del fake_redis
        csrf = await login_via_github(client)
        user_id = await current_user_id(client)
        gr = await _insert_gr(user_id=user_id, status="completed", completed=True)

        res = await client.post(
            f"/api/me/generations/{gr}/cancel",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 409
        assert "completed" in res.json()["detail"]

    @respx.mock
    async def test_異常系_他人のリクエストは404(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del fake_redis
        # A の generation を作る
        await login_via_github(client, gh_id=1)
        a_id = await current_user_id(client)
        gr_of_a = await _insert_gr(user_id=a_id, status="pending")

        # B でログイン後 A の id を cancel しようとする
        csrf = await login_via_github(client, gh_id=2)
        res = await client.post(
            f"/api/me/generations/{gr_of_a}/cancel",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 404


# ----------------------------------------------------------------------------
# POST /api/me/generations/:id/retry
# ----------------------------------------------------------------------------
class TestRetryGeneration:
    @respx.mock
    async def test_正常系_failed_を_新規generation_request_として複製(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del fake_redis
        csrf = await login_via_github(client)
        user_id = await current_user_id(client)
        original = await _insert_gr(
            user_id=user_id, status="failed", category="recursion", difficulty="hard",
            failure_reason="judge_below_threshold",
        )

        res = await client.post(
            f"/api/me/generations/{original}/retry",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 202
        body = res.json()
        new_id = uuid.UUID(body["id"])
        assert new_id != original
        assert body["status"] == "pending"
        assert body["retryOf"] == str(original)

        # DB 上の新規行が retry_of を指し、同じ category/difficulty を継承する
        async with AsyncSessionLocal() as s:
            new_gr = await s.get(GenerationRequest, new_id)
        assert new_gr is not None
        assert new_gr.retry_of == original
        assert new_gr.category == "recursion"
        assert new_gr.difficulty == "hard"
        assert new_gr.status == "pending"

    @respx.mock
    async def test_異常系_failed以外は409(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del fake_redis
        csrf = await login_via_github(client)
        user_id = await current_user_id(client)
        gr = await _insert_gr(user_id=user_id, status="pending")
        res = await client.post(
            f"/api/me/generations/{gr}/retry",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 409
        assert "pending" in res.json()["detail"]

    @respx.mock
    async def test_異常系_他人のリクエストは404(
        self, client: AsyncClient, fake_redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del fake_redis
        await login_via_github(client, gh_id=1)
        a_id = await current_user_id(client)
        gr_of_a = await _insert_gr(user_id=a_id, status="failed")

        csrf = await login_via_github(client, gh_id=2)
        res = await client.post(
            f"/api/me/generations/{gr_of_a}/retry",
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 404
