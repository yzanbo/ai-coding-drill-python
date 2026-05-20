# /api/submissions ルーター（POST のみ R1-4）の結合テスト。
#
# テスト方針：
#   - 実 FastAPI + 実 Postgres + fakeredis + 既存の GitHub OAuth スタブ経路で
#     セッションを作る
#   - POST 成功で submissions に 1 行 INSERT されることを観察
#   - 未認証 / 存在しない問題 / バリデーション失敗 等の異常系も確認
#
# 関わる要件：
#   - docs/requirements/4-features/grading.md §API #post-submissions

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import fakeredis.aioredis
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.problems import Problem
from app.models.submissions import Submission

from ._helpers import current_user_id, login_via_github


@pytest.fixture(autouse=True)
async def reset_submissions_table() -> AsyncIterator[None]:
    """各テスト前に submissions / problems を空にする（テスト間の独立性）。"""
    async with AsyncSessionLocal() as session:
        await session.execute(delete(Submission))
        await session.execute(delete(Problem))
        await session.commit()
    yield


async def _insert_problem(*, deleted: bool = False) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        problem = Problem(
            title="配列の合計",
            description="合計を返してください",
            category="array",
            difficulty="easy",
            language="typescript",
            examples=[{"input": "[1,2,3]", "output": "6"}],
            test_cases=[{"input": "[1,2,3]", "expected": "6"}],
            reference_solution="x",
            judge_scores={},
        )
        session.add(problem)
        await session.flush()
        problem_id = problem.id
        if deleted:
            problem.deleted_at = datetime.now(UTC)
        await session.commit()
    return problem_id


class TestPostSubmission:
    async def test_異常系_未認証なら401_CSRF_middlewareが先に弾く(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        res = await client.post(
            "/api/submissions",
            json={"problemId": str(uuid.uuid4()), "code": "x"},
        )
        # POST に対して認証情報なしは CSRF middleware が 401 を返す（routers より前段）。
        assert res.status_code == 401

    @respx.mock
    async def test_正常系_202で_submissionId_と_status_pending_が返り_DBにINSERTされる(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        problem_id = await _insert_problem()
        csrf = await login_via_github(client)
        user_id = await current_user_id(client)

        res = await client.post(
            "/api/submissions",
            json={"problemId": str(problem_id), "code": "const solve = (n: number) => n;"},
            headers={"X-CSRF-Token": csrf},
        )

        assert res.status_code == 202
        body = res.json()
        assert "submissionId" in body
        uuid.UUID(body["submissionId"])
        assert body["status"] == "pending"

        # DB に 1 行 INSERT されている契約。
        async with AsyncSessionLocal() as session:
            rows = (
                (await session.execute(select(Submission).where(Submission.user_id == user_id)))
                .scalars()
                .all()
            )
        assert len(rows) == 1
        assert rows[0].problem_id == problem_id
        assert rows[0].status == "pending"
        # R1-5 で書く列は本フェーズでは未設定。
        assert rows[0].result is None
        assert rows[0].score is None
        assert rows[0].graded_at is None

    @respx.mock
    async def test_異常系_存在しないproblemIdは404でsubmissionsはINSERTされない(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        csrf = await login_via_github(client)
        user_id = await current_user_id(client)

        res = await client.post(
            "/api/submissions",
            json={"problemId": str(uuid.uuid4()), "code": "x"},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 404

        async with AsyncSessionLocal() as session:
            count = (
                await session.execute(select(Submission).where(Submission.user_id == user_id))
            ).all()
        assert count == []

    @respx.mock
    async def test_異常系_ソフトデリート済みのproblemIdも404(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        problem_id = await _insert_problem(deleted=True)
        csrf = await login_via_github(client)

        res = await client.post(
            "/api/submissions",
            json={"problemId": str(problem_id), "code": "x"},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 404

    @respx.mock
    async def test_異常系_空コードは422(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        problem_id = await _insert_problem()
        csrf = await login_via_github(client)

        res = await client.post(
            "/api/submissions",
            json={"problemId": str(problem_id), "code": ""},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 422
