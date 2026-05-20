# このファイルの役割：
#   問題ドメインの APIRouter。R1-3 時点では問題生成リクエストの 2 エンドポイントを持つ。
#
#   - POST /problems/generate              : 生成リクエストの enqueue（202 即返）
#   - GET  /problems/generate/:requestId   : 生成ステータス取得（ポーリング用）
#
#   LLM 呼び出しは Worker 側に閉じる（ADR 0040）ため、本 Router は
#   「DB に行を作って NOTIFY を撃つ」「DB から状態を引いて返す」だけ。
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md §API

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.deps.auth import get_current_user
from app.models.users import User
from app.schemas.problems import (
    ProblemGenerateAcceptedResponse,
    ProblemGenerateRequest,
    ProblemGenerateStatusResponse,
)
from app.services.problem_generation import (
    GenerationRequestNotFoundError,
    ProblemGenerationService,
)

# APIRouter: URL をグループ単位でまとめる箱。
# 認証は各エンドポイントの `user: CurrentUser` 引数で必須化する。
# router-level の dependencies=[Depends(get_current_user)] は付けない：
#   - 関数引数で user.id を使うため必ず CurrentUser を受け取る作り
#   - router-level と関数引数の両方に並ぶと「2 段ガード」と誤読される
#   - 既存 auth router（routers/auth.py）も router-level dep を持たない統一感
# tags: Swagger UI のグルーピング表示。
router = APIRouter(
    prefix="/problems",
    tags=["problems"],
)

# DI エイリアス。Annotated + Depends を毎回書くと冗長なのでまとめる。
DbDep = Annotated[AsyncSession, Depends(get_async_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]


# ----------------------------------------------------------------------------
# POST /problems/generate : 生成リクエストの受付（202 + requestId 即返）
# ----------------------------------------------------------------------------
@router.post(
    "/generate",
    response_model=ProblemGenerateAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_problem_generation(
    body: ProblemGenerateRequest,
    db_session: DbDep,
    user: CurrentUser,
) -> ProblemGenerateAcceptedResponse:
    """カテゴリ・難易度を受け取って生成ジョブを enqueue する。

    挙動：
      - generation_requests へ 1 行 INSERT（status='pending'）
      - jobs へ 1 行 INSERT + NOTIFY new_job を同一トランザクションで実行
      - 202 で requestId を返す。実際の生成は Worker が非同期で処理する
    """
    service = ProblemGenerationService(db_session)
    return await service.enqueue_generation(
        user_id=user.id,
        category=body.category,
        difficulty=body.difficulty,
    )


# ----------------------------------------------------------------------------
# GET /problems/generate/:requestId : 生成ステータス取得（ポーリング）
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
    service = ProblemGenerationService(db_session)
    try:
        return await service.get_status(
            user_id=user.id,
            request_id=request_id,
        )
    except GenerationRequestNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="指定された生成リクエストが見つかりません",
        ) from exc
