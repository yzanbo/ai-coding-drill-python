# POST /api/submissions のレート制限の結合テスト。
#
# 要件:
#   - docs/requirements/4-features/grading.md §API #post-submissions
#   - docs/requirements/3-cross-cutting/02-api-conventions.md §レート制限
#     「1 ユーザー / 1 分 / 20 回」を超えると 429 を返す。
#
# テスト方針:
#   - tests/conftest.py の先頭で RATE_LIMIT_STORAGE_URI=memory:// を仕込んであるため、
#     Limiter は実 Redis 不要のメモリ保存で動く。
#   - 認証は _helpers.login_via_github（@respx.mock で GitHub OAuth をスタブ）を使い、
#     test_submissions_api.py と同じ認証経路を踏む。
#   - Service / Repository / INSERT の振る舞いは test_submissions_api.py 側で網羅されている
#     前提で、本テストでは「rate limit デコレータ + 429 ハンドラ」の HTTP 層挙動だけに集中する。
#   - 各テストの前後で limiter.reset() を呼んでカウンタを 0 に戻す（テスト独立性）。
#   - key 関数は deps/rate_limit.py の get_rate_limit_key（認証時は user:<id>）。
#     test_problems_rate_limit.py 側でユーザー単位カウンタ分離は検証済みのため、
#     本ファイルでは閾値 + 429 ハンドラ整合のみを担保する。

from collections.abc import AsyncIterator

import fakeredis.aioredis
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import delete

from app.db.session import AsyncSessionLocal
from app.deps.rate_limit import limiter
from app.models.problems import Problem
from app.models.submissions import Submission

from ._factories import create_problem
from ._helpers import login_via_github


@pytest.fixture(autouse=True)
async def reset_submissions_tables() -> AsyncIterator[None]:
    """各テスト前に submissions / problems を空にする（テスト独立性）。"""
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Submission))
        await session.execute(delete(Problem))
        await session.commit()
    yield


@pytest.fixture(autouse=True)
async def reset_rate_limiter() -> AsyncIterator[None]:
    """テスト前後で slowapi のカウンタを 0 に戻す。"""
    limiter.reset()
    yield
    limiter.reset()


class TestSubmissionsRateLimit:
    @respx.mock
    async def test_正常系_1分以内に20回までは202を返す(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """閾値 20/minute の下限：20 回までは 202 が返る。"""
        del fake_redis
        async with AsyncSessionLocal() as session:
            problem_id = await create_problem(session)
        csrf = await login_via_github(client, gh_id=3001)

        for i in range(20):
            res = await client.post(
                "/api/submissions",
                json={"problemId": str(problem_id), "code": "const solve = (n: number) => n;"},
                headers={"X-CSRF-Token": csrf},
            )
            assert res.status_code == 202, f"{i + 1} 回目で {res.status_code}: {res.text}"

    @respx.mock
    async def test_異常系_21回目は429を返し_日本語_detail_が付く(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """閾値 20/minute の上限：21 回目で 429 + 日本語 detail。"""
        del fake_redis
        async with AsyncSessionLocal() as session:
            problem_id = await create_problem(session)
        csrf = await login_via_github(client, gh_id=3002)

        # 20 回までは流す。
        for _ in range(20):
            res = await client.post(
                "/api/submissions",
                json={"problemId": str(problem_id), "code": "const solve = (n: number) => n;"},
                headers={"X-CSRF-Token": csrf},
            )
            assert res.status_code == 202

        # 21 回目で 429 を観測。
        res = await client.post(
            "/api/submissions",
            json={"problemId": str(problem_id), "code": "const solve = (n: number) => n;"},
            headers={"X-CSRF-Token": csrf},
        )

        assert res.status_code == 429
        payload = res.json()
        # 日本語 detail（deps/rate_limit.py の rate_limit_exceeded_handler）。
        assert (
            payload["detail"]
            == "リクエストが多すぎます。しばらく時間を置いてから再度お試しください。"
        )
