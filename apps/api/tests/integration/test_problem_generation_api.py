# /api/problems/generate 系ルーター（POST / GET）の結合テスト。
#
# テスト方針：
#   - 実 FastAPI アプリ（main.app）+ 実 Postgres + fakeredis + respx の組み合わせ
#   - ログイン経路は GitHub OAuth スタブ（auth_api テストと同じ）で実セッションを作る。
#     これで CSRF middleware（POST 必須）と get_current_user の両方を本物の経路で通す
#   - POST：generation_requests / jobs に行が増えること、レスポンス JSON 形を観察
#   - GET ：status 別の JSON 形（pending / completed / failed）+ 他人 / 存在しない ID の 404
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md §API / §JSON 例 / §バリデーション
#   - docs/requirements/3-cross-cutting/02-api-conventions.md（CSRF）

import uuid
from collections.abc import AsyncIterator

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
    """各テスト前に generation_requests / jobs / problems を空にする。

    integration/conftest.py の reset_auth_tables も別途 users を消すが、
    generation_requests / jobs / problems は users.id を `ON DELETE CASCADE` で
    FK 参照しているため、conftest 側だけでもデータは連動削除される
    （fixture 実行順への依存は無い）。それでも本 fixture を残すのは：
      - users と切り離されたゴミ（FK を指していない jobs 行など）も併せて掃除する
      - 「このテストモジュールはこのテーブル群を使う」という宣言を兼ねる
    """
    async with AsyncSessionLocal() as session:
        await session.execute(delete(GenerationRequest))
        await session.execute(delete(Job))
        await session.execute(delete(Problem))
        await session.commit()
    yield


