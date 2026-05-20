# ProblemGenerationService: 問題生成ドメインのビジネスロジック層。
#
# ADR 0044：
#   - SQLAlchemy を直接呼ばず Repository に委譲
#   - トランザクション境界（async with session.begin()）はここで握る
#   - ORM → Pydantic への詰め替えもここで行う
#
# 主な責務：
#   1. 認証ユーザーから受け取ったカテゴリ・難易度で generation_requests を INSERT
#   2. 同一トランザクション内で jobs を INSERT + NOTIFY new_job
#   3. ステータス問い合わせは「自分のリクエストか」を必ずチェック
#   4. LLM 呼び出しはここでは行わない（Worker に委譲、ADR 0040）

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import GenerationRequestNotFoundError
from app.repositories.generation_requests import GenerationRequestRepository
from app.repositories.jobs import JobRepository
from app.schemas.jobs.common import TraceContext
from app.schemas.jobs.problem_generation import ProblemGenerationJobPayload
from app.schemas.problems import (
    GenerationStatus,
    ProblemCategory,
    ProblemDifficulty,
    ProblemGenerateAcceptedResponse,
    ProblemGenerateStatusResponse,
)

logger = logging.getLogger(__name__)

# ジョブキュー名 / タイプ識別子。
#   queue   : Worker 側で LISTEN する論理キュー名。R1〜R6 は grading Worker が
#             generation も兼務する想定（ADR 0040）だが、後段で分離する時に
#             ここを切り替えやすいよう定数化しておく。
#   type    : 1 ジョブのスキーマを識別する文字列。Worker 側 switch の case と一致させる。
_JOB_QUEUE = "generation"
_JOB_TYPE = "problem.generate"


class ProblemGenerationService:
    """問題生成リクエストのサービス。

    - 1 リクエストにつき 1 インスタンス生成
    - 引数の db_session を保持して Repository を組み立てる
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self.requests = GenerationRequestRepository(db_session)
        self.jobs = JobRepository(db_session)

    async def enqueue_generation(
        self,
        *,
        user_id: UUID,
        category: ProblemCategory,
        difficulty: ProblemDifficulty,
    ) -> ProblemGenerateAcceptedResponse:
        """生成リクエストを受付けてジョブを enqueue する。

        振る舞い：
          1. generation_requests に 1 行 INSERT（status='pending'）
          2. ジョブ payload を組み立て（W3C Trace Context を埋め込む、ADR 0010）
          3. jobs に 1 行 INSERT + NOTIFY new_job を同一トランザクション内で実行
          4. 202 用の Pydantic を返す
        """
        # トランザクション境界は Service が握る契約（ADR 0044）。
        # ここに到達するまでに get_current_user 依存が同じ session で SELECT を
        # 走らせて autobegin が起きているため、明示的な session.begin() を呼ぶと
        # 「A transaction is already begun on this Session」になる。
        # autobegin で開始済みの暗黙トランザクションをそのまま使い、末尾で
        # commit する形にする（INSERT + INSERT + NOTIFY が 1 つの tx に収まる
        # 契約は維持される、ADR 0004）。例外時は AsyncSessionLocal 終了時に
        # 未 commit 変更が rollback される。
        gr = await self.requests.create(
            user_id=user_id,
            category=category.value,
            difficulty=difficulty.value,
        )

        # W3C Trace Context（ADR 0010）を payload に埋める箱。
        #   現状は OTel SDK 未導入（R4「観測性」で組み込み予定）のため、
        #   traceparent は None（= 親なし）で送り、Worker は None を受けたら
        #   新規 root span を発行する設計にしておく。
        #   R4 で opentelemetry.propagate.inject を呼んで実値を詰める形に差し替える。
        #   空文字を sentinel に使わないのは W3C 仕様で無効書式となり、
        #   「無効値」と「未指定」を将来パーサで区別できなくなるため。
        trace_context = TraceContext(traceparent=None, tracestate="")

        payload = ProblemGenerationJobPayload(
            generation_request_id=gr.id,
            user_id=user_id,
            category=category,
            difficulty=difficulty,
            trace_context=trace_context,
        )

        # mode="json": UUID / Enum を JSON 互換の str に直して JSONB へ詰める。
        # by_alias=True: snake_case 属性 → camelCase キーで書き出す
        #                （Worker 側 Go struct の JSON タグと整合）。
        job = await self.jobs.enqueue(
            queue=_JOB_QUEUE,
            type_=_JOB_TYPE,
            payload=payload.model_dump(mode="json", by_alias=True),
        )

        # commit：generation_requests INSERT + jobs INSERT + NOTIFY を確定する。
        await self.db_session.commit()

        # ログには user_id / request_id / job_id を残す（Worker 側ログとの突合キーになる）。
        # payload は冗長なので残さない。
        logger.info(
            "Problem generation enqueued: user_id=%s request_id=%s job_id=%s "
            "category=%s difficulty=%s",
            user_id,
            gr.id,
            job.id,
            category.value,
            difficulty.value,
        )

        return ProblemGenerateAcceptedResponse(request_id=gr.id)

    async def get_status(
        self,
        *,
        user_id: UUID,
        request_id: UUID,
    ) -> ProblemGenerateStatusResponse:
        """生成リクエストの現在ステータスを返す。

        - 自分（user_id）のリクエストでない / 存在しない場合は
          GenerationRequestNotFoundError を投げる（Router 側で 404）
        - status='completed' の時のみ produced_problem_id を problemId として返す
        """
        gr = await self.requests.get_by_id_for_user(
            request_id=request_id,
            user_id=user_id,
        )
        if gr is None:
            raise GenerationRequestNotFoundError

        # GenerationStatus(...): DB の status 文字列を Enum に復元する。
        #   Worker は pending / completed / failed しか書かない設計（CHECK 制約
        #   を張らない代わりに Pydantic 側 Literal で縛る方針、models/
        #   generation_requests.py docstring 参照）。万一 DB に異常値が入った
        #   場合は ValueError になり 500 を返すが、ログにキーを残して
        #   運用者が後追いできるようにしておく。
        try:
            status = GenerationStatus(gr.status)
        except ValueError:
            logger.error(
                "Unknown generation_requests.status detected: "
                "request_id=%s user_id=%s status=%r",
                gr.id,
                user_id,
                gr.status,
            )
            raise

        return ProblemGenerateStatusResponse(
            request_id=gr.id,
            status=status,
            problem_id=gr.produced_problem_id if status is GenerationStatus.COMPLETED else None,
        )
