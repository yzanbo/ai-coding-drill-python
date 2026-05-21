# このファイルの役割：
#   学習履歴・統計ドメインの APIRouter。R1-6 で 2 エンドポイントが揃う。
#
#   - GET /api/me/stats    : 全期間の正答率 + カテゴリ別習熟度
#   - GET /api/me/weakness : 正答率の低いカテゴリ Top N
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

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.deps.auth import get_current_user
from app.models.users import User
from app.schemas.me import MeStatsResponse, MeWeaknessResponse
from app.services.me import MeService

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
