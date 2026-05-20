# SubmissionService: 解答送信ドメインのビジネスロジック層（ADR 0044）。
#
#   - submit_answer    : 解答受付 → submissions INSERT + jobs INSERT + NOTIFY（R1-5 で
#                        ジョブ enqueue を載せた）
#   - get_submission   : GET /api/submissions/:id 用に 1 件取得（ownership 込み）
#   - list_submissions : GET /api/submissions 用に自分の履歴をページングで返す
#
#   submissions テーブルの UPDATE（status='graded' / 'failed' への遷移）は Worker
#   （apps/workers/grading）責務で本 Service からは書き込まない。
#
# 関わる要件：
#   - docs/requirements/4-features/grading.md §API

import logging
import math
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ProblemNotFoundError, SubmissionNotFoundError
from app.repositories.jobs import JobRepository
from app.repositories.problems import ProblemRepository
from app.repositories.submissions import SubmissionRepository
from app.schemas.jobs.common import TraceContext
from app.schemas.jobs.grading import GradingJobPayload
from app.schemas.submissions import (
    SubmissionAcceptedResponse,
    SubmissionResultPayload,
    SubmissionsListResponse,
    SubmissionStatus,
    SubmissionStatusResponse,
    SubmissionSummary,
)

logger = logging.getLogger(__name__)

# ジョブキュー名 / タイプ識別子。
#   queue : 採点 Worker が LISTEN する論理キュー名（Worker 側の
#           apps/workers/grading/internal/job/types.go GradingQueue と一致）。
#   type  : 1 ジョブのスキーマを識別する文字列。Worker 側 switch の case と一致。
_JOB_QUEUE = "grading"
_JOB_TYPE = "submission.grade"


