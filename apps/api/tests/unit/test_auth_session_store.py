# core/session のユニットテスト。
#
# テスト方針：
#   - fakeredis.aioredis.FakeRedis で実 Redis なしに状態遷移を検証
#   - create → get → delete の round-trip と user_id 逆引き set の整合性を網羅
#   - rolling TTL のしきい値（30 分）越え挙動は time.time をモンキーパッチして強制
#
# 関わる要件：
#   - authentication.md §1.1 複数セッション許容
#   - §1.3 セッション（TTL 7 日 / rolling / 旧セッション無効化）
#   - ADR 0047

import uuid
from collections.abc import Awaitable
from typing import cast

import fakeredis.aioredis
import pytest

from app.core import session as session_store


@pytest.fixture
async def redis() -> fakeredis.aioredis.FakeRedis:
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


# fakeredis の typeshed では smembers / hset の戻り値が直接 Set / int 等になり、
# pyright が「await できない」と誤検知する。実体は coroutine なので cast で吸収する。
async def _smembers(redis: fakeredis.aioredis.FakeRedis, key: str) -> set[str]:
    return await cast("Awaitable[set[str]]", redis.smembers(key))


async def _hset_mapping(
    redis: fakeredis.aioredis.FakeRedis, key: str, mapping: dict[str, str]
) -> None:
    await cast("Awaitable[int]", redis.hset(key, mapping=mapping))


class TestSessionCreateAndGet:
    async def test_正常系_作成したセッションをsidで引ける(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        user_id = uuid.uuid4()
        created = await session_store.create(redis, user_id)

        loaded = await session_store.get(redis, created.sid)
        assert loaded is not None
        assert loaded.sid == created.sid
        assert loaded.user_id == user_id
        assert loaded.csrf_token == created.csrf_token

    async def test_正常系_sidとcsrf_tokenは別CSPRNGで重複しない(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        user_id = uuid.uuid4()
        s = await session_store.create(redis, user_id)
        assert s.sid != s.csrf_token

    async def test_正常系_user_idの逆引きsetに追加されている(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        """複数端末ログアウト対応のため、user_id → sids の逆引きを持つ。"""
        user_id = uuid.uuid4()
        s = await session_store.create(redis, user_id)

        members = await _smembers(redis, f"user:{user_id}:sessions")
        assert s.sid in members

    async def test_正常系_同一ユーザーで2セッション作ると逆引きsetに両方残る(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        """複数端末ログイン許容（authentication.md §1.1）。"""
        user_id = uuid.uuid4()
        s1 = await session_store.create(redis, user_id)
        s2 = await session_store.create(redis, user_id)
        assert s1.sid != s2.sid

        members = await _smembers(redis, f"user:{user_id}:sessions")
        assert {s1.sid, s2.sid} <= members


class TestSessionGetInvalid:
    async def test_異常系_存在しないsidはNone(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        result = await session_store.get(redis, "no-such-sid")
        assert result is None

    async def test_異常系_空文字sidはNone(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        result = await session_store.get(redis, "")
        assert result is None

    async def test_異常系_256文字超のsidは弾く(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        huge = "x" * 257
        result = await session_store.get(redis, huge)
        assert result is None

    async def test_異常系_hashデータが壊れている場合はNone(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        """user_id が UUID として parse できない場合は無効扱い。"""
        sid = "broken-sid"
        await _hset_mapping(
            redis,
            f"session:{sid}",
            mapping={
                "user_id": "not-a-uuid",
                "csrf_token": "x",
                "created_at": "0",
                "last_seen_at": "0",
            },
        )
        result = await session_store.get(redis, sid)
        assert result is None


class TestSessionRollingTouch:
    async def test_正常系_30分以上経過したget呼び出しでlast_seen_atが更新される(
        self,
        redis: fakeredis.aioredis.FakeRedis,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """rolling TTL のしきい値超えで EXPIRE が再発行され last_seen_at が進む。"""
        # 作成時の時刻を固定。
        base = 1_700_000_000
        monkeypatch.setattr(session_store, "time", lambda: float(base))

        user_id = uuid.uuid4()
        s = await session_store.create(redis, user_id)

        # 31 分後に呼び出す（_TOUCH_THRESHOLD_SECONDS=1800 を越える）。
        monkeypatch.setattr(session_store, "time", lambda: float(base + 1801))
        loaded = await session_store.get(redis, s.sid)
        assert loaded is not None
        assert loaded.last_seen_at == base + 1801

    async def test_正常系_30分未満のget呼び出しではlast_seen_atが据え置き(
        self,
        redis: fakeredis.aioredis.FakeRedis,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """毎リクエスト EXPIRE すると Redis 負荷が線形に増えるため間引く。"""
        base = 1_700_000_000
        monkeypatch.setattr(session_store, "time", lambda: float(base))

        user_id = uuid.uuid4()
        s = await session_store.create(redis, user_id)

        # 5 分後の get。
        monkeypatch.setattr(session_store, "time", lambda: float(base + 300))
        loaded = await session_store.get(redis, s.sid)
        assert loaded is not None
        assert loaded.last_seen_at == base


class TestSessionDelete:
    async def test_正常系_削除後にgetするとNoneになる(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        user_id = uuid.uuid4()
        s = await session_store.create(redis, user_id)

        await session_store.delete(redis, s.sid)
        assert await session_store.get(redis, s.sid) is None

    async def test_正常系_削除でuser_id逆引きsetから該当sidが消える(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        user_id = uuid.uuid4()
        s1 = await session_store.create(redis, user_id)
        s2 = await session_store.create(redis, user_id)

        await session_store.delete(redis, s1.sid)

        members = await _smembers(redis, f"user:{user_id}:sessions")
        assert s1.sid not in members
        assert s2.sid in members

    async def test_正常系_存在しないsidの削除は例外を出さずno_op(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        """二重ログアウト等で既に消えている sid を渡してもエラーにしない。"""
        await session_store.delete(redis, "ghost-sid")  # no raise

    async def test_正常系_空文字sidの削除も例外を出さずno_op(
        self, redis: fakeredis.aioredis.FakeRedis
    ) -> None:
        await session_store.delete(redis, "")  # no raise
