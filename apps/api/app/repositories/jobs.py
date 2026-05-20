# JobRepository: jobs テーブルへの SQL と NOTIFY 発行を集約する層。
#
# ADR 0044 の方針：
#   - SQLAlchemy の insert / NOTIFY を呼ぶ実装はここに集約
#   - 戻り値は ORM オブジェクト（Pydantic への詰め替えは Service）
#   - トランザクション境界は持たない（Service 側で `async with session.begin():`）
#
# 関連：
#   - docs/adr/0004-postgres-as-job-queue.md（Postgres ジョブキュー採用）
#   - docs/adr/0046-job-queue-delivery-guarantees.md（配送保証契約）

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.jobs import Job


class JobRepository:
    """jobs テーブルへの enqueue を集約する。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def enqueue(
        self,
        *,
        queue: str,
        type_: str,
        payload: dict[str, Any],
    ) -> Job:
        """新規ジョブを 1 行 INSERT して、id が埋まった ORM を返す。

        加えて、同一トランザクション内で NOTIFY を発行する（ADR 0004）。
          - NOTIFY 自体は best-effort なレイテンシ最適化
          - 配送保証の本体は 30 秒ポーリング側（ADR 0046）

        commit はしない（Service 側）。
        """
        job = Job(
            queue=queue,
            type=type_,
            payload=payload,
        )
        self.session.add(job)
        # flush: ここで INSERT が走って id（BIGSERIAL）が確定する。
        #        NOTIFY ペイロードに id を載せたいので flush 必須。
        await self.session.flush()

        # NOTIFY new_job, '<job_id>':
        #   Worker 側が LISTEN new_job しており、ペイロード文字列で job_id が通知される。
        #   Postgres の NOTIFY は payload を文字列「リテラル」でしか受け付けず、
        #   prepared statement のパラメータバインド ($1) を許可しない仕様
        #   （NOTIFY new_job, $1 は syntax error になる）。
        #   そのため文字列補間でクエリを組み立てる。job.id は BIGSERIAL なので int 化
        #   した上で str() に通せばインジェクション余地は無い（数字以外混入し得ない）。
        job_id = int(job.id)
        await self.session.execute(text(f"NOTIFY new_job, '{job_id}'"))
        return job
