# このファイルの役割：
#   /me 系の APIRouter。R1-6 で学習統計、R1-7 で生成履歴・状態管理が追加。
#
#   - GET  /api/me/stats                  : 全期間の正答率 + カテゴリ別習熟度
#   - GET  /api/me/weakness               : 正答率の低いカテゴリ Top N
#   - GET  /api/me/generations            : 自分の生成リクエスト履歴一覧
#   - POST /api/me/generations/:id/cancel : pending のキャンセル
#   - POST /api/me/generations/:id/retry  : failed の再試行
#
#   `/me` 系は「現在の認証ユーザー自身のリソース」を指す慣例パス。
#   `/api` prefix は routers/problems.py 冒頭コメントと同じ
#   （Next.js ページパスとの衝突回避）。
#
#   GET /api/submissions（自分の解答履歴一覧）は grading.md / routers/submissions.py
#   が所有しているため本 router には載せない（learning.md §API 所有権ルール）。
#
# 関わる要件：
#   - docs/requirements/4-features/learning.md §API
#   - docs/requirements/4-features/problem-generation.md §履歴・状態管理

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.deps.auth import get_current_user
from app.models.users import User
from app.schemas.me import MeStatsResponse, MeWeaknessResponse
from app.schemas.me_generations import (
    GenerationRequestCancelResponse,
    GenerationRequestRetryResponse,
    MeGenerationsListResponse,
)
from app.services.me import MeService
from app.services.me_generations import MeGenerationsService

router = APIRouter(
    prefix="/api/me",
    tags=["me"],
)

DbDep = Annotated[AsyncSession, Depends(get_async_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# ----------------------------------------------------------------------------
# GET /api/me/stats : 全期間の正答率 + カテゴリ別習熟度
# ----------------------------------------------------------------------------
@router.get(
    "/stats",
    response_model=MeStatsResponse,
)
async def get_my_stats(
    db_session: DbDep,
    user: CurrentUser,
) -> MeStatsResponse:
    """全期間・全カテゴリの正答率を返す（取得時点でリアルタイム集計）。

    - 採点完了行（status='graded'）のみカウント
    - 履歴ゼロのユーザーには total=0 / accuracy=0.0 / byCategory=[] を返す
    - ソフトデリートは無視（履歴永続保存、learning.md §ビジネスルール）
    """
    service = MeService(db_session)
    return await service.get_stats(user_id=user.id)


# ----------------------------------------------------------------------------
# GET /api/me/weakness : 弱点カテゴリ Top N
# ----------------------------------------------------------------------------
@router.get(
    "/weakness",
    response_model=MeWeaknessResponse,
)
async def get_my_weakness(
    db_session: DbDep,
    user: CurrentUser,
) -> MeWeaknessResponse:
    """正答率の低いカテゴリ Top N を返す。

    抽出ルール（learning.md §ビジネスルール）：
      - 3 問以上解答かつ正答率 50% 未満のカテゴリのみ対象
      - accuracy 昇順、tie-break で attempts 降順
      - Top 5 まで返す
    """
    service = MeService(db_session)
    return await service.get_weakness(user_id=user.id)


# ----------------------------------------------------------------------------
# GET /api/me/generations : 自分の生成リクエスト履歴一覧（ページネーション）
# ----------------------------------------------------------------------------
@router.get(
    "/generations",
    response_model=MeGenerationsListResponse,
)
async def list_my_generations(
    db_session: DbDep,
    user: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
) -> MeGenerationsListResponse:
    """自分の generation_requests を created_at DESC でページネーション付きで返す。

    - 履歴ゼロは items=[] / totalPages=0（200 のまま）
    - prompt_version は jobs.payload から JOIN 取得、消えていれば null
    - retry_count は retry_of チェーンの深さ
    """
    service = MeGenerationsService(db_session)
    return await service.list_history(user_id=user.id, page=page)


# ----------------------------------------------------------------------------
# POST /api/me/generations/:id/cancel : pending のキャンセル
# ----------------------------------------------------------------------------
@router.post(
    "/generations/{request_id}/cancel",
    response_model=GenerationRequestCancelResponse,
)
async def cancel_my_generation(
    db_session: DbDep,
    user: CurrentUser,
    request_id: Annotated[UUID, Path()],
) -> GenerationRequestCancelResponse:
    """pending のリクエストを canceled に倒す（Worker は state='dead' にして無効化）。

    - 他人のリクエスト / 存在しない → 404
    - pending 以外 → 409 Conflict
    """
    service = MeGenerationsService(db_session)
    return await service.cancel(user_id=user.id, request_id=request_id)


# ----------------------------------------------------------------------------
# POST /api/me/generations/:id/retry : failed の再試行
# ----------------------------------------------------------------------------
@router.post(
    "/generations/{request_id}/retry",
    response_model=GenerationRequestRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_my_generation(
    db_session: DbDep,
    user: CurrentUser,
    request_id: Annotated[UUID, Path()],
) -> GenerationRequestRetryResponse:
    """failed のリクエストを新規 generation_request として複製する（retry_of リンク付き）。

    - 他人のリクエスト / 存在しない → 404
    - failed 以外 → 409 Conflict
    - 成功時 → 202 + 新規 id / status='pending' / retry_of
    """
    service = MeGenerationsService(db_session)
    return await service.retry(user_id=user.id, request_id=request_id)
