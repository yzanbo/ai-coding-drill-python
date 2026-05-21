# MeGenerationsRepository: 問題生成履歴・状態管理ドメイン（R1-7）の SQL 集約層。
#
# ADR 0044：
#   - SQLAlchemy の select / update を呼ぶ実装はここに集約
#   - 戻り値は ORM オブジェクト / プリミティブ（Pydantic 詰め替えは Service）
#   - 認可（user_id 一致チェック）は WHERE 句で行うが、404 への変換は Service
#
# generation_requests への INSERT は既存 GenerationRequestRepository.create が
# 持っているため本 Repository では複製しない（retry 時もそちらを呼ぶ）。

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import desc, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.generation_requests import GenerationRequest
from app.models.jobs import Job


class MeGenerationsRepository:
    """自分の生成リクエスト履歴の読み書きを集約する。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_for_user(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
    ) -> list[GenerationRequest]:
        """自分の generation_requests を created_at DESC で 1 ページ分返す。

        prompt_version は jobs.payload JSONB から別途取得する設計のため、ここでは
        持って来ない（jobs は TTL でハードデリートされうるため LEFT JOIN にしても
        NULL になるケースあり、Service 側で fetch_prompt_versions を別途呼ぶ）。
        """
        stmt = (
            select(GenerationRequest)
            .where(GenerationRequest.user_id == user_id)
            .order_by(desc(GenerationRequest.created_at))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_user(self, *, user_id: UUID) -> int:
        """自分の generation_requests の総件数。totalPages 計算用。"""
        stmt = select(func.count()).select_from(GenerationRequest).where(
            GenerationRequest.user_id == user_id,
        )
        return await self.session.scalar(stmt) or 0

    async def fetch_prompt_versions(
        self,
        *,
        generation_request_ids: list[UUID],
    ) -> dict[UUID, str | None]:
        """対応する jobs.payload から prompt_version を取得する。

        - jobs は type='problem.generate' のもの。payload JSONB に
          generation_request_id（camelCase）と prompt_version（camelCase）を持つ
        - 通常 1 generation_request : 1 jobs。retry は新規 generation_request を
          作る設計のため payload の generationRequestId は 1 対 1
          （MeGenerationsService.retry → enqueue_generation の経路）
        - 上記前提が崩れた場合（重複 INSERT 等の事故）の防御として DISTINCT ON で
          最新 jobs.id を採用する
        - jobs が TTL で消えていれば該当キーは {id: None} を返す
        """
        if not generation_request_ids:
            return {}

        # ids を string にして JSONB の text 比較に使う。Pydantic mode='json' で
        # 詰めた時点で generationRequestId / promptVersion は string になっている。
        id_strs = [str(i) for i in generation_request_ids]

        # 各 generation_request_id ごとに「最新の jobs.id」を一段で取りたい。
        #   PostgreSQL DISTINCT ON でグループ別に最大 id を 1 行に絞る。
        #   DISTINCT ON の式と ORDER BY の先頭式が「同じ文字列」になる必要があるため、
        #   gr_id_expr を 1 度作って使い回す（毎回 .payload[...] を書くと SQLAlchemy が
        #   バインドを別パラメータで出してしまい "must match" エラーになる）。
        gr_id_expr = Job.payload["generationRequestId"].astext
        stmt = (
            select(
                gr_id_expr.label("gr_id"),
                Job.payload["promptVersion"].astext.label("prompt_version"),
            )
            .where(
                Job.type == "problem.generate",
                gr_id_expr.in_(id_strs),
            )
            .order_by(gr_id_expr, desc(Job.id))
            .distinct(gr_id_expr)
        )
        result = await self.session.execute(stmt)
        out: dict[UUID, str | None] = {gid: None for gid in generation_request_ids}
        for row in result.all():
            try:
                key = UUID(row.gr_id)
            except (ValueError, TypeError):
                continue
            out[key] = row.prompt_version
        return out

    async def cancel_pending(
        self,
        *,
        request_id: UUID,
        user_id: UUID,
    ) -> bool:
        """pending の generation_request をキャンセルする。

        振る舞い：
          - 対象 generation_request が「自分 + 現状 pending」の時のみ status='canceled' /
            completed_at=NOW() を書く（race condition で running になっていたら何もしない）
          - 同時に、対応する jobs を state='queued' → 'dead' に更新（Worker が
            SELECT FOR UPDATE SKIP LOCKED で取らないようにする）
          - 戻り値：実際に状態遷移したかどうか（True なら成功、False なら遷移条件不一致）

        Service 側でトランザクション境界を握る前提で、本関数内では commit しない。
        """
        now = datetime.now(UTC)

        # 1) generation_requests: pending → canceled
        gr_stmt = (
            update(GenerationRequest)
            .where(
                GenerationRequest.id == request_id,
                GenerationRequest.user_id == user_id,
                GenerationRequest.status == "pending",
            )
            .values(status="canceled", completed_at=now)
            .returning(GenerationRequest.id)
        )
        gr_result = await self.session.execute(gr_stmt)
        if gr_result.scalar_one_or_none() is None:
            return False

        # 2) jobs: queued → dead（同じ generation_request_id を payload に持つもの）
        #   Worker は state='queued' のみ取るので、'dead' に倒せば取られない。
        #   payload は JSONB なので ->> 'generationRequestId' で text 比較。
        job_stmt = (
            update(Job)
            .where(
                Job.type == "problem.generate",
                Job.state == "queued",
                Job.payload["generationRequestId"].astext == str(request_id),
            )
            .values(state="dead")
        )
        await self.session.execute(job_stmt)
        return True

    async def get_for_user(
        self,
        *,
        request_id: UUID,
        user_id: UUID,
    ) -> GenerationRequest | None:
        """自分の generation_request を主キーで 1 件取得する（cancel / retry 共通）。

        他人のリクエスト ID を渡された場合は None（情報漏洩防止のため、Service 側で
        「他人」と「存在しない」を区別せず 404 に倒す）。
        """
        stmt = select(GenerationRequest).where(
            GenerationRequest.id == request_id,
            GenerationRequest.user_id == user_id,
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def compute_retry_depths(
        self,
        *,
        user_id: UUID,
        request_ids: list[UUID],
    ) -> dict[UUID, int]:
        """与えられた request_ids について、retry_of チェーンを辿った深さを返す。

        - 元リクエスト（retry_of=NULL）は 0
        - 1 段目の retry は 1、その retry は 2 ... と再帰的に数える
        - WITH RECURSIVE CTE で 1 クエリにまとめる（N+1 を避ける）
        - 同じ user_id 配下に限定して再帰させる（他人の行を辿るのを防ぐ）
        """
        if not request_ids:
            return {}

        sql = text(
            """
            WITH RECURSIVE chain AS (
              SELECT id, retry_of, 0 AS depth
                FROM generation_requests
               WHERE user_id = :user_id
                 AND id = ANY(:ids)
              UNION ALL
              SELECT chain.id, gr.retry_of, chain.depth + 1
                FROM chain
                JOIN generation_requests gr
                  ON gr.id = chain.retry_of
               WHERE gr.user_id = :user_id
            )
            SELECT id, MAX(depth) AS depth
              FROM chain
             GROUP BY id
            """
        )
        result = await self.session.execute(
            sql, {"user_id": user_id, "ids": list(request_ids)}
        )
        out: dict[UUID, int] = {rid: 0 for rid in request_ids}
        for row in result.all():
            out[row.id] = int(row.depth)
        return out