class SubmissionService:
    """解答送信サービス。

    - 1 リクエストにつき 1 インスタンス生成
    - 引数の db_session を保持して Repository を組み立てる
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self.submissions = SubmissionRepository(db_session)
        self.problems = ProblemRepository(db_session)
        self.jobs = JobRepository(db_session)

    async def submit_answer(
        self,
        *,
        user_id: UUID,
        problem_id: UUID,
        code: str,
    ) -> SubmissionAcceptedResponse:
        """解答を受け付けて採点ジョブを enqueue する。

        振る舞い：
          1. 対象 problem が生きていることを確認（存在しない / soft delete 済みは 404）
          2. submissions に 1 行 INSERT（status='pending'、Repository 側で flush）
          3. 採点ジョブ payload を組み立て（W3C Trace Context を埋める、ADR 0010）
          4. jobs に 1 行 INSERT + NOTIFY new_job を同一トランザクション内で実行
          5. 202 用 Pydantic を返す
        """
        async with self.db_session.begin():
            # 対象問題の存在確認。Worker が後段で読み出しに失敗するより前に弾く。
            problem = await self.problems.get_by_id(problem_id=problem_id)
            if problem is None:
                raise ProblemNotFoundError

            submission = await self.submissions.create(
                user_id=user_id,
                problem_id=problem_id,
                code=code,
            )

            # W3C Trace Context（ADR 0010）を payload に埋める箱。
            #   OTel SDK 未導入（R4「観測性」で組み込み予定）のため、traceparent は
            #   None（= 親なし）で送り、Worker は None を受けたら新規 root span を
            #   発行する設計にしておく。R4 で opentelemetry.propagate.inject を呼んで
            #   実値を詰める形に差し替える。
            #   空文字を sentinel に使わないのは W3C 仕様で無効書式となり、
            #   「無効値」と「未指定」を将来パーサで区別できなくなるため。
            trace_context = TraceContext(traceparent=None, tracestate="")

            payload = GradingJobPayload(
                submission_id=submission.id,
                user_id=user_id,
                problem_id=problem_id,
                code=code,
                trace_context=trace_context,
            )

            # mode="json": UUID / Enum を JSON 互換の str に直して JSONB に詰める。
            # by_alias=True: snake_case 属性 → camelCase キーで書き出す
            #                （Worker 側 Go struct の JSON タグと整合）。
            job = await self.jobs.enqueue(
                queue=_JOB_QUEUE,
                type_=_JOB_TYPE,
                payload=payload.model_dump(mode="json", by_alias=True),
            )

        # ログには user_id / problem_id / submission_id / job_id を残す
        # （Worker 側ログとの突合キーになる）。payload は冗長なので残さない。
        logger.info(
            "Submission accepted: user_id=%s problem_id=%s submission_id=%s job_id=%s",
            user_id,
            problem_id,
            submission.id,
            job.id,
        )

        return SubmissionAcceptedResponse(submission_id=submission.id)

    async def get_submission(
        self,
        *,
        user_id: UUID,
        submission_id: UUID,
    ) -> SubmissionStatusResponse:
        """採点状態 + 結果を返す（ポーリング用）。

        - 自分（user_id）の submission でない / 存在しない場合は
          SubmissionNotFoundError を投げる（Router 側で 404）
        - status が 'graded' / 'failed' に達するまで score / result / graded_at は
          None のまま（Worker が UPDATE してから埋まる）
        """
        submission = await self.submissions.get_by_id_for_user(
            submission_id=submission_id,
            user_id=user_id,
        )
        if submission is None:
            raise SubmissionNotFoundError

        # SubmissionStatus(...): DB の status 文字列を Enum に復元する。
        #   Worker は pending / graded / failed しか書かない設計だが、万一 DB に
        #   異常値が入った場合は ValueError になり 500 を返す。ログにキーを残して
        #   運用者が後追いできるようにする（problem_generation 側と同じ方針）。
        try:
            submission_status = SubmissionStatus(submission.status)
        except ValueError:
            logger.error(
                "Unknown submissions.status detected: submission_id=%s user_id=%s status=%r",
                submission.id,
                user_id,
                submission.status,
            )
            raise

        # result JSONB → Pydantic 詰め替え。
        #   Worker が書き込む形は SubmissionResultPayload と一致させる契約。
        #   pending の間は NULL、Pydantic 側でそのまま None として返す。
        result_payload: SubmissionResultPayload | None = None
        if submission.result is not None:
            result_payload = SubmissionResultPayload.model_validate(submission.result)

        # total_count: result.testResults の件数を返す（Worker が書き込んだ
        # テストケース総数）。pending の間や result 未書き込み時は None。
        total_count = (
            len(result_payload.test_results) if result_payload is not None else None
        )

        return SubmissionStatusResponse(
            id=submission.id,
            problem_id=submission.problem_id,
            status=submission_status,
            score=submission.score,
            total_count=total_count,
            result=result_payload,
            graded_at=submission.graded_at,
        )

    async def list_submissions(
        self,
        *,
        user_id: UUID,
        page: int,
        page_size: int,
    ) -> SubmissionsListResponse:
        """自分の解答履歴をページングで返す。

        並び順は created_at DESC（Repository 側で固定）。
        problem_title は problems JOIN で取得。
        """
        submissions, total = await self.submissions.list_for_user(
            user_id=user_id,
            page=page,
            page_size=page_size,
        )

        # total_pages: total=0 でも 1 を返す（空ページでもクライアントが
        # 「1/1 ページ」と表示できるため）。math.ceil で切り上げ。
        total_pages = max(1, math.ceil(total / page_size)) if page_size > 0 else 1

        items: list[SubmissionSummary] = []
        for submission in submissions:
            # problem_title: Repository が contains_eager で事前読み込みした
            #   submission.problem から取り出す（追加 SQL は走らない）。
            problem_title = submission.problem.title
            # result.testResults の件数を total_count として詰める（GET /:id と同じ規約）。
            total_count: int | None = None
            if submission.result is not None:
                # JSONB は dict として返るので testResults キーを直接参照。
                test_results = submission.result.get("testResults")
                if isinstance(test_results, list):
                    total_count = len(test_results)

            try:
                submission_status = SubmissionStatus(submission.status)
            except ValueError:
                logger.error(
                    "Unknown submissions.status detected (list): submission_id=%s status=%r",
                    submission.id,
                    submission.status,
                )
                raise

            items.append(
                SubmissionSummary(
                    id=submission.id,
                    problem_id=submission.problem_id,
                    problem_title=problem_title,
                    status=submission_status,
                    score=submission.score,
                    total_count=total_count,
                    graded_at=submission.graded_at,
                )
            )

        return SubmissionsListResponse(
            items=items,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
