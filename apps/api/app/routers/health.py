from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_async_session
from app.models import HealthCheck
from app.schemas.health import HealthCheckResponse

# DB 疎通確認用エンドポイント（DB 往復ありの readiness 相当）。
#
# POST /health: health_check テーブルに 1 行 INSERT し、生成された行を返す
# GET  /health: 直近 10 件を新しい順に返す
# - FastAPI router → SQLAlchemy session → Postgres の経路を end-to-end で 1 周通す疎通用。
# - プロセス生存だけを返す軽量プローブは /healthz（routers/probes.py）が担う。
#   依存込みの readiness を分けることで、DB 一時障害でコンテナ再起動の嵐を引き起こさない。
# - 将来 /readyz（DB + Redis 等を含めた受付可否判定）に役割を移譲する余地を残してある。
#
# 設計判断（Service レイヤ非配置）：
# - health は trivial（INSERT 1 行 / SELECT 1 行）なので、本プロジェクトの単層構成方針
#   （backend.md: Service が AsyncSession を直接呼ぶ）に従いつつ、Service レイヤを切り出さず
#   router 内で SQLAlchemy 操作を直接記述する。実機能（auth / problems / submissions 等）から
#   `app/services/<feature>.py` を導入する運用とする（→ docs/.../02-python.md step 7 設計判断）。

router = APIRouter(prefix="/health", tags=["health"])

# FastAPI の依存性注入は Annotated[T, Depends(...)] 形式で書く（B008 ruff 規約に準拠、
# default 引数で関数呼び出しを行う旧スタイルは禁止）。
SessionDep = Annotated[AsyncSession, Depends(get_async_session)]


@router.post("", response_model=HealthCheckResponse)
async def create_health_check(session: SessionDep) -> HealthCheck:
    """疎通確認用：health_check テーブルに 1 行 INSERT して返す。"""
    record = HealthCheck()
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


@router.get("", response_model=list[HealthCheckResponse])
async def list_health_checks(session: SessionDep) -> list[HealthCheck]:
    """疎通確認用：直近 10 件を新しい順に返す。"""
    stmt = select(HealthCheck).order_by(HealthCheck.created_at.desc()).limit(10)
    result = await session.execute(stmt)
    return list(result.scalars().all())
