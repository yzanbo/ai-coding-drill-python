# このファイルの役割：
#   問題ドメインの APIRouter。R1-3 + R1-4 時点で 4 エンドポイントを持つ。
#
#   - POST /api/problems/generate              : 生成リクエストの enqueue（202 即返、R1-3）
#   - GET  /api/problems/generate/:requestId   : 生成ステータス取得（ポーリング用、R1-3）
#   - GET  /api/problems                       : 問題一覧（フィルタ + ページング、R1-4）
#   - GET  /api/problems/:problemId            : 問題詳細（テストケース一部マスク、R1-4）
#
#   prefix に /api を被せている理由：
#     Frontend の Next.js ページパス（/problems/new, /problems/generate/:requestId）と
#     API パスを構造的に分離するため。Hey API クライアントは同一オリジン相対パスで
#     叩く設計（apps/web/src/lib/api/api-client.ts の baseUrl: ""）で、
#     Next.js の rewrites（apps/web/next.config.ts）が /api/* を FastAPI に
#     裏で転送する。/api prefix が無いと /problems/generate/:requestId が
#     Next.js のページパスと完全衝突して、ブラウザナビゲーションが API JSON に
#     置き換わってしまう。/auth, /health, /healthz は callback URL 登録や
#     インフラ慣習の都合で /api を被せず素のまま残してある。
#
#   LLM 呼び出しは Worker 側に閉じる（ADR 0040）ため、本 Router は
#   「DB に行を作って NOTIFY を撃つ」「DB から状態を引いて返す」だけ。
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md §API

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.deps.auth import get_current_user
from app.deps.rate_limit import limiter
from app.models.users import User
from app.schemas.problems import (
    PROBLEMS_PAGE_SIZE,
    ProblemCategory,
    ProblemDetailResponse,
    ProblemDifficulty,
    ProblemGenerateAcceptedResponse,
    ProblemGenerateRequest,
    ProblemGenerateStatusResponse,
    ProblemListResponse,
)
from app.services.problem_generation import ProblemGenerationService
from app.services.problems import ProblemService

# APIRouter: URL をグループ単位でまとめる箱。
# 認証は各エンドポイントの `user: CurrentUser` 引数で必須化する。
# router-level の dependencies=[Depends(get_current_user)] は付けない：
#   - 関数引数で user.id を使うため必ず CurrentUser を受け取る作り
#   - router-level と関数引数の両方に並ぶと「2 段ガード」と誤読される
#   - 既存 auth router（routers/auth.py）も router-level dep を持たない統一感
# tags: Swagger UI のグルーピング表示。
router = APIRouter(
    prefix="/api/problems",
    tags=["problems"],
)

