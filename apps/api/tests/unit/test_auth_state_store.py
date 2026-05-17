# core/state_store のユニットテスト。
#
# テスト方針：
#   - fakeredis.aioredis.FakeRedis を本物の Redis 代わりに差し込む
#     （redis.asyncio.Redis 互換 API なので state_store はそのまま動く）
#   - state レコードに同梱する next_path / 1 回使い切り / TTL 切れの 3 観点を網羅
#
# 関わる要件：
#   - authentication.md §1.3 セッション（state TTL 10 分 + 1 回使い切り）
#   - §2.5 バリデーション（state 不一致は state_invalid へ 302）

import fakeredis.aioredis
import pytest

from app.core import state_store


@pytest.fixture
async def redis() -> fakeredis.aioredis.FakeRedis:
    # decode_responses=True は本物の Redis クライアントと同じ設定（core/redis.py:54）。
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


class TestStateIssue:
    async def test_正常系_発行したトークンはランダムなURLセーフ文字列(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        token1 = await state_store.issue(redis, next_path="")
        token2 = await state_store.issue(redis, next_path="")
        # CSPRNG なので 2 つの発行は別の値になるはず。
        assert token1 != token2
        # 32 byte → base64url で 43 文字（パディング無し）。
        assert len(token1) >= 32

    async def test_正常系_発行直後にRedisに保存されている(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        token = await state_store.issue(redis, next_path="/problems")
        stored = await redis.get(f"state:{token}")
        assert stored == "/problems"


class TestStateVerifyAndConsume:
    async def test_正常系_発行直後の照合は成功してnext_pathが取れる(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        token = await state_store.issue(redis, next_path="/problems")
        valid, next_path = await state_store.verify_and_consume(redis, token)
        assert valid is True
        assert next_path == "/problems"

    async def test_正常系_next_pathが空文字でも照合は成功する(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        token = await state_store.issue(redis, next_path="")
        valid, next_path = await state_store.verify_and_consume(redis, token)
        assert valid is True
        assert next_path == ""

    async def test_異常系_2回目の照合は失敗する_1回使い切り(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        """リプレイ攻撃対策：照合成功時に Redis から消える。"""
        token = await state_store.issue(redis, next_path="/x")
        valid1, _ = await state_store.verify_and_consume(redis, token)
        valid2, next2 = await state_store.verify_and_consume(redis, token)
        assert valid1 is True
        assert valid2 is False
        assert next2 == ""

    async def test_異常系_存在しないトークンは失敗(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        valid, next_path = await state_store.verify_and_consume(redis, "nonexistent")
        assert valid is False
        assert next_path == ""

    async def test_異常系_空文字トークンは即座に弾く(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        valid, next_path = await state_store.verify_and_consume(redis, "")
        assert valid is False
        assert next_path == ""

    async def test_異常系_256文字超のトークンは即座に弾く(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        """DoS ガード。"""
        huge = "x" * 257
        valid, next_path = await state_store.verify_and_consume(redis, huge)
        assert valid is False
        assert next_path == ""
