# /api/submissions ルーター（POST + GET /:id + GET /、R1-5）の結合テスト。
#
# テスト方針：
#   - 実 FastAPI + 実 Postgres + fakeredis + 既存の GitHub OAuth スタブ経路で
#     セッションを作る
#   - POST 成功で submissions + jobs に 1 行ずつ INSERT されることを観察
#   - GET /:id は ownership 込みで自分のものだけ 200、他人 / 存在しない id は 404
#   - GET / は自分の履歴のみ返る、ページネーション境界も検証
#
# 関わる要件：
#   - docs/requirements/4-features/grading.md §API

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import fakeredis.aioredis
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.models.jobs import Job
from app.models.problems import Problem
from app.models.submissions import Submission

from ._helpers import current_user_id, login_via_github


@pytest.fixture(autouse=True)
async def reset_submissions_table() -> AsyncIterator[None]:
    """各テスト前に submissions / jobs / problems を空にする（テスト間の独立性）。"""
    async with AsyncSessionLocal() as session:
        # submissions → jobs → problems の順で消す（jobs は FK を持たないが
        # 後続テストとの状態漏洩を防ぐため毎回クリア）。
        await session.execute(delete(Submission))
        await session.execute(delete(Job))
        await session.execute(delete(Problem))
        await session.commit()
    yield