# DI エイリアス。Annotated + Depends を毎回書くと冗長なのでまとめる。
DbDep = Annotated[AsyncSession, Depends(get_async_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# ----------------------------------------------------------------------------
# POST /api/problems/generate : 生成リクエストの受付（202 + requestId 即返）
# ----------------------------------------------------------------------------
@router.post(
    "/generate",
    response_model=ProblemGenerateAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
# @limiter.limit: 1 ユーザー 1 分あたり 5 回まで（02-api-conventions.md §レート制限）。
#   キーは deps/rate_limit.py の get_rate_limit_key が決定（認証時は user:<id>）。
#   超過時は slowapi が RateLimitExceeded を投げ、main.py で 429 JSON に変換される。
#   request: Request 引数は slowapi が key 関数の引数として読むため必須。
#   response: Response 引数は slowapi が X-RateLimit-* / Retry-After ヘッダを
#     書き込むために必要（Limiter の headers_enabled=True と対）。
@limiter.limit("5/minute")
async def request_problem_generation(
    request: Request,
    response: Response,
    body: ProblemGenerateRequest,
    db_session: DbDep,
    user: CurrentUser,
) -> ProblemGenerateAcceptedResponse:
    """カテゴリ・難易度を受け取って生成ジョブを enqueue する。

    挙動：
      - generation_requests へ 1 行 INSERT（status='pending'）
      - jobs へ 1 行 INSERT + NOTIFY new_job を同一トランザクションで実行
      - 202 で requestId を返す。実際の生成は Worker が非同期で処理する
      - レート制限: 同一ユーザーで 1 分 / 5 回を超えると 429 を返す
    """
    # request / response 引数は slowapi がデコレータで使うだけ（本体ロジックでは不要）。
    del request, response
    service = ProblemGenerationService(db_session)
    return await service.enqueue_generation(
        user_id=user.id,
        category=body.category,
        difficulty=body.difficulty,
    )


# ----------------------------------------------------------------------------
# GET /api/problems/generate/:requestId : 生成ステータス取得（ポーリング）
# ----------------------------------------------------------------------------
@router.get(
    "/generate/{request_id}",
    response_model=ProblemGenerateStatusResponse,
)
async def get_problem_generation_status(
    db_session: DbDep,
    user: CurrentUser,
    # Path(...): URL パスパラメータ。Annotated + Path で 型変換 + OpenAPI 反映。
    request_id: Annotated[UUID, Path(description="生成リクエストの ID")],
) -> ProblemGenerateStatusResponse:
    """生成リクエストの現在ステータスを返す。

    - 自分のリクエストでない / 存在しないリクエスト ID には 404 を返す
      （他人のリクエストか存在しないかの区別は付けない、情報漏洩防止）
    - status='completed' の時のみ problemId フィールドが付く
    """
    # GenerationRequestNotFoundError は core/exceptions.py の global handler が
    # 404 + 統一メッセージに変換するため、ここでは try/except しない。
    service = ProblemGenerationService(db_session)
    return await service.get_status(
        user_id=user.id,
        request_id=request_id,
    )


# ----------------------------------------------------------------------------
# GET /api/problems : 問題一覧（ゲスト閲覧可、フィルタ + ページング、R1-4）
# ----------------------------------------------------------------------------
# 認証不要：problem-display-and-answer.md §ビジネスルール
#   「問題閲覧はゲストでも可」のため CurrentUser を取らない。
#
# ルーティング順の注意：
#   /api/problems の prefix 下に既に POST /generate, GET /generate/{request_id}
#   が登録されている。本ルートは "" でルート直下、次ルートは "/{problem_id}"
#   で UUID 受け。FastAPI は登録順に match を試みるため、/generate 系を
#   先に登録した状態でこの 2 つを後置すれば衝突しない（/generate は文字列
#   リテラルとして先に当たる）。
@router.get(
    "",
    response_model=ProblemListResponse,
)
async def list_problems(
    db_session: DbDep,
    # Query(...): URL クエリパラメータ。Annotated + Query で OpenAPI に反映。
    #   category / difficulty は未指定（None）ならフィルタしない。
    #   page は 1 始まり、上限は付けない（DB 側で範囲外なら空 items を返す）。
    category: Annotated[ProblemCategory | None, Query(description="カテゴリで絞り込み")] = None,
    difficulty: Annotated[
        ProblemDifficulty | None, Query(description="難易度で絞り込み")
    ] = None,
    page: Annotated[int, Query(ge=1, description="ページ番号（1 始まり）")] = 1,
    # page_size: 1 ページあたりの件数。
    #   既定 20 / 上限なし（クライアント側で全件取得したい時に大きい値を渡せるように）。
    page_size: Annotated[
        int, Query(ge=1, description="1 ページあたりの件数（上限なし）")
    ] = PROBLEMS_PAGE_SIZE,
) -> ProblemListResponse:
    """カテゴリ・難易度フィルタ付きで問題一覧を返す。

    - 認証不要（ゲスト閲覧可、problem-display-and-answer.md §ビジネスルール）
    - 並び順は created_at DESC（新着優先）
    - 0 件でも 200 + items=[] / totalPages=0 で返す
    """
    service = ProblemService(db_session)
    return await service.list_problems(
        category=category,
        difficulty=difficulty,
        page=page,
        page_size=page_size,
    )


# ----------------------------------------------------------------------------
# GET /api/problems/:problemId : 問題詳細（テストケース一部マスク、R1-4）
# ----------------------------------------------------------------------------
@router.get(
    "/{problem_id}",
    response_model=ProblemDetailResponse,
)
async def get_problem_detail(
    db_session: DbDep,
    problem_id: Annotated[UUID, Path(description="問題の ID")],
) -> ProblemDetailResponse:
    """問題詳細を返す。テストケース全体は返さず examples（公開用 1〜数件）のみ含む。

    - 認証不要（problem-display-and-answer.md §ビジネスルール）
    - 存在しない / ソフトデリート済みは 404
    - レスポンスから test_cases / reference_solution / judge_scores を完全に
      落とすマスキングは ProblemDetailResponse のスキーマ定義で実施される
    """
    service = ProblemService(db_session)
    return await service.get_detail(problem_id=problem_id)
