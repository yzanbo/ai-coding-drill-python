# このファイルの役割：
#   GitHub OAuth フロー中の CSRF 対策に使う「state」トークンを Redis で扱うストア。
#
#   流れ：
#     1. /auth/github を叩いたら、ここで state を新規発行して Redis に保存（TTL 10 分）。
#        next（ログイン後の戻り先パス）も同じレコードに同梱する
#     2. その state を GitHub に渡し、コールバック時に同じ値が返ってくる
#     3. /auth/github/callback でその state を Redis から取り出して照合 + 即削除
#        （照合成功時に削除することで「1 回使い切り」を保証 → リプレイ攻撃対策）
#        next も同時に取り出してリダイレクト先に使う
#
#   なぜ next を Redis レコードに同梱するか：
#     旧実装では state は Redis、next は別 Cookie（auth_next）に分かれていた。
#     攻撃者の state と被害者の auth_next を組み合わせて偽コールバックを送れる
#     ような「state と next の弱い結合」が成立し得た。本実装では同じレコードに
#     束ねることで、state が valid ならその発行時の next しか取り出せない構造に
#     する（_safe_next_path で同一オリジン縛りも別途維持）。
#
#   ※ ログイン後の状態変更 API（POST /auth/logout 等）の CSRF 対策は別物
#     （double submit cookie 方式、→ 02-api-conventions.md / session.py）。

import secrets

from redis.asyncio import Redis

from app.core.config import get_settings

# キー命名規則：state:<token> でハッシュ衝突しない名前空間に置く。
#   値は next（戻り先相対パス）を入れる。空文字なら「ホームへ」を意味する。
_KEY_PREFIX = "state:"


async def issue(redis: Redis, *, next_path: str = "") -> str:
    """新しい state トークンを発行して Redis に保存する。next_path も同じ
    レコードに同梱する。

    - 値は CSPRNG（暗号学的乱数）で 32 byte 相当の URL セーフ文字列
    - TTL は Settings.state_ttl_seconds（既定 10 分、authentication.md §1.3）
    - 戻り値の文字列を GitHub 認可 URL のクエリ `state` に乗せる
    - next_path は同一オリジン相対パス（"/foo" 形式）を呼び出し側で検証済み
      前提。検証は routers/auth.py:_safe_next_path で済ませる
    """
    # token_urlsafe(32):
    #   32 byte（256 bit）相当のランダムを base64url エンコードして返す。
    #   URL に直接埋め込めて、十分な乱雑性（衝突確率は事実上 0）。
    token = secrets.token_urlsafe(32)

    settings = get_settings()
    # value に next_path を入れる。空文字でも「あえて空のレコードを置いた」
    # ことを示せる（state そのものの存在判定は変わらない）。
    await redis.set(_KEY_PREFIX + token, next_path, ex=settings.state_ttl_seconds)
    return token


async def verify_and_consume(redis: Redis, token: str) -> tuple[bool, str]:
    """state トークンが Redis に存在すれば (True, next_path) を返し、同時に
    削除する。存在しない / 期限切れ / 既に使われた場合は (False, "")。

    1 回使い切り（リプレイ攻撃対策）+ next の同梱取り出しを atomic に行う：
      - GET と DELETE を pipeline で 1 ラウンドにまとめる
      - DELETE の戻り値（削除件数）で valid 判定する
        1 = 削除に成功 = 直前まで存在していた = 有効
        0 = キーがなかった = 無効
      これにより「複数の callback が同じ state で同時に来ても 1 つしか通らない」
      ことが Redis の atomicity で保証される。

    Redis の GETDEL コマンド（Redis 6.2+）を使う実装でも同じ atomicity を
    達成できるが、redis-py 5.x の async API での getdel 戻り値型が
    Awaitable[bytes | None] | bytes | None で扱いづらいため、pipeline で
    GET + DEL を組む方が型が素直になる。
    """
    if not token or len(token) > 256:
        return False, ""

    async with redis.pipeline(transaction=True) as pipe:
        pipe.get(_KEY_PREFIX + token)
        pipe.delete(_KEY_PREFIX + token)
        results = await pipe.execute()

    # results[0] = GET の結果（next_path or None）、results[1] = DELETE 件数。
    raw_next = results[0]
    deleted = results[1]
    if deleted != 1:
        return False, ""
    # raw_next は decode_responses=True で str。None / 非 str は念のため弾く。
    if not isinstance(raw_next, str):
        return True, ""
    return True, raw_next
