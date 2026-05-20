# このファイルの役割：
#   FastAPI のレート制限（slowapi + Redis）の入口。
#   ここで Limiter を 1 個作って main.py が app.state.limiter に積む。
#   各 router は from app.deps.rate_limit import limiter / `@limiter.limit("5/minute")` で使う。
#
# 設計：
#   - 保存先（カウンタ置き場）は Redis。本番は同一 Redis インスタンスを使い回す
#     （セッション / キャッシュと同居。ADR 0005 で「ジョブキュー以外の Redis 用途」として整理済）。
#   - 採用アルゴリズムは Sliding Log（slowapi では "moving-window" 文字列）。
#     1 分間に「直近の N 件のリクエスト時刻を見て判定する」方式。
#     fixed-window 系より境界をまたいだバースト（59 秒目に 5 件 + 1 分 1 秒目に 5 件）に強い。
#     詳細採用根拠は docs/requirements/2-foundation/01-non-functional.md §セキュリティ。
#   - key（誰のカウンタか）は認証済みユーザーは user:<id>、未認証は ip:<addr> に倒す。
#     ID と IP を別 namespace にしておくと、未認証時の「同一 IP 多数ユーザー」と
#     認証時の「ユーザー単位の制御」が混ざらない。
#   - 超過時は core/exceptions.py 経由ではなく、本ファイルの handler で直接 429 JSON を返す。
#     RateLimitExceeded は slowapi のライブラリ例外で、ドメイン例外ではないため。
#
# 関わる要件：
#   - docs/requirements/3-cross-cutting/02-api-conventions.md §レート制限
#   - docs/requirements/2-foundation/01-non-functional.md §セキュリティ（Sliding Log 採用）
#   - docs/requirements/2-foundation/05-runtime-stack.md §キャッシュ / セッション

from __future__ import annotations

from fastapi import Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import get_settings


# get_rate_limit_key: 「誰のカウンタを引くか」を決める関数。
#   - 認証済み: user:<UUID 文字列>
#   - 未認証:   ip:<IP アドレス>
#   request.state.user は deps/auth.py の get_current_user_optional が積む。
#   未認証 / そもそも optional ガードを通っていないルートでは属性が無いので
#   getattr で None フォールバックして IP に倒す。
def get_rate_limit_key(request: Request) -> str:
    """ユーザー単位（認証時）/ IP 単位（匿名時）のキーを返す。"""
    user = getattr(request.state, "user", None)
    if user is not None:
        # User.id は SQLAlchemy の Mapped[UUID]。str() で安定文字列にする。
        return f"user:{user.id}"
    # get_remote_address は X-Forwarded-For を尊重する（slowapi 同梱のユーティリティ）。
    return f"ip:{get_remote_address(request)}"


def _build_limiter() -> Limiter:
    """設定を読んで Limiter を 1 個組み立てる。

    関数に分けているのは、テストで `get_settings.cache_clear()` を呼んだあとに
    再構築できるようにするため（プロダクション運用では import 時 1 回だけ呼ばれる）。
    """
    settings = get_settings()
    # rate_limit_storage_uri が None なら redis_url を使う（本番運用の既定）。
    #   テスト時は環境変数 RATE_LIMIT_STORAGE_URI=memory:// で in-memory に倒す。
    storage_uri = settings.rate_limit_storage_uri or settings.redis_url
    return Limiter(
        key_func=get_rate_limit_key,
        storage_uri=storage_uri,
        # strategy: "moving-window" は Sliding Log の slowapi 名（1 分の境目バーストに強い）。
        strategy="moving-window",
        # headers_enabled: X-RateLimit-* / Retry-After を自動付与
        #   （クライアントが残量を観測できる）。
        headers_enabled=True,
        # key_prefix: Redis 上の他用途（session: 等）と名前衝突しないよう接頭辞を付ける。
        key_prefix="ratelimit",
    )


# limiter: アプリ全体で 1 個の Limiter（モジュールレベル singleton）。
#   router 側で from app.deps.rate_limit import limiter と読んで @limiter.limit(...) を貼る。
limiter = _build_limiter()


# rate_limit_exceeded_handler: RateLimitExceeded → 429 JSON に変換する関数。
#   FastAPI の add_exception_handler に渡して登録する（main.py が呼ぶ）。
#   detail は日本語、retry-after 秒数も同梱する（slowapi が自動でヘッダにも付ける）。
async def rate_limit_exceeded_handler(
    _request: Request,
    exc: RateLimitExceeded,
) -> JSONResponse:
    """429 + 日本語 detail。"""
    # exc.detail は "5 per 1 minute" 形式の人間向け文字列（slowapi 既定）。
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "detail": "リクエストが多すぎます。しばらく時間を置いてから再度お試しください。",
            "limit": str(exc.detail),
        },
    )
