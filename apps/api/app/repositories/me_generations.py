# MeGenerationsRepository: 問題生成履歴・状態管理ドメイン（R1-7）の SQL 集約層。
#
# ADR 0044：
#   - SQLAlchemy の select / update を呼ぶ実装はここに集約
#   - 戻り値は ORM オブジェクト / プリミティブ（Pydantic 詰め替えは Service）
#   - 認可（user_id 一致チェック）は WHERE 句で行うが、404 への変換は Service
#
# generation_requests への INSERT は既存 GenerationRequestRepository.create が
# 持っているため本 Repository では複製しない（retry 時もそちらを呼ぶ）。

from uuid import UUID

from sqlalchemy import desc, func, select, text
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
        #   PostgreSQL の DISTINCT ON で同じ id のグループから先頭 1 行だけ残す。
        #   DISTINCT ON で指定する式と ORDER BY 先頭の式は完全に同じものを書く
        #   必要があるため、gr_id_expr を 1 度作って使い回す
        #   （.payload[...] を 2 回書くと別物扱いになりエラーになる）。
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

    async def fetch_attempt_errors(
        self,
        *,
        generation_request_ids: list[UUID],
    ) -> dict[UUID, list[dict]]:
        """対応する jobs.attempt_errors JSONB array を取得する（failed 行の試行ごと
        エラー履歴表示用）。

        - fetch_prompt_versions と同じパターンで JOIN 取得（DISTINCT ON で最新 jobs.id）
        - jobs が TTL で消えていれば空配列
        - Service 側で AttemptError に整形して status=='failed' の行だけに詰める
        - 戻り値の型は list[dict]（生の JSONB）。Pydantic 整形は Service 側で行う
          ことで Repository を ORM オブジェクト返却に近い責務（ADR 0044）に保つ
        """
        if not generation_request_ids:
            return {}

        id_strs = [str(i) for i in generation_request_ids]
        gr_id_expr = Job.payload["generationRequestId"].astext
        stmt = (
            select(
                gr_id_expr.label("gr_id"),
                Job.attempt_errors.label("attempt_errors"),
            )
            .where(
                Job.type == "problem.generate",
                gr_id_expr.in_(id_strs),
            )
            .order_by(gr_id_expr, desc(Job.id))
            .distinct(gr_id_expr)
        )
        result = await self.session.execute(stmt)
        out: dict[UUID, list[dict]] = {gid: [] for gid in generation_request_ids}
        for row in result.all():
            try:
                key = UUID(row.gr_id)
            except (ValueError, TypeError):
                continue
            # JSONB は SQLAlchemy が Python list/dict にして返す。
            out[key] = row.attempt_errors or []
        return out

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
