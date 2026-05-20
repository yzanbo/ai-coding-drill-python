# Alembic autogenerate が全モデルを拾えるよう、ここで re-export する。
# 新規モデルを apps/api/app/models/<name>.py に追加したら、
# 必ず本ファイルにも import を追加すること（追加し忘れるとマイグレーションに乗らない）。

from app.models.auth_providers import AuthProvider
from app.models.generation_requests import GenerationRequest
from app.models.health_check import HealthCheck
from app.models.jobs import Job
from app.models.problems import Problem
from app.models.users import User

__all__ = [
    "AuthProvider",
    "GenerationRequest",
    "HealthCheck",
    "Job",
    "Problem",
    "User",
]
