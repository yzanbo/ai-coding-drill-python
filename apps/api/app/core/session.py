# このファイルの役割：
#   ログイン後のユーザーセッションを Redis に保存・取得・削除するストア。
#
#   セッションが扱う情報：
#     - user_id          : セッションがどのユーザーのものか
#     - csrf_token       : 状態変更 API（POST 等）の double submit cookie 用 CSRF トークン
#     - created_at       : セッション作成時刻（unix epoch 秒）
#     - last_seen_at     : 最終アクセス時刻（rolling TTL の更新判断に使う）
#
#   Cookie 設計（→ 02-api-conventions.md / ADR 0047）：
#     - セッション ID   = `sid` Cookie（HttpOnly + Secure + SameSite=Lax）
#     - CSRF トークン  = `csrf_token` Cookie（HttpOnly なし、JS から読める）
#
#   保存形式：
#     - key: `session:<sid>`  type=hash  TTL=7 日（操作のたびに延長＝rolling）
#     - key: `user:<user_id>:sessions`  type=set  そのユーザーの全 sid を保持
#       （複数端末ログアウト機能を将来追加する時に使う、ADR 0047）

import secrets
from collections.abc import Awaitable
from dataclasses import dataclass
from time import time
from typing import cast
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import get_settings

# redis-py 5.x の async クライアントは戻り値型を ResponseT = Awaitable[T] | T の
# 共用体で宣言しており、pyright が awaitable と解釈できないことがある（既知の問題）。
# 各コマンド呼び出し時に cast(Awaitable[...], ...) で実態に揃える小ヘルパで吸収する。

_SESSION_KEY_PREFIX = "session:"
_USER_SESSIONS_KEY_PREFIX = "user:"
_USER_SESSIONS_KEY_SUFFIX = ":sessions"

# rolling TTL の更新間隔：毎リクエスト EXPIRE すると Redis 負荷が増えるため、
# 最終アクセスから 30 分以上経った時のみ延長する（ADR 0047 §やらないこと）。
_TOUCH_THRESHOLD_SECONDS = 1800


def _session_key(sid: str) -> str:
    return _SESSION_KEY_PREFIX + sid


def _user_sessions_key(user_id: UUID) -> str:
    return _USER_SESSIONS_KEY_PREFIX + str(user_id) + _USER_SESSIONS_KEY_SUFFIX


# Session: Redis から読み出したセッションの中身を Python オブジェクトで表す入れ物。
#   @dataclass を使うと、__init__ / __repr__ / __eq__ が自動生成される。
#   slots=True でメモリ消費を抑える。
@dataclass(slots=True)
class Session:
    """Redis から読み出したセッションの値オブジェクト。

    属性は authentication.md §1.3 と ADR 0047 の保存項目に対応：
      - sid          : セッション ID（Cookie に入る値）
      - user_id      : 認証済みユーザーの UUID
      - csrf_token   : double submit cookie の照合用トークン
      - created_at   : セッション作成時刻（unix epoch 秒）
      - last_seen_at : 最終アクセス時刻（unix epoch 秒）
    """

    sid: str
    user_id: UUID
    csrf_token: str
    created_at: int
    last_seen_at: int


# create: ログイン成功時に呼ぶ「セッションを 1 個作る」関数。
async def create(redis: Redis, user_id: UUID) -> Session:
    """新規セッションを発行し、Redis に保存して Session 値を返す。

    - sid と csrf_token は別々の CSPRNG（混同を防ぐため明示的に別生成）
    - TTL は Settings.session_ttl_seconds（既定 7 日）
    - 同じユーザーが複数端末でログインしても許容される（authentication.md §1.1）
    """
    sid = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(32)
    # time(): 現在時刻を unix epoch（1970-01-01 からの経過秒）の float で返す。
    #   int() で秒精度に落として保存（ミリ秒精度は本用途に不要）。
    now = int(time())

    settings = get_settings()
    ttl = settings.session_ttl_seconds

    # pipeline + transaction=True: MULTI/EXEC で 4 コマンドを atomic に実行する。
    #   セッション作成は「hash の SET + EXPIRE + user_id 側 set への SADD + EXPIRE」の
    #   4 コマンドが必要で、途中で 1 つでも失敗すると
    #     - session:<sid> hash は作られたが user:<id>:sessions set に sid が無い
    #     - その逆（sid が set に居るが hash が無い）
    #   といった壊れた状態が残る。MULTI/EXEC で 1 つでも失敗したら全部巻き戻すことで
    #   この中間状態を作らない。ログイン処理は 1 リクエストに 1 回しか走らないため、
    #   MULTI/EXEC のオーバーヘッドは無視できる。
    async with redis.pipeline(transaction=True) as pipe:
        # hset: hash 型キーに複数フィールドを一括 SET する。
        #   mapping= で {フィールド名: 値} を渡す。
        #   redis-py の型は str | None だけ受け付けるため、数値は str に変換しておく。
        pipe.hset(
            _session_key(sid),
            mapping={
                "user_id": str(user_id),
                "csrf_token": csrf_token,
                "created_at": str(now),
                "last_seen_at": str(now),
            },
        )
        pipe.expire(_session_key(sid), ttl)
        # 複数端末ログアウト対応のため、user_id 側にも sid を逆引きできるよう SADD する。
        # 個別 sid の expire と同期させたいので、こちら側にも同じ TTL を設定。
        pipe.sadd(_user_sessions_key(user_id), sid)
        pipe.expire(_user_sessions_key(user_id), ttl)
        await pipe.execute()

    return Session(
        sid=sid,
        user_id=user_id,
        csrf_token=csrf_token,
        created_at=now,
        last_seen_at=now,
    )


