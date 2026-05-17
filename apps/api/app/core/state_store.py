# このファイルの役割：
#   GitHub OAuth フロー中の CSRF 対策に使う「state」トークンを Redis で扱うストア。
#
#   流れ：
#     1. /auth/github を叩いたら、ここで state を新規発行して Redis に保存（TTL 10 分）
#     2. その state を GitHub に渡し、コールバック時に同じ値が返ってくる
#     3. /auth/github/callback でその state を Redis から取り出して照合 + 即削除
#        （照合成功時に削除することで「1 回使い切り」を保証 → リプレイ攻撃対策）
#
#   ※ ログイン後の状態変更 API（POST /auth/logout 等）の CSRF 対策は別物
#     （double submit cookie 方式、→ 02-api-conventions.md / session.py）。
#     こちらは「ログイン前の OAuth フロー専用」の使い切りトークン。

# secrets: Python 標準。暗号学的に安全な乱数を作る公式モジュール。
#   random と違って Cookie / トークン / API キー等のセキュリティ用途に使える。
import secrets

# Redis: redis-py の非同期クライアントの型注釈用 import。
from redis.asyncio import Redis

# get_settings: TTL 値を .env / Settings から取り出すために使う。
from app.core.config import get_settings

# キー命名規則：state:<token> でハッシュ衝突しない名前空間に置く。
#   値そのものに意味がないので、value は「予約済み」を示す固定文字列 "1" でよい。
#   キーが存在すること自体が「未使用の有効なトークン」を意味する。
_KEY_PREFIX = "state:"


# new_state: 新しい state トークンを発行して Redis に保存し、文字列を返す。
async def issue(redis: Redis) -> str:
    """新しい state トークンを発行して Redis に保存する。

    - 値は CSPRNG（暗号学的乱数）で 32 byte 相当の URL セーフ文字列
    - TTL は Settings.state_ttl_seconds（既定 10 分、authentication.md §1.3）
    - 戻り値の文字列を GitHub 認可 URL のクエリ `state` に乗せる
    """
    # token_urlsafe(32):
    #   32 byte（256 bit）相当のランダムを base64url エンコードして返す。
    #   URL に直接埋め込めて、十分な乱雑性（衝突確率は事実上 0）。
    token = secrets.token_urlsafe(32)

    settings = get_settings()
    # set(name, value, ex=...):
    #   Redis の SET コマンド。ex= で TTL（秒）を指定すると、サーバ側で自動的に
    #   期限が来たらキーが消える（cron 不要）。
    #   nx=True を付けない理由：token は CSPRNG で必ず一意のため衝突想定不要。
    await redis.set(_KEY_PREFIX + token, "1", ex=settings.state_ttl_seconds)
    return token


# verify_and_consume: コールバック時に呼び、state が有効なら True を返してその場で削除する。
#   1 回使い切り（リプレイ攻撃対策）を保証するため、「照合成功 = 即削除」を 1 操作で行う。
async def verify_and_consume(redis: Redis, token: str) -> bool:
    """state トークンが Redis に存在すれば True を返し、同時に削除する。

    - 存在しない / 期限切れ / 既に使われた場合は False
    - 競合条件を避けるため delete の戻り値（削除件数）で判定する：
        1 = 削除に成功 = 直前まで存在していた = 有効
        0 = キーがなかった = 無効
      これにより「複数の callback が同じ state で同時に来ても 1 つしか通らない」
      ことが Redis 単一コマンドの atomicity で保証される。
    """
    # 空文字や明らかに長すぎる入力はそもそも Redis に問い合わせる前に弾く。
    # （DoS や Redis に対する無駄な負荷を避ける軽い前段フィルタ）
    if not token or len(token) > 256:
        return False

    # delete: 指定キーを削除し、削除できた件数（0 or 1）を返す。
    #   存在チェック → 削除を 1 コマンドにまとめることで競合状態を避ける。
    deleted = await redis.delete(_KEY_PREFIX + token)
    return deleted == 1
