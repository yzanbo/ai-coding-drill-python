# POST /problems/generate のレート制限の結合テスト。
#
# 要件:
#   - docs/requirements/3-cross-cutting/02-api-conventions.md §レート制限
#     「1 ユーザー / 1 分 / 5 回」を超えると 429 を返す。
#
# テスト方針:
#   - tests/conftest.py の先頭で RATE_LIMIT_STORAGE_URI=memory:// を仕込んであるため、
#     Limiter は実 Redis 不要のメモリ保存で動く。
#   - 既存の OAuth フローは通さず、session_store.create で直接セッションを発行し、
#     署名済み Cookie を AsyncClient に積んで認証状態を組み立てる
#     （目的は rate limit の挙動検証で、認証経路はテスト対象でないため）。
#   - 本テストは「rate limit デコレータ + 429 ハンドラ」が HTTP 層で正しく動くか
#     だけを確認すれば十分なので、ProblemGenerationService.enqueue_generation を
#     monkeypatch で stub に差し替える（DB / NOTIFY / ジョブキュー側は別 PR で個別に検証）。
#   - 各テストの前後で limiter.reset() を呼んでカウンタを 0 に戻す（テスト独立性）。

from collections.abc import AsyncIterator
from uuid import uuid4

import fakeredis.aioredis
import pytest
from httpx import AsyncClient

from app.core import session as session_store
from app.core.config import get_settings
from app.core.cookies import sign_sid
from app.db.session import AsyncSessionLocal
from app.deps.rate_limit import limiter
from app.models.users import User
from app.schemas.problems import (
    GenerationStatus,
    ProblemGenerateAcceptedResponse,
)
from app.services.problem_generation import ProblemGenerationService


@pytest.fixture(autouse=True)
async def reset_rate_limiter() -> AsyncIterator[None]:
    """テスト前後で slowapi のカウンタを 0 に戻す（テスト独立性）。"""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(autouse=True)
def stub_enqueue_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    """ProblemGenerationService.enqueue_generation を stub に置き換える。

    本物の実装は jobs テーブルへの NOTIFY 発行を伴うが、これは rate limit の
    検証範囲外。stub は呼ばれるたびに新しい requestId を返すだけ。
    """

    async def _fake_enqueue(self: ProblemGenerationService, **_kwargs: object) -> (
        ProblemGenerateAcceptedResponse
    ):
        del self
        return ProblemGenerateAcceptedResponse(
            request_id=uuid4(),
            status=GenerationStatus.PENDING,
        )

    monkeypatch.setattr(ProblemGenerationService, "enqueue_generation", _fake_enqueue)


async def _signed_in_client(
    client: AsyncClient,
    fake_redis: fakeredis.aioredis.FakeRedis,
    *,
    display_name: str = "Taro",
) -> User:
    """User 行を作って Redis にセッションを書き、Cookie を client に積む。

    OAuth フローを通すと respx での GitHub モックが必要になり、本テストの
    関心（rate limit）から離れるため、認証状態だけを最短経路で作る。
    """
    settings = get_settings()
    async with AsyncSessionLocal() as session:
        user = User(display_name=display_name, email=None)
        session.add(user)
        await session.commit()
        await session.refresh(user)

    sess = await session_store.create(fake_redis, user.id)
    # session_id Cookie には itsdangerous で署名した値を積む
    #   （Backend 側 unsign_sid と対称）。
    signed = sign_sid(sess.sid)
    client.cookies.set(settings.session_cookie_name, signed)
    # csrf_token Cookie は Frontend が JS で読んで X-CSRF-Token に詰める契約。
    #   結合テストでは double submit の両側を自前で組み立てる。
    client.cookies.set(settings.csrf_cookie_name, sess.csrf_token)
    return user


class TestProblemsGenerateRateLimit:
    async def test_正常系_1分以内に5回までは202を返す(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        await _signed_in_client(client, fake_redis)
        csrf = client.cookies.get(get_settings().csrf_cookie_name)
        assert csrf is not None

        for i in range(5):
            res = await client.post(
                "/problems/generate",
                json={"category": "array", "difficulty": "easy"},
                headers={"X-CSRF-Token": csrf},
            )
            assert res.status_code == 202, f"{i + 1} 回目で {res.status_code}: {res.text}"

    async def test_異常系_6回目は429を返す(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        await _signed_in_client(client, fake_redis)
        csrf = client.cookies.get(get_settings().csrf_cookie_name)
        assert csrf is not None

        # 5 回までは流して、6 回目で 429 を観測する。
        for _ in range(5):
            res = await client.post(
                "/problems/generate",
                json={"category": "array", "difficulty": "easy"},
                headers={"X-CSRF-Token": csrf},
            )
            assert res.status_code == 202

        res = await client.post(
            "/problems/generate",
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

    async def test_正常系_ユーザーが違えばカウンタは独立で5回ずつ通る(
        self,
        client: AsyncClient,
        fake_redis: fakeredis.aioredis.FakeRedis,
    ) -> None:
        """key 関数が user:<id> 単位で分離されていることを担保する。"""
        # ユーザー A で 5 回流す。
        await _signed_in_client(client, fake_redis, display_name="A")
        csrf = client.cookies.get(get_settings().csrf_cookie_name)
        assert csrf is not None
        for _ in range(5):
            res = await client.post(
                "/problems/generate",
                json={"category": "array", "difficulty": "easy"},
                headers={"X-CSRF-Token": csrf},
            )
            assert res.status_code == 202

        # ユーザー B でログイン直し（Cookie 上書き）→ 同じく 5 回成功できる。
        client.cookies.clear()
        await _signed_in_client(client, fake_redis, display_name="B")
        csrf_b = client.cookies.get(get_settings().csrf_cookie_name)
        assert csrf_b is not None
        for _ in range(5):
            res = await client.post(
                "/problems/generate",
                json={"category": "array", "difficulty": "easy"},
                headers={"X-CSRF-Token": csrf_b},
            )
            assert res.status_code == 202
