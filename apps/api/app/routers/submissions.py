# このファイルの役割：
#   解答送信ドメインの APIRouter。R1-4 時点では POST 1 本のみ。
#
#   - POST /api/submissions : 解答を受け付けて submissions 行を作成（202 即返）
#
#   GET /api/submissions/:id（採点結果ポーリング）と GET /api/submissions（履歴一覧）は
#   R1-5（grading.md）と R1-7（learning.md）で追加する。
#
#   /api prefix の理由は routers/problems.py 冒頭コメントと同じ
#   （Next.js ページパスとの衝突回避）。
#
# 関わる要件：
#   - docs/requirements/4-features/grading.md §API #post-submissions
#   - docs/requirements/4-features/problem-display-and-answer.md §「実行」ボタン

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.deps.auth import get_current_user
from app.deps.rate_limit import limiter
from app.models.users import User
from app.schemas.submissions import (
    SubmissionAcceptedResponse,
    SubmissionCreateRequest,
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

    挙動（R1-4）：
      - 対象問題の存在確認（存在しない / soft delete 済みは 404）
      - submissions に 1 行 INSERT（status='pending'）
      - レート制限: 1 ユーザー 1 分 / 20 回まで

    R1-5 で追加する挙動：
      - 同一トランザクション内で jobs に 1 行 INSERT + NOTIFY new_job
      - GET /api/submissions/:id でポーリング、status が graded / failed へ遷移
    """
    del request, response
    service = SubmissionService(db_session)
    return await service.submit_answer(
        user_id=user.id,
        problem_id=body.problem_id,
        code=body.code,
    )
