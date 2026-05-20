# POST /api/problems/generate のレート制限の結合テスト。
#
# 要件:
#   - docs/requirements/3-cross-cutting/02-api-conventions.md §レート制限
#     「1 ユーザー / 1 分 / 5 回」を超えると 429 を返す。
#
# テスト方針:
#   - tests/conftest.py の先頭で RATE_LIMIT_STORAGE_URI=memory:// を仕込んであるため、
#     Limiter は実 Redis 不要のメモリ保存で動く。
#   - ログインは _helpers.login_via_github（@respx.mock で GitHub OAuth をスタブ）を使い、
#     既存の test_problem_generation_api.py と同じ認証経路を踏む。
#   - 本テストは実 enqueue を通す（DB / NOTIFY 含む）。Service / Repository / NOTIFY の
#     振る舞いは test_problem_generation_api.py 側で別途網羅されている前提で、
#     ここでは「rate limit デコレータ + 429 ハンドラ」の HTTP 層挙動だけに集中する。
#   - 各テストの前後で limiter.reset() を呼んでカウンタを 0 に戻す（テスト独立性）。

from collections.abc import AsyncIterator

import fakeredis.aioredis
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import delete

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.deps.rate_limit import limiter
from app.models.generation_requests import GenerationRequest
from app.models.jobs import Job
from app.models.problems import Problem

from ._helpers import login_via_github


@pytest.fixture(autouse=True)
async def reset_generation_tables() -> AsyncIterator[None]:
    """各テスト前に generation_requests / jobs / problems を空にする。

    本テストは実 enqueue を通すため両テーブルに行が積まれる。テスト独立性のため
    毎回掃除する（test_problem_generation_api.py と同じパターン）。
    """
    async with AsyncSessionLocal() as session:
        await session.execute(delete(GenerationRequest))
        await session.execute(delete(Job))
        await session.execute(delete(Problem))
        await session.commit()
    yield


@pytest.fixture(autouse=True)
async def reset_rate_limiter() -> AsyncIterator[None]:
    """テスト前後で slowapi のカウンタを 0 に戻す（テスト独立性）。"""
    limiter.reset()
    yield
    limiter.reset()


class TestProblemsGenerateRateLimit:
    @respx.mock
    async def test_正常系_1分以内に5回までは202を返す(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        csrf = await login_via_github(client, gh_id=1001)

        for i in range(5):
            res = await client.post(
                "/api/problems/generate",
                json={"category": "array", "difficulty": "easy"},
                headers={"X-CSRF-Token": csrf},
            )
            assert res.status_code == 202, f"{i + 1} 回目で {res.status_code}: {res.text}"

    @respx.mock
    async def test_異常系_6回目は429を返す(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        csrf = await login_via_github(client, gh_id=1002)

        # 5 回までは流して、6 回目で 429 を観測する。
        for _ in range(5):
            res = await client.post(
                "/api/problems/generate",
                json={"category": "array", "difficulty": "easy"},
                headers={"X-CSRF-Token": csrf},
            )
            assert res.status_code == 202

        res = await client.post(
            "/api/problems/generate",
            json={"category": "array", "difficulty": "easy"},
            headers={"X-CSRF-Token": csrf},
        )

        assert res.status_code == 429
        payload = res.json()
        # 日本語 detail（deps/rate_limit.py の rate_limit_exceeded_handler）。
        assert (
            payload["detail"]
            == "リクエストが多すぎます。しばらく時間を置いてから再度お試しください。"
        )

    @respx.mock
    async def test_正常系_ユーザーが違えばカウンタは独立で5回ずつ通る(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """key 関数が user:<id> 単位で分離されていることを担保する。"""
        del fake_redis
        settings = get_settings()

        # ユーザー A で 5 回流す。
        csrf_a = await login_via_github(client, gh_id=2001)
        for _ in range(5):
            res = await client.post(
                "/api/problems/generate",
                json={"category": "array", "difficulty": "easy"},
                headers={"X-CSRF-Token": csrf_a},
            )
            assert res.status_code == 202

        # ユーザー B で別ログイン（Cookie を上書き）→ 同じく 5 回成功できる。
        # session_id / csrf_token Cookie はログイン時に書き換わるが、
        # login_via_github を呼ぶ前に明示的に消しておく方が
        # 前ユーザーの認証状態を引きずらない（=テストの意図が明示的になる）。
        client.cookies.delete(settings.session_cookie_name)
        client.cookies.delete(settings.csrf_cookie_name)
        csrf_b = await login_via_github(client, gh_id=2002)
        for _ in range(5):
            res = await client.post(
                "/api/problems/generate",
                json={"category": "array", "difficulty": "easy"},
                headers={"X-CSRF-Token": csrf_b},
            )
            assert res.status_code == 202
