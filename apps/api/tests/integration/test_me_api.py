# /api/me ルーター（GET /stats + GET /weakness、R1-6）の結合テスト。
#
# テスト方針：
#   - 実 FastAPI + 実 Postgres + fakeredis + GitHub OAuth スタブでログイン状態を作る
#   - 直接 DB に submissions / problems を INSERT して集計の素材を用意し、
#     エンドポイントを叩いて JSON を観測する
#   - 認証必須 / 履歴ゼロでも 200 / 採点完了行のみ集計 / 弱点しきい値 を網羅
#
# 関わる要件：
#   - docs/requirements/4-features/learning.md §API §受け入れ条件 §ビジネスルール

import uuid
from collections.abc import AsyncIterator
from typing import Any

import fakeredis.aioredis
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import delete

from app.db.session import AsyncSessionLocal
from app.models.problems import Problem
from app.models.submissions import Submission

from ._helpers import current_user_id, login_via_github


@pytest.fixture(autouse=True)
async def reset_me_tables() -> AsyncIterator[None]:
    """各テスト前に submissions / problems を空にする（テスト間の独立性）。"""
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Submission))
        await session.execute(delete(Problem))
        await session.commit()
    yield


async def _insert_problem(*, category: str = "array") -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        problem = Problem(
            title="t",
            description="d",
            category=category,
            difficulty="easy",
            language="typescript",
            examples=[{"input": "", "output": ""}],
            test_cases=[{"input": "", "expected": ""}],
            reference_solution="x",
            judge_scores={},
        )
        session.add(problem)
        await session.flush()
        problem_id = problem.id
        await session.commit()
    return problem_id


async def _insert_submission(
    *,
    user_id: uuid.UUID,
    problem_id: uuid.UUID,
    status: str = "graded",
    passed: bool | None = True,
) -> None:
    """graded 行を直接 INSERT する（Worker 経由を待たないため）。"""
    async with AsyncSessionLocal() as session:
        sub = Submission(user_id=user_id, problem_id=problem_id, code="x")
        sub.status = status
        if passed is None:
            sub.result = None
        else:
            result: dict[str, Any] = {
                "passed": passed,
                "durationMs": 100,
                "testResults": [],
            }
            sub.result = result
        session.add(sub)
        await session.commit()


class TestGetMyStats:
    async def test_異常系_未認証なら401(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        res = await client.get("/api/me/stats")
        # 認証必須エンドポイント（get_current_user 経由）。
        assert res.status_code == 401

    @respx.mock
    async def test_正常系_履歴ゼロは200で空集計を返す(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        await login_via_github(client)

        res = await client.get("/api/me/stats")

        # learning.md §受け入れ条件「履歴ゼロでも 200 / 空集計」。
        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 0
        assert body["correct"] == 0
        assert body["accuracy"] == 0.0
        assert body["byCategory"] == []

    @respx.mock
    async def test_正常系_カテゴリ別集計とaccuracyが返る(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        await login_via_github(client)
        user_id = await current_user_id(client)

        array_problem = await _insert_problem(category="array")
        recursion_problem = await _insert_problem(category="recursion")
        # array: 2 / 2 = 1.0
        await _insert_submission(
            user_id=user_id, problem_id=array_problem, passed=True
        )
        await _insert_submission(
            user_id=user_id, problem_id=array_problem, passed=True
        )
        # recursion: 0 / 1 = 0.0
        await _insert_submission(
            user_id=user_id, problem_id=recursion_problem, passed=False
        )

        res = await client.get("/api/me/stats")

        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 3
        assert body["correct"] == 2
        assert body["accuracy"] == pytest.approx(2 / 3)
        by_cat = {item["category"]: item for item in body["byCategory"]}
        assert by_cat["array"]["attempts"] == 2
        assert by_cat["array"]["correct"] == 2
        assert by_cat["array"]["accuracy"] == 1.0
        assert by_cat["recursion"]["attempts"] == 1
        assert by_cat["recursion"]["accuracy"] == 0.0

    @respx.mock
    async def test_他人の解答は混ざらない(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        # ユーザー A としてログイン → A の submission を 1 件作る。
        await login_via_github(client, gh_id=1)
        user_a = await current_user_id(client)
        problem_id = await _insert_problem(category="array")
        await _insert_submission(
            user_id=user_a, problem_id=problem_id, passed=True
        )
        # ユーザー B の submission を直接 INSERT（B には触らない fake user）。
        b_id = uuid.uuid4()
        # FK 制約上 users に B が居ないと INSERT できないため、別 gh_id でログインして
        # B を作ってから A に戻る、という方が簡潔。
        # ここでは別 gh_id でログインして user_b を取得 → B の submission を作る。
        await login_via_github(client, gh_id=2)
        user_b = await current_user_id(client)
        await _insert_submission(
            user_id=user_b, problem_id=problem_id, passed=False
        )
        await _insert_submission(
            user_id=user_b, problem_id=problem_id, passed=False
        )
        # 観測：ユーザー B の視点で /me/stats を叩くと B の 2 件だけが見える。
        del user_a, b_id

        res = await client.get("/api/me/stats")

        assert res.status_code == 200
        body = res.json()
        assert body["total"] == 2
        assert body["correct"] == 0


class TestGetMyWeakness:
    async def test_異常系_未認証なら401(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        res = await client.get("/api/me/weakness")
        assert res.status_code == 401

    @respx.mock
    async def test_正常系_履歴ゼロはweakCategoriesが空(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        await login_via_github(client)

        res = await client.get("/api/me/weakness")

        assert res.status_code == 200
        assert res.json() == {"weakCategories": []}

    @respx.mock
    async def test_正常系_3問未満のカテゴリは弱点に出ない(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        await login_via_github(client)
        user_id = await current_user_id(client)

        # async: 2 件全敗（accuracy=0 だが attempts=2 < 3 でサンプル不足）。
        async_problem = await _insert_problem(category="async")
        await _insert_submission(
            user_id=user_id, problem_id=async_problem, passed=False
        )
        await _insert_submission(
            user_id=user_id, problem_id=async_problem, passed=False
        )

        res = await client.get("/api/me/weakness")

        assert res.status_code == 200
        # learning.md §ビジネスルール「解答数が一定以上（3 問以上）」。
        assert res.json()["weakCategories"] == []

    @respx.mock
    async def test_正常系_しきい値を満たす弱点カテゴリが返る(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        await login_via_github(client)
        user_id = await current_user_id(client)

        # recursion: 1 / 5 = 0.2（弱点）。
        recursion_problem = await _insert_problem(category="recursion")
        await _insert_submission(
            user_id=user_id, problem_id=recursion_problem, passed=True
        )
        for _ in range(4):
            await _insert_submission(
                user_id=user_id, problem_id=recursion_problem, passed=False
            )
        # array: 8 / 10 = 0.8（弱点ではない）。
        array_problem = await _insert_problem(category="array")
        for _ in range(8):
            await _insert_submission(
                user_id=user_id, problem_id=array_problem, passed=True
            )
        for _ in range(2):
            await _insert_submission(
                user_id=user_id, problem_id=array_problem, passed=False
            )

        res = await client.get("/api/me/weakness")

        assert res.status_code == 200
        weak = res.json()["weakCategories"]
        assert len(weak) == 1
        assert weak[0]["category"] == "recursion"
        assert weak[0]["attempts"] == 5
        assert weak[0]["correct"] == 1
        assert weak[0]["accuracy"] == pytest.approx(0.2)
