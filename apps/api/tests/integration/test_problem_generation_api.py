# /problems/generate 系ルーター（POST / GET）の結合テスト。
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

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models.generation_requests import GenerationRequest
from app.models.jobs import Job
from app.models.problems import Problem

_TOKEN_URL = "https://github.com/login/oauth/access_token"
_USER_API_URL = "https://api.github.com/user"


@pytest.fixture(autouse=True)
async def reset_generation_tables() -> AsyncIterator[None]:
    """各テスト前に generation_requests / jobs / problems を空にする。

    integration/conftest.py の reset_auth_tables（autouse）が users / auth_providers を
    消す前に、これらが FK 参照しているテーブルを先に消しておく必要がある。
    fixture の実行順は alphabetical + autouse 同士は名前順なので、別 fixture として
    切ってこちらが先に動くよう reset_auth_tables より前に来る名前にしてある。
    """
    async with AsyncSessionLocal() as session:
        await session.execute(delete(GenerationRequest))
        await session.execute(delete(Job))
        await session.execute(delete(Problem))
        await session.commit()
    yield


def _stub_github_success(
    *,
    gh_id: int = 12345,
    name: str | None = "Taro",
    login: str = "taro",
    email: str | None = "taro@example.com",
) -> None:
    """GitHub の OAuth フロー（token 交換 + user 取得）を成功レスポンスでモックする。"""
    respx.post(_TOKEN_URL).respond(
        200, json={"access_token": "gho_dummy", "token_type": "bearer"}
    )
    respx.get(_USER_API_URL).respond(
        200, json={"id": gh_id, "name": name, "login": login, "email": email}
    )


async def _login(client: AsyncClient, *, gh_id: int = 1) -> str:
    """GitHub OAuth スタブでログインして、CSRF ヘッダー値を返す。

    副作用：
      - client.cookies に session_id / csrf_token Cookie がセットされる
      - DB に users + auth_providers が 1 件ずつ作られる
      - Redis（fakeredis）にセッションハッシュが作られる
    返り値の csrf_token は POST 系の X-CSRF-Token ヘッダーにそのまま使う。
    """
    _stub_github_success(gh_id=gh_id, name=f"u{gh_id}", login=f"u{gh_id}", email=None)

    start = await client.get("/auth/github")
    state_token = start.headers["location"].split("state=")[1].split("&")[0]
    cb = await client.get(f"/auth/github/callback?code=ok&state={state_token}")

    settings = get_settings()
    signed = _extract_cookie_value(cb, settings.session_cookie_name)
    csrf = _extract_cookie_value(cb, settings.csrf_cookie_name)
    client.cookies.set(settings.session_cookie_name, signed)
    client.cookies.set(settings.csrf_cookie_name, csrf)
    return csrf


def _extract_cookie_value(response: object, name: str) -> str:
    """Set-Cookie 文字列を直接パースして value だけ取り出す（auth_api と同じ）。"""
    set_cookie_headers = response.headers.get_list("set-cookie")  # type: ignore[attr-defined]
    prefix = f"{name}="
    for header in set_cookie_headers:
        if header.startswith(prefix):
            return header[len(prefix) :].split(";", 1)[0]
    raise AssertionError(f"Set-Cookie '{name}' not found in {set_cookie_headers!r}")


async def _current_user_id(client: AsyncClient) -> uuid.UUID:
    """ログイン済みクライアントの user.id を /auth/me から取る（テストの観測用）。"""
    res = await client.get("/auth/me")
    assert res.status_code == 200
    return uuid.UUID(res.json()["id"])


# ----------------------------------------------------------------------------
# POST /problems/generate
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
            "/problems/generate",
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
        csrf = await _login(client)

        res = await client.post(
            "/problems/generate",
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
        csrf = await _login(client)
        user_id = await _current_user_id(client)

        res = await client.post(
            "/problems/generate",
            json={"category": "string", "difficulty": "medium"},
            headers={"X-CSRF-Token": csrf},
        )
        request_id = uuid.UUID(res.json()["requestId"])

        async with AsyncSessionLocal() as s:
            grs = (await s.execute(select(GenerationRequest))).scalars().all()
            jobs = (await s.execute(select(Job))).scalars().all()

        # generation_requests に 1 行作られ、入力どおりの値 + status=pending で保存される。
        assert len(grs) == 1
        assert grs[0].id == request_id
        assert grs[0].user_id == user_id
        assert grs[0].category == "string"
        assert grs[0].difficulty == "medium"
        assert grs[0].status == "pending"
        assert grs[0].produced_problem_id is None

        # jobs にも 1 行作られ、queue / type / payload の主要キーが詰まっている。
        assert len(jobs) == 1
        assert jobs[0].queue == "generation"
        assert jobs[0].type == "problem.generate"
        assert jobs[0].state == "queued"
        payload = jobs[0].payload
        assert payload["generationRequestId"] == str(request_id)
        assert payload["userId"] == str(user_id)
        assert payload["category"] == "string"
        assert payload["difficulty"] == "medium"
        # ADR 0010：R1 期間は traceparent=None で送る。
        assert payload["traceContext"]["traceparent"] is None


class TestPostGenerateValidation:
    @respx.mock
    async def test_異常系_未知のcategoryは422(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        csrf = await _login(client)

        res = await client.post(
            "/problems/generate",
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
        csrf = await _login(client)

        res = await client.post(
            "/problems/generate",
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
        csrf = await _login(client)

        # difficulty 欠落。
        res = await client.post(
            "/problems/generate",
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
        await _login(client)

        res = await client.post(
            "/problems/generate",
            json={"category": "array", "difficulty": "easy"},
        )
        assert res.status_code == 403


# ----------------------------------------------------------------------------
# GET /problems/generate/:request_id
# ----------------------------------------------------------------------------
class TestGetStatusUnauthenticated:
    async def test_異常系_未認証なら401(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        del fake_redis
        res = await client.get(f"/problems/generate/{uuid.uuid4()}")
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
        csrf = await _login(client)

        post_res = await client.post(
            "/problems/generate",
            json={"category": "array", "difficulty": "easy"},
            headers={"X-CSRF-Token": csrf},
        )
        request_id = post_res.json()["requestId"]

        res = await client.get(f"/problems/generate/{request_id}")
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
        csrf = await _login(client)

        post_res = await client.post(
            "/problems/generate",
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

        res = await client.get(f"/problems/generate/{request_id}")
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
        csrf = await _login(client)

        post_res = await client.post(
            "/problems/generate",
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

        res = await client.get(f"/problems/generate/{request_id}")
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
        await _login(client)

        res = await client.get(f"/problems/generate/{uuid.uuid4()}")
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
        csrf_a = await _login(client, gh_id=100)
        post_res = await client.post(
            "/problems/generate",
            json={"category": "string", "difficulty": "easy"},
            headers={"X-CSRF-Token": csrf_a},
        )
        owner_request_id = post_res.json()["requestId"]

        # 一度ログアウト相当：cookie をクリアして別ユーザー B でログインし直す。
        # 既存テスト同様、respx を reset してから再ログインする。
        client.cookies.clear()
        respx.reset()
        await _login(client, gh_id=200)

        res = await client.get(f"/problems/generate/{owner_request_id}")
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
        await _login(client)

        res = await client.get("/problems/generate/not-a-uuid")
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
