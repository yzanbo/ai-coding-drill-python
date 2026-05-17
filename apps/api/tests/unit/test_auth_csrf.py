# core/csrf.verify_csrf middleware のユニットテスト。
#
# テスト方針：
#   - 最小の FastAPI アプリ（dummy ルート 3 本）に verify_csrf を載せて
#     ASGI 経由で叩く（実 main.py の lifespan / Redis 起動には依存しない）
#   - core.csrf.get_redis を monkeypatch で fakeredis に差し替える
#   - 実 session_store.create を使って sid + csrf_token のペアを作り、
#     Cookie / X-CSRF-Token の組み合わせをパターン網羅する
#
# 関わる要件：
#   - authentication.md §1.3 CSRF 対策（state 系 / double submit cookie）
#   - §2.5 バリデーション
#   - 02-api-conventions.md「CSRF 対策（double submit cookie）」

import uuid
from collections.abc import AsyncIterator

import fakeredis.aioredis
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core import csrf as csrf_module
from app.core import session as session_store
from app.core.config import get_settings
from app.core.cookies import sign_sid
from app.core.csrf import verify_csrf


def _make_app() -> FastAPI:
    """検証用に最小ルートを 3 本だけ持つ FastAPI アプリ。"""
    app = FastAPI()
    app.middleware("http")(verify_csrf)

    @app.get("/get-route")
    async def _get() -> dict[str, str]:
        return {"ok": "true"}

    @app.post("/post-route")
    async def _post() -> dict[str, str]:
        return {"ok": "true"}

    @app.post("/health")  # _EXEMPT_PATHS の片方
    async def _health() -> dict[str, str]:
        return {"exempt": "true"}

    @app.post("/auth/github/callback")  # _EXEMPT_PATHS のもう片方
    async def _cb() -> dict[str, str]:
        return {"exempt": "true"}

    return app


@pytest.fixture
async def redis(monkeypatch: pytest.MonkeyPatch) -> fakeredis.aioredis.FakeRedis:
    """csrf.get_redis を fakeredis に差し替えてセッションも実関数で作れるようにする。"""
    r = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(csrf_module, "get_redis", lambda: r)
    return r


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=_make_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def _create_session(
    redis: fakeredis.aioredis.FakeRedis,
) -> tuple[str, str]:
    """sid + csrf_token を発行して Cookie に積める形（署名済み sid）まで返す。"""
    s = await session_store.create(redis, uuid.uuid4())
    return sign_sid(s.sid), s.csrf_token


def _set_session_cookie(client: AsyncClient, signed_sid: str) -> None:
    """httpx 0.28+ では per-request cookies が deprecated のため client.cookies に積む。"""
    client.cookies.set(get_settings().session_cookie_name, signed_sid)


class TestCsrfSkippedMethods:
    async def test_正常系_GETはCSRF検証をスキップ(
        self, client: AsyncClient, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del redis  # fixture を発火させたいだけ
        res = await client.get("/get-route")
        assert res.status_code == 200


class TestCsrfExemptPaths:
    async def test_正常系_health_POSTはexemptで素通り(
        self, client: AsyncClient, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del redis
        res = await client.post("/health")
        assert res.status_code == 200

    async def test_正常系_auth_github_callback_POSTもexemptで素通り(
        self, client: AsyncClient, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del redis
        res = await client.post("/auth/github/callback")
        assert res.status_code == 200


class TestCsrfReject:
    async def test_異常系_Cookieなしで保護POSTは401(
        self, client: AsyncClient, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del redis
        res = await client.post("/post-route")
        assert res.status_code == 401

    async def test_異常系_署名不正のsid_Cookieで401(
        self, client: AsyncClient, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del redis
        _set_session_cookie(client, "garbage.value")
        res = await client.post("/post-route", headers={"X-CSRF-Token": "whatever"})
        assert res.status_code == 401

    async def test_異常系_署名は通るがRedisにセッションが無い場合は401(
        self, client: AsyncClient, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        del redis  # Redis を空のまま使う
        _set_session_cookie(client, sign_sid("ghost-sid"))
        res = await client.post("/post-route", headers={"X-CSRF-Token": "x"})
        assert res.status_code == 401

    async def test_異常系_セッションありでヘッダー欠落なら403(
        self, client: AsyncClient, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        signed_sid, _csrf = await _create_session(redis)
        _set_session_cookie(client, signed_sid)
        res = await client.post("/post-route")
        assert res.status_code == 403

    async def test_異常系_セッションありでヘッダー値が不一致なら403(
        self, client: AsyncClient, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        signed_sid, csrf = await _create_session(redis)
        _set_session_cookie(client, signed_sid)
        res = await client.post("/post-route", headers={"X-CSRF-Token": csrf + "tamper"})
        assert res.status_code == 403


class TestCsrfAccept:
    async def test_正常系_sid_CookieとX_CSRF_Tokenが一致なら次へ進む(
        self, client: AsyncClient, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        signed_sid, csrf = await _create_session(redis)
        _set_session_cookie(client, signed_sid)
        res = await client.post("/post-route", headers={"X-CSRF-Token": csrf})
        assert res.status_code == 200
        assert res.json() == {"ok": "true"}