# get: リクエストごとに Cookie の sid から Session を引く関数。
#   ヒットしたら rolling TTL を必要に応じて延長する。
async def get(redis: Redis, sid: str) -> Session | None:
    """Cookie の sid から Session を取得する。存在しない / 期限切れなら None。

    - 最終アクセスから _TOUCH_THRESHOLD_SECONDS 以上経過していれば TTL を延長
      （毎リクエスト EXPIRE すると Redis 負荷が線形に増えるため間引く、ADR 0047）
    """
    if not sid or len(sid) > 256:
        return None

    # hgetall: hash の全フィールドを一括取得する。
    #   キーが無い / 期限切れの場合は空 dict が返る（None ではない点に注意）。
    #   redis-py async の戻り値型は Awaitable[T] | T 共用体のため、cast で実態に揃える。
    data = await cast("Awaitable[dict[str, str]]", redis.hgetall(_session_key(sid)))
    if not data:
        return None

    # data の各値は decode_responses=True 設定により str。
    # user_id / *_at は変換が必要。
    try:
        user_id = UUID(data["user_id"])
        csrf_token = data["csrf_token"]
        created_at = int(data["created_at"])
        last_seen_at = int(data["last_seen_at"])
    except (KeyError, ValueError):
        # Redis のデータが壊れていた場合（バージョン差分等）はセッション無効として扱う。
        return None

    settings = get_settings()
    now = int(time())

    # rolling TTL：閾値を超えていたら last_seen_at 更新 + EXPIRE 延長を 1 ラウンドで。
    if now - last_seen_at >= _TOUCH_THRESHOLD_SECONDS:
        async with redis.pipeline(transaction=False) as pipe:
            pipe.hset(_session_key(sid), "last_seen_at", str(now))
            pipe.expire(_session_key(sid), settings.session_ttl_seconds)
            pipe.expire(
                _user_sessions_key(user_id),
                settings.session_ttl_seconds,
            )
            await pipe.execute()
        last_seen_at = now

    return Session(
        sid=sid,
        user_id=user_id,
        csrf_token=csrf_token,
        created_at=created_at,
        last_seen_at=last_seen_at,
    )


# delete: ログアウト時に呼ぶ「セッションを 1 個消す」関数。
async def delete(redis: Redis, sid: str) -> None:
    """指定セッションを破棄する。存在しない sid を渡しても何もしないだけで例外なし。

    - user_id 側の set からも該当 sid を取り除く（残骸を残さない）
    - sid が無効なら早期 return
    """
    if not sid or len(sid) > 256:
        return

    # user_id を取り出すために先に hget しておく（delete 前なら拾える）。
    # redis-py async の戻り値型は Awaitable[T] | T 共用体のため、cast で実態に揃える。
    user_id_raw = await cast(
        "Awaitable[str | None]", redis.hget(_session_key(sid), "user_id")
    )
    if user_id_raw is None:
        # 既に削除済み / 期限切れ。残骸も無いはずなので何もしない。
        return
    try:
        user_id = UUID(user_id_raw)
    except ValueError:
        # データ破損時は本体だけ消して終わり。
        await redis.delete(_session_key(sid))
        return

    async with redis.pipeline(transaction=False) as pipe:
        pipe.delete(_session_key(sid))
        pipe.srem(_user_sessions_key(user_id), sid)
        await pipe.execute()