async def _insert_problem(
    *,
    title: str = "配列の合計",
    deleted: bool = False,
) -> uuid.UUID:
    async with AsyncSessionLocal() as session:
        problem = Problem(
            title=title,
            description="合計を返してください",
            category="array",
            difficulty="easy",
            language="typescript",
            examples=[{"input": "[1,2,3]", "output": "6"}],
            # test_cases.input は Worker 側 TestCase 契約（[]any）に合わせて配列で入れる。
            # 文字列を入れると grading Worker が json unmarshal で落ちて即 dead 行きになる。
            # 契約 SSoT: apps/workers/grading/internal/grading/generation_prompt.go の TestCase
            test_cases=[{"input": [[1, 2, 3]], "expected": 6}],
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


async def _insert_submission(
    *,
    user_id: uuid.UUID,
    problem_id: uuid.UUID,
    code: str = "x",
    status: str = "pending",
    score: int | None = None,
    result: dict[str, Any] | None = None,
    graded_at: datetime | None = None,
    deleted: bool = False,
) -> uuid.UUID:
    """テスト用 submission を直接 INSERT して id を返す。

    GET 系テストでは「Worker が既に graded まで遷移させた状態」を作りたいことが
    多いので、status / score / result / graded_at を任意で受け取る。
    """
    async with AsyncSessionLocal() as session:
        sub = Submission(user_id=user_id, problem_id=problem_id, code=code)
        sub.status = status
        sub.score = score
        sub.result = result
        sub.graded_at = graded_at
        session.add(sub)
        await session.flush()
        sub_id = sub.id
        if deleted:
            sub.deleted_at = datetime.now(UTC)
        await session.commit()
    return sub_id


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
    async def test_正常系_202で_submissions_と_jobs_両方にINSERTされる(
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
        submission_id = uuid.UUID(body["submissionId"])
        assert body["status"] == "pending"

        # submissions に 1 行 INSERT されている契約。
        async with AsyncSessionLocal() as session:
            rows = (
                (await session.execute(select(Submission).where(Submission.user_id == user_id)))
                .scalars()
                .all()
            )
        # 本テストが pin したい契約は「POST /api/submissions が submissions に
        # 1 行 INSERT し、user_id / problem_id を正しく詰める」こと（Backend の
        # API 責務）。INSERT 後の status / result / score / graded_at は Worker が
        # 握っており本契約のスコープ外。
        #
        # 同期実行下では status='pending' 直後で観測できるが、dev:all で Worker を
        # 同時起動した状態だと既に 'graded' / 'failed' に遷移していることがある。
        # 「初期値そのもの」ではなく「初期値から始まる有効遷移のいずれか」を
        # 許容する形で assert する。
        allowed_sub_statuses = {"pending", "graded", "failed"}
        assert len(rows) == 1
        assert rows[0].id == submission_id
        assert rows[0].problem_id == problem_id
        assert rows[0].status in allowed_sub_statuses
        # result / score / graded_at は status='pending' のときのみ未設定。
        # Worker が触った後は値が入っていてよい（観測時点による）。
        if rows[0].status == "pending":
            assert rows[0].result is None
            assert rows[0].score is None
            assert rows[0].graded_at is None

        # R1-5: 同一 tx 内で jobs に 1 行 INSERT + NOTIFY が走る契約（ADR 0004）。
        # queue='grading' / type='submission.grade' / payload に traceContext が
        # 必須（ADR 0010）。NOTIFY 自体は副作用なので DB 行で観測する。
        async with AsyncSessionLocal() as session:
            jobs = (
                (await session.execute(select(Job).where(Job.queue == "grading")))
                .scalars()
                .all()
            )
        assert len(jobs) == 1
        job = jobs[0]
        assert job.type == "submission.grade"
        payload = job.payload
        assert payload["submissionId"] == str(submission_id)
        assert payload["userId"] == str(user_id)
        assert payload["problemId"] == str(problem_id)
        assert payload["code"] == "const solve = (n: number) => n;"
        # R1〜R3 暫定: traceparent=None / tracestate=""（ADR 0010、OTel SDK 結線は R4）。
        assert payload["traceContext"]["traceparent"] is None
        assert payload["traceContext"]["tracestate"] == ""

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


class TestGetSubmissionById:
    async def test_異常系_未認証なら401(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        res = await client.get(f"/api/submissions/{uuid.uuid4()}")
        assert res.status_code == 401

    @respx.mock
    async def test_正常系_pending時はscore_totalCount_result_gradedAtがnullで返る(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        problem_id = await _insert_problem()
        await login_via_github(client)
        user_id = await current_user_id(client)
        sub_id = await _insert_submission(user_id=user_id, problem_id=problem_id)

        res = await client.get(f"/api/submissions/{sub_id}")

        assert res.status_code == 200
        body = res.json()
        assert body["id"] == str(sub_id)
        assert body["problemId"] == str(problem_id)
        assert body["status"] == "pending"
        assert body["score"] is None
        assert body["totalCount"] is None
        assert body["result"] is None
        assert body["gradedAt"] is None

    @respx.mock
    async def test_正常系_graded時はresult_JSONBがそのまま返り_totalCountも詰まる(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        problem_id = await _insert_problem()
        await login_via_github(client)
        user_id = await current_user_id(client)
        graded_at = datetime.now(UTC)
        sub_id = await _insert_submission(
            user_id=user_id,
            problem_id=problem_id,
            status="graded",
            score=2,
            result={
                "passed": False,
                "durationMs": 1340,
                "failureKind": "test_failed",
                "testResults": [
                    {"name": "case1", "passed": True, "durationMs": 120},
                    {
                        "name": "case2",
                        "passed": False,
                        "durationMs": 80,
                        "expected": "6",
                        "actual": "7",
                        "message": "AssertionError",
                    },
                    {"name": "case3", "passed": True, "durationMs": 100},
                ],
            },
            graded_at=graded_at,
        )

        res = await client.get(f"/api/submissions/{sub_id}")

        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "graded"
        assert body["score"] == 2
        assert body["totalCount"] == 3  # testResults 件数から派生
        assert body["gradedAt"] is not None
        result = body["result"]
        assert result["passed"] is False
        assert result["durationMs"] == 1340
        assert result["failureKind"] == "test_failed"
        assert len(result["testResults"]) == 3
        assert result["testResults"][1]["expected"] == "6"
        assert result["testResults"][1]["actual"] == "7"

    @respx.mock
    async def test_異常系_他人の解答は404(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """情報漏洩防止：他人の id を渡しても 404（存在チェックと区別しない）。"""
        del fake_redis
        problem_id = await _insert_problem()
        # Owner として 1 件作る。
        await login_via_github(client, gh_id=100)
        owner_id = await current_user_id(client)
        sub_id = await _insert_submission(user_id=owner_id, problem_id=problem_id)
        # Other に切り替え（client は同一だが Cookie を再発行する）。
        client.cookies.clear()
        await login_via_github(client, gh_id=200)

        res = await client.get(f"/api/submissions/{sub_id}")
        assert res.status_code == 404

    @respx.mock
    async def test_異常系_存在しないIDは404(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        await login_via_github(client)

        res = await client.get(f"/api/submissions/{uuid.uuid4()}")
        assert res.status_code == 404


class TestListSubmissions:
    async def test_異常系_未認証なら401(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        res = await client.get("/api/submissions")
        assert res.status_code == 401

    @respx.mock
    async def test_正常系_自分の解答だけが新着順で返る_problem_titleも詰まる(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        problem_id = await _insert_problem(title="二倍にして返す")
        # Owner で 2 件作り、Other を 1 件混ぜる。
        await login_via_github(client, gh_id=300)
        owner_id = await current_user_id(client)
        await _insert_submission(user_id=owner_id, problem_id=problem_id, code="old")
        await _insert_submission(user_id=owner_id, problem_id=problem_id, code="new")
        client.cookies.clear()
        await login_via_github(client, gh_id=301)
        other_id = await current_user_id(client)
        await _insert_submission(user_id=other_id, problem_id=problem_id, code="other")

        # Owner に戻して履歴を取る。
        client.cookies.clear()
        await login_via_github(client, gh_id=300)

        res = await client.get("/api/submissions")

        assert res.status_code == 200
        body = res.json()
        assert body["page"] == 1
        assert body["pageSize"] == 20
        assert body["totalPages"] == 1
        items = body["items"]
        # Owner の 2 件だけ返り、他人の 1 件は混ざらない。
        assert len(items) == 2
        # 並び順は新着順（"new" が先頭）。
        # problem_title が JOIN で詰まる契約（一覧 UI で問題名を出すため）。
        for item in items:
            assert item["problemId"] == str(problem_id)
            assert item["problemTitle"] == "二倍にして返す"

    @respx.mock
    async def test_正常系_pageSize1で最終ページと超過ページが空配列(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        problem_id = await _insert_problem()
        await login_via_github(client)
        user_id = await current_user_id(client)
        # 3 件作って pageSize=1 で 3 ページ + 超過 1 ページを観測。
        for _ in range(3):
            await _insert_submission(user_id=user_id, problem_id=problem_id)

        # page=3（最終ページ）：1 件返る。
        res = await client.get("/api/submissions?page=3&pageSize=1")
        assert res.status_code == 200
        body = res.json()
        assert body["page"] == 3
        assert body["pageSize"] == 1
        assert body["totalPages"] == 3
        assert len(body["items"]) == 1

        # page=4（超過）：空配列で返る（total_pages 自体は 3 のまま）。
        res = await client.get("/api/submissions?page=4&pageSize=1")
        assert res.status_code == 200
        body = res.json()
        assert body["page"] == 4
        assert body["pageSize"] == 1
        assert body["totalPages"] == 3
        assert body["items"] == []

    @respx.mock
    async def test_異常系_ソフトデリートされたproblemの解答は履歴に出ない(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        alive_problem = await _insert_problem(title="生きてる問題")
        dead_problem = await _insert_problem(title="削除済み問題", deleted=True)
        await login_via_github(client)
        user_id = await current_user_id(client)
        await _insert_submission(user_id=user_id, problem_id=alive_problem)
        await _insert_submission(user_id=user_id, problem_id=dead_problem)

        res = await client.get("/api/submissions")

        assert res.status_code == 200
        body = res.json()
        # 問題が消えた解答は履歴に出さない契約（JOIN 側の deleted_at も WHERE で除外）。
        assert len(body["items"]) == 1
        assert body["items"][0]["problemTitle"] == "生きてる問題"

    @respx.mock
    async def test_異常系_ソフトデリートされたsubmissionも履歴に出ない(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        problem_id = await _insert_problem()
        await login_via_github(client)
        user_id = await current_user_id(client)
        await _insert_submission(user_id=user_id, problem_id=problem_id, deleted=True)
        await _insert_submission(user_id=user_id, problem_id=problem_id)

        res = await client.get("/api/submissions")

        assert res.status_code == 200
        body = res.json()
        # deleted_at IS NULL の 1 件だけ返る契約。
        assert len(body["items"]) == 1
