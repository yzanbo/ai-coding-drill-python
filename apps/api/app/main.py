# このファイルの役割：
#   FastAPI アプリの「組み立て」をする入口ファイル。
#   ルーターをまとめて、起動 / 終了時の処理（lifespan）を登録する。
#
#   起動時：Redis 接続を 1 回開く（以降のリクエストで使い回す）
#   終了時：Redis 接続を閉じる
#   DB は engine が import 時に作られ、リクエストごとに session が払い出される
#   （明示的な open/close は不要、→ db/session.py）。

# asynccontextmanager: 非同期版の「コンテキストマネージャ」を作るデコレータ。
#   yield の前 = 起動処理、yield の後 = 終了処理 という構造で書けるようになる。
#   FastAPI の lifespan はこの形式を要求する。
# AsyncGenerator: 非同期で値を 1 つずつ渡せる「ジェネレータ関数」の戻り値型。
#   yield を含む `async def` 関数の戻り値型に使う。
#   asynccontextmanager は AsyncIterator ではなく AsyncGenerator を要求する
#   （Python 3.12+ の typeshed で正式化）。
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from slowapi.errors import RateLimitExceeded

# verify_csrf: 状態変更 API（POST/PUT/DELETE/PATCH）の double submit cookie 検証
#              middleware（中身は core/csrf.py）。
from app.core.config import get_settings
from app.core.cookies import clear_session_cookies
from app.core.csrf import verify_csrf

# register_exception_handlers: ドメイン例外を HTTP レスポンスに変換する
#   handler を一括登録する関数（中身は core/exceptions.py）。
from app.core.exceptions import register_exception_handlers

# open_http_client / close_http_client: 共有 httpx クライアントの開閉
# （中身は core/http_client.py、GitHub OAuth 等の外部 API 呼び出しで使う）。
from app.core.http_client import close_http_client, open_http_client

# open_redis / close_redis: Redis 接続の生成と解放（中身は core/redis.py）。
from app.core.redis import close_redis, open_redis

# limiter: アプリ全体で 1 個の slowapi Limiter（中身は deps/rate_limit.py）。
# rate_limit_exceeded_handler: 超過時に 429 JSON を返す関数。
from app.deps.rate_limit import limiter, rate_limit_exceeded_handler
from app.routers import auth, health, me, probes, problems, submissions


# lifespan: FastAPI の起動 / 終了フックを 1 関数にまとめる関数。
#   @asynccontextmanager で「yield 前 = 起動、yield 後 = 終了」の形式にし、
#   FastAPI(lifespan=...) で登録すると、サーバ起動時に yield 前が走り、
#   停止時に yield 後が走る。
#
#   なぜ on_event("startup") / on_event("shutdown") を使わないか：
#     FastAPI 0.93 以降で非推奨化された旧 API のため。新規コードは lifespan を使う。
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None]:
    """アプリ起動 / 終了時の共通処理。"""
    # ---- 起動時 ----
    # Redis クライアントを 1 個作って保持する（core/redis.py の _client に格納）。
    await open_redis()
    # 外部 API 用の httpx クライアントも 1 個作って共有する。
    # 1 リクエストごとに新規作成すると接続プールが再利用されないため。
    await open_http_client()
    # yield: ここでアプリが起動完了し、リクエストを受け付ける状態になる。
    #        サーバが停止するとここから後ろが実行される。
    yield
    # ---- 終了時 ----
    # 起動と逆順で閉じる（依存関係が薄いので順序の制約は事実上ないが、
    # 「後から開いたものを先に閉じる」の慣習に揃える）。
    await close_http_client()
    await close_redis()


# FastAPI アプリ本体。title は /docs（Swagger UI）の見出しに使われる。
# lifespan= で上記の起動 / 終了処理を紐付ける。
app = FastAPI(title="AI Coding Drill API", lifespan=lifespan)

# CSRF middleware：状態変更系（POST/PUT/DELETE/PATCH）の double submit cookie 検証
# （02-api-conventions.md「CSRF 対策（double submit cookie）」）。
# GET / HEAD / OPTIONS と /auth/github 系は中で skip する。
# 認証ガード自体は各ルーター内で Depends(get_current_user) を使う（backend.md）。
app.middleware("http")(verify_csrf)


# clear_stale_session_cookie_on_401: 401 レスポンスを返す時に、リクエストが
#   session_id Cookie を持っていたら Max-Age=0 で物理削除する。
#
#   背景：Cookie はブラウザに残っているが Redis 側でセッションが失効している
#   「stale Cookie」状態のユーザーが認証必須画面 → /auth/me 401 → /login redirect
#   → /login は Cookie を見て元の画面に戻す、の無限ループを構造的に断ち切る。
#   一度 401 が返れば Cookie を消すことで、次の /login 訪問時は Cookie なし扱い
#   となり、LoginForm が表示される。
#
#   ログイン関連の正規 401（CSRF 失敗等）でも Cookie を巻き込み削除するが、
#   401 = 認証情報が無効、という解釈で問題はない（再ログインを強制する方向）。
@app.middleware("http")
async def clear_stale_session_cookie_on_401(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    if response.status_code == 401:
        settings = get_settings()
        if settings.session_cookie_name in request.cookies:
            clear_session_cookies(response)
    return response

# ドメイン例外 → HTTP レスポンスの変換ハンドラを登録する。
#   services/* が raise する業務例外（GenerationRequestNotFoundError 等)を
#   core/exceptions.py の handler が 404 等の JSON に翻訳する設計。
#   詳細は .claude/rules/backend.md §Service / app/core/README.md §2。
register_exception_handlers(app)

# レート制限：slowapi の Limiter を app.state.limiter に積む（slowapi の規約）。
#   @limiter.limit(...) デコレータはここを参照しないが、slowapi の内部処理
#   （超過時の例外 raise、ヘッダ付与）が app.state.limiter から設定を引くため必要。
# RateLimitExceeded → 429 JSON への変換ハンドラもここで登録する。
# 採用根拠は docs/requirements/3-cross-cutting/02-api-conventions.md §レート制限。
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    rate_limit_exceeded_handler,  # type: ignore[arg-type]
)

# ルーター登録：URL のグルーピング単位で main から読み込む。
# 新しい機能を作ったらここに 1 行追加していく。
app.include_router(probes.router)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(problems.router)
app.include_router(submissions.router)
app.include_router(me.router)
