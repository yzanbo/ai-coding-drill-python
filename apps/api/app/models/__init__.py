# Alembic autogenerate が全モデルを拾えるよう、ここで re-export する。
# 新規モデルを apps/api/app/models/<name>.py に追加したら、
# 必ず本ファイルにも import を追加すること（追加し忘れるとマイグレーションに乗らない）。

from app.models.health_check import HealthCheck

__all__ = ["HealthCheck"]
