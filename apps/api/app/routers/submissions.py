# このファイルの役割：
#   解答送信ドメインの APIRouter。R1-5 で 3 エンドポイントが揃う。
#
#   - POST /api/submissions       : 解答を受け付けて submissions 行を作成（202 即返）
#                                   + 同 tx で jobs INSERT + NOTIFY（R1-5）
#   - GET  /api/submissions/:id   : 採点結果ポーリング用（R1-5）
#   - GET  /api/submissions       : 自分の解答履歴一覧（R1-5）
#
#   /api prefix の理由は routers/problems.py 冒頭コメントと同じ
#   （Next.js ページパスとの衝突回避）。
#
# 関わる要件：
#   - docs/requirements/4-features/grading.md §API
#   - docs/requirements/4-features/problem-display-and-answer.md §「実行」ボタン

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.deps.auth import get_current_user
from app.deps.rate_limit import limiter
from app.models.users import User
from app.schemas.submissions import (
    SUBMISSIONS_PAGE_SIZE,
    SUBMISSIONS_PAGE_SIZE_MAX,
    SubmissionAcceptedResponse,
    SubmissionCreateRequest,
    SubmissionsListResponse,
    SubmissionStatusResponse,
)
from app.services.submissions import SubmissionService

router = APIRouter(
    prefix="/api/submissions",
    tags=["submissions"],
)

DbDep = Annotated[AsyncSession, Depends(get_async_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# ----------------------------------------------------------------------------
# POST /api/submissions : 解答送信（202 + submissionId 即返）
# ----------------------------------------------------------------------------
@router.post(
    "",
    response_model=SubmissionAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
# @limiter.limit: 1 ユーザー 1 分あたり 20 回まで。
#   問題生成（5/min）より緩く、ただし採点はコストがそれなりに掛かるため 20 に抑える。
#   閾値は 01-non-functional.md / 02-api-conventions.md と整合させて運用で調整する。
@limiter.limit("20/minute")
async def submit_answer(
    request: Request,
    response: Response,
    body: SubmissionCreateRequest,
    db_session: DbDep,
    user: CurrentUser,
) -> SubmissionAcceptedResponse:
    """解答コードを受け付けて submissions 行を作成し、202 で submissionId を返す。

    挙動：
      - 対象問題の存在確認（存在しない / soft delete 済みは 404）
      - submissions に 1 行 INSERT（status='pending'）
      - 同一トランザクション内で jobs に 1 行 INSERT + NOTIFY new_job
      - レート制限: 1 ユーザー 1 分 / 20 回まで

    クライアントはレスポンスの submissionId を持って
    GET /api/submissions/:id をポーリングし、status が graded / failed に遷移するのを待つ。
    """
    del request, response
    service = SubmissionService(db_session)
    return await service.submit_answer(
        user_id=user.id,
        problem_id=body.problem_id,
        code=body.code,
    )


# ----------------------------------------------------------------------------
# GET /api/submissions : 自分の解答履歴一覧（ページング）
# ----------------------------------------------------------------------------
#
# 注意: パス順序として `""`（履歴一覧）を `"/{submission_id}"`（個別）より先に
#       宣言する。これは FastAPI 公式の "Path operations are evaluated in order"
#       挙動と整合させるため（`/{id}` が先だと文字列リテラルパスを掴むケースがある）。
@router.get(
    "",
    response_model=SubmissionsListResponse,
)
async def list_my_submissions(
    db_session: DbDep,
    user: CurrentUser,
    # Query(...): デフォルト値・最小・最大を OpenAPI に出す。
    #   page: 1 始まり、page_size: SUBMISSIONS_PAGE_SIZE_MAX を上限に設定。
    #   alias: クライアント側 ?pageSize= を受け取れるよう camelCase 別名を持たせる。
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[
        int,
        Query(ge=1, le=SUBMISSIONS_PAGE_SIZE_MAX, alias="pageSize"),
    ] = SUBMISSIONS_PAGE_SIZE,
) -> SubmissionsListResponse:
    """自分の解答履歴をページングで返す。

    並び順は created_at DESC（新着順）。problem_title まで含めて返すため
    一覧 UI 側は追加の問題詳細取得が不要。
    """
    service = SubmissionService(db_session)
    return await service.list_submissions(
        user_id=user.id,
        page=page,
        page_size=page_size,
    )


# ----------------------------------------------------------------------------
# GET /api/submissions/:id : 採点結果取得（ポーリング用）
# ----------------------------------------------------------------------------
@router.get(
    "/{submission_id}",
    response_model=SubmissionStatusResponse,
)
async def get_submission(
    db_session: DbDep,
    user: CurrentUser,
    submission_id: Annotated[UUID, Path(description="解答 ID")],
) -> SubmissionStatusResponse:
    """採点状態 + 結果を返す。

    - pending の間は score / totalCount / result / gradedAt が None
    - graded / failed に遷移してから埋まる（Worker が UPDATE）
    - 他人の id や存在しない id は 404
    """
    service = SubmissionService(db_session)
    return await service.get_submission(
        user_id=user.id,
        submission_id=submission_id,
    )