# ----------------------------------------------------------------------------
# POST /api/problems/generate
# ----------------------------------------------------------------------------
class TestPostGenerateUnauthenticated:
    async def test_異常系_未認証なら401_CSRF_middlewareが先に弾く(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """CSRF middleware は POST に対して認証情報なしを 401 にする（routers より前段）。"""
        del fake_redis  # fixture 起動だけ
        res = await client.post(
            "/api/problems/generate",
            json={"category": "array", "difficulty": "easy"},
        )
        assert res.status_code == 401


class TestPostGenerateSuccess:
    @respx.mock
    async def test_正常系_202で_requestId_と_status_pending_が返る(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        csrf = await login_via_github(client)

        res = await client.post(
            "/api/problems/generate",
            json={"category": "array", "difficulty": "easy"},
            headers={"X-CSRF-Token": csrf},
        )

        assert res.status_code == 202
        body = res.json()
        assert "requestId" in body
        # UUID として読める。
        uuid.UUID(body["requestId"])
        assert body["status"] == "pending"

    @respx.mock
    async def test_正常系_DBにgeneration_requestsとjobsが1件ずつINSERTされる(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        csrf = await login_via_github(client)
        user_id = await current_user_id(client)

        res = await client.post(
            "/api/problems/generate",
            json={"category": "string", "difficulty": "medium"},
            headers={"X-CSRF-Token": csrf},
        )
        request_id = uuid.UUID(res.json()["requestId"])

        async with AsyncSessionLocal() as s:
            grs = (await s.execute(select(GenerationRequest))).scalars().all()
            jobs = (await s.execute(select(Job))).scalars().all()

        # 本テストが pin したい契約は「POST /api/problems/generate が
        # generation_requests と jobs に 1 行ずつ INSERT し、FK / payload を
        # 正しく詰める」こと（Backend の API 責務）。INSERT 後の状態遷移は
        # Worker が握っており本契約のスコープ外。
        #
        # よって status / state は「初期値そのもの」ではなく「初期値から
        # 始まる有効遷移のいずれか」を許容する形で assert する。dev:all で
        # Worker を同時起動した状態でも race にならない。
        allowed_gr_statuses = {"pending", "running", "succeeded", "failed"}
        allowed_job_states = {"queued", "running", "done", "failed", "dead"}

        # generation_requests に 1 行作られ、FK / 入力値が正しく詰まる。
        assert len(grs) == 1
        assert grs[0].id == request_id
        assert grs[0].user_id == user_id
        assert grs[0].category == "string"
        assert grs[0].difficulty == "medium"
        assert grs[0].status in allowed_gr_statuses
        # produced_problem_id は succeeded で初めて入るため、それ以外は None。
        if grs[0].status != "succeeded":
            assert grs[0].produced_problem_id is None

        # jobs にも 1 行作られ、queue / type / payload の主要キーが詰まっている。
        assert len(jobs) == 1
        assert jobs[0].queue == "generation"
        assert jobs[0].type == "problem.generate"
        assert jobs[0].state in allowed_job_states
        payload = jobs[0].payload
        assert payload["generationRequestId"] == str(request_id)
        assert payload["userId"] == str(user_id)
        assert payload["category"] == "string"
        assert payload["difficulty"] == "medium"
        # ADR 0010：R1 期間は traceparent=None で送る。
        assert payload["traceContext"]["traceparent"] is None


class TestPostGenerateTransactionRollback:
    """generation_requests INSERT + jobs INSERT + NOTIFY を 1 つの tx で
    包む契約（ADR 0044 / 0004）の動作 pin。

    Service の `async with session.begin():` ブロック内で例外が起きたら、
    先に走った generation_requests INSERT も巻き戻ること（部分書き込みが
    残らないこと）を実 DB で観測する。
    """

    @respx.mock
    async def test_異常系_jobs_enqueueが落ちたらgeneration_requestsも巻き戻る(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        del fake_redis
        csrf = await login_via_github(client)

        # JobRepository.enqueue を「INSERT を済ませる前に例外を投げる」関数に
        # 差し替える。begin() ブロック内で raise されると SQLAlchemy 側の
        # context manager が rollback を発火するはずで、その結果先に走った
        # generation_requests.create も巻き戻る、という挙動を観測する。
        from app.repositories.jobs import JobRepository

        async def _boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("simulated enqueue failure")

        monkeypatch.setattr(JobRepository, "enqueue", _boom)

        # ASGITransport は既定で「アプリ未捕捉の例外を呼び出し元へ再 raise」する
        # ため、httpx 側で例外が観測される。本テストは「rollback が起きたか」を
        # 観たいので、例外発生自体は想定内として受け止め、続けて DB 状態を assert。
        with pytest.raises(RuntimeError, match="simulated enqueue failure"):
            await client.post(
                "/api/problems/generate",
                json={"category": "array", "difficulty": "easy"},
                headers={"X-CSRF-Token": csrf},
            )

        # 同一 tx 契約：jobs enqueue 失敗時は generation_requests も 0 件のまま
        # （Service の `async with session.begin():` 経由で rollback が走る）。
        async with AsyncSessionLocal() as s:
            grs = (await s.execute(select(GenerationRequest))).scalars().all()
            jobs = (await s.execute(select(Job))).scalars().all()
        assert len(grs) == 0
        assert len(jobs) == 0


class TestPostGenerateValidation:
    @respx.mock
    async def test_異常系_未知のcategoryは422(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        csrf = await login_via_github(client)

        res = await client.post(
            "/api/problems/generate",
            json={"category": "physics", "difficulty": "easy"},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 422

    @respx.mock
    async def test_異常系_未知のdifficultyは422(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        csrf = await login_via_github(client)

        res = await client.post(
            "/api/problems/generate",
            json={"category": "array", "difficulty": "impossible"},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 422

    @respx.mock
    async def test_異常系_必須フィールド欠落は422(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        csrf = await login_via_github(client)

        # difficulty 欠落。
        res = await client.post(
            "/api/problems/generate",
            json={"category": "array"},
            headers={"X-CSRF-Token": csrf},
        )
        assert res.status_code == 422

    @respx.mock
    async def test_異常系_CSRFヘッダー欠落は403(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """ログイン済みでも X-CSRF-Token ヘッダーが無いと middleware が 403 を返す。"""
        del fake_redis
        await login_via_github(client)

        res = await client.post(
            "/api/problems/generate",
            json={"category": "array", "difficulty": "easy"},
        )
        assert res.status_code == 403


# ----------------------------------------------------------------------------
# GET /api/problems/generate/:request_id
# ----------------------------------------------------------------------------
class TestGetStatusUnauthenticated:
    async def test_異常系_未認証なら401(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        res = await client.get(f"/api/problems/generate/{uuid.uuid4()}")
        assert res.status_code == 401


class TestGetStatusReturnsCorrectShape:
    @respx.mock
    async def test_正常系_pending中はrequest_idとstatusのみ_problemIdは出ない(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """JSON 例: { "requestId": "<uuid>", "status": "pending" }（problemId キーは含めない）。"""
        del fake_redis
        csrf = await login_via_github(client)

        post_res = await client.post(
            "/api/problems/generate",
            json={"category": "array", "difficulty": "easy"},
            headers={"X-CSRF-Token": csrf},
        )
        request_id = post_res.json()["requestId"]

        res = await client.get(f"/api/problems/generate/{request_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["requestId"] == request_id
        assert body["status"] == "pending"
        # serialize_by_alias=True + None 値は exclude されないため problemId キー自体は存在し
        # 値が null で返る。Frontend は null を未完了扱いする契約（problem-generation.md）。
        assert body.get("problemId") is None

    @respx.mock
    async def test_正常系_completedになるとproblemIdが入って返る(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """Worker 完了相当の DB 状態を直接作って観察する。

        status=completed + produced_problem_id 設定 → problemId が返る契約。
        """
        del fake_redis
        csrf = await login_via_github(client)

        post_res = await client.post(
            "/api/problems/generate",
            json={"category": "recursion", "difficulty": "medium"},
            headers={"X-CSRF-Token": csrf},
        )
        request_id = uuid.UUID(post_res.json()["requestId"])

        # Worker の完了処理を模して、status / produced_problem_id を直接書き換える。
        problem_id = await _insert_problem()
        async with AsyncSessionLocal() as s:
            gr = (
                await s.execute(
                    select(GenerationRequest).where(GenerationRequest.id == request_id)
                )
            ).scalar_one()
            gr.status = "completed"
            gr.produced_problem_id = problem_id
            await s.commit()

        res = await client.get(f"/api/problems/generate/{request_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "completed"
        assert body["problemId"] == str(problem_id)

    @respx.mock
    async def test_正常系_failedはproblemIdがnull(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        csrf = await login_via_github(client)

        post_res = await client.post(
            "/api/problems/generate",
            json={"category": "async", "difficulty": "hard"},
            headers={"X-CSRF-Token": csrf},
        )
        request_id = uuid.UUID(post_res.json()["requestId"])

        async with AsyncSessionLocal() as s:
            gr = (
                await s.execute(
                    select(GenerationRequest).where(GenerationRequest.id == request_id)
                )
            ).scalar_one()
            gr.status = "failed"
            await s.commit()

        res = await client.get(f"/api/problems/generate/{request_id}")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "failed"
        assert body.get("problemId") is None


class TestGetStatusAuthorization:
    @respx.mock
    async def test_異常系_存在しないrequest_idは404(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        await login_via_github(client)

        res = await client.get(f"/api/problems/generate/{uuid.uuid4()}")
        assert res.status_code == 404
        # 統一メッセージ（情報漏洩防止、core/exceptions.py）。
        assert res.json() == {"detail": "指定された生成リクエストが見つかりません"}

    @respx.mock
    async def test_異常系_他人のrequest_idも404_存在しないIDと区別しない(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """情報漏洩防止：他人のものか存在しないかは判別できないように同じ 404 に揃える。"""
        del fake_redis

        # ユーザー A でログインしてリクエストを作る。
        csrf_a = await login_via_github(client, gh_id=100)
        post_res = await client.post(
            "/api/problems/generate",
            json={"category": "string", "difficulty": "easy"},
            headers={"X-CSRF-Token": csrf_a},
        )
        owner_request_id = post_res.json()["requestId"]

        # 一度ログアウト相当：cookie をクリアして別ユーザー B でログインし直す。
        # 既存テスト同様、respx を reset してから再ログインする。
        client.cookies.clear()
        respx.reset()
        await login_via_github(client, gh_id=200)

        res = await client.get(f"/api/problems/generate/{owner_request_id}")
        assert res.status_code == 404
        assert res.json() == {"detail": "指定された生成リクエストが見つかりません"}

    @respx.mock
    async def test_異常系_UUIDで無い形式のrequest_idは422(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """Path(UUID) のパースで FastAPI が 422 を返す（認証通過後の Path 検証）。"""
        del fake_redis
        await login_via_github(client)

        res = await client.get("/api/problems/generate/not-a-uuid")
        assert res.status_code == 422


# ----------------------------------------------------------------------------
# 補助：problems テーブルに最小行を 1 件作って id を返す
# ----------------------------------------------------------------------------
async def _insert_problem() -> uuid.UUID:
    """produced_problem_id の FK 制約を満たすため problems に 1 件 INSERT して id を返す。"""
    p = Problem(
        title="dummy",
        description="dummy",
        category="array",
        difficulty="easy",
        language="typescript",
        examples=[],
        test_cases=[],
        reference_solution="",
        judge_scores={},
    )
    async with AsyncSessionLocal() as s:
        s.add(p)
        await s.flush()
        new_id = p.id
        await s.commit()
    return new_id
