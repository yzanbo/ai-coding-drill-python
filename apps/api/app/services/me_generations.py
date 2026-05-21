# MeGenerationsService: 問題生成履歴・状態管理（R1-7）のビジネスロジック層（ADR 0044）。
#
#   - list_history : ページネーション付きで自分の generation_requests を返す
#   - cancel       : pending のリクエストをキャンセル（jobs を dead に倒す）
#   - retry        : failed のリクエストを新規 generation_request として複製
#
#   prompt_version は jobs.payload から JOIN 取得、retry_count は WITH RECURSIVE
#   CTE で 1 クエリ取得（N+1 を避ける）。
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md §履歴・状態管理
#   - docs/requirements/4-features/problem-generation.md §API

import logging
import math
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    GenerationRequestNotCancelableError,
    GenerationRequestNotFoundError,
    GenerationRequestNotRetryableError,
)
from app.repositories.me_generations import MeGenerationsRepository
from app.schemas.me_generations import (
    ME_GENERATIONS_PAGE_SIZE,
    AttemptError,
    FailureReasonTag,
    GenerationRequestCancelResponse,
    GenerationRequestRetryResponse,
    GenerationRequestSummary,
    MeGenerationsListResponse,
    ProgressStep,
)
from app.schemas.problems import (
    ProblemCategory,
    ProblemDifficulty,
)
from app.services.problem_generation import ProblemGenerationService

logger = logging.getLogger(__name__)

# _KNOWN_FAILURE_REASONS: Worker が書く想定の失敗理由タグ集合。
#   Worker (apps/workers/grading/internal/grading/problem_generate.go の
#   classifyFailureReason) と 1:1 で揃える。集合に無い値（旧データ / 手動修正）
#   は API レスポンスから除外し、FE 側のデフォルト文言にフォールバックさせる。
_KNOWN_FAILURE_REASONS: frozenset[str] = frozenset(
    [
        "llm_unauthorized",
        "llm_cost_exceeded",
        "judge_below_threshold",
        "sandbox_failed",
        "sandbox_infrastructure",
        "llm_invalid_output",
        "llm_rate_limit",
        "llm_timeout",
        "llm_schema_invalid",
        "max_attempts_exceeded",
    ]
)


def _coerce_failure_reason(raw: str | None) -> FailureReasonTag | None:
    """DB の生 string を FailureReasonTag に絞り込む。想定外値は None。

    failed 以外の状態で値が紛れていた場合 / 旧データの未知タグ / NULL を
    一括で None に倒し、API レスポンスからは除外する。
    """
    if raw is None:
        return None
    if raw in _KNOWN_FAILURE_REASONS:
        return raw  # type: ignore[return-value]
    return None


# _KNOWN_PROGRESS_STEPS: Worker が書く想定のステップ集合。
#   Worker (apps/workers/grading/internal/grading/problem_generate.go の Handle で
#   updateProgressStep が書く 4 値) と 1:1。集合に無い値は API レスポンスから
#   除外し、FE 側でステップ未確定（≒ キュー待ち or 起動直後）の表示にフォールバック。
_KNOWN_PROGRESS_STEPS: frozenset[str] = frozenset(
    [
        "llm_generating",
        "sandbox_verifying",
        "judging",
        "persisting",
    ]
)


def _coerce_progress_step(raw: str | None) -> ProgressStep | None:
    """DB の生 string を ProgressStep に絞り込む。想定外値は None。

    Worker が pending 中に書く 4 タグ以外（旧データ / 手動修正 / 将来追加されたが
    API 側が追従していない値）は除外する。FailureReasonTag と同じ防御線パターン。
    """
    if raw is None:
        return None
    if raw in _KNOWN_PROGRESS_STEPS:
        return raw  # type: ignore[return-value]
    return None


def _coerce_attempt_errors(raw: list[dict] | None) -> list[AttemptError]:
    """jobs.attempt_errors JSONB array を AttemptError のリストに整形する。

    Worker が書く構造は camelCase {attempt, failureReason, message, failedAt} だが、
    Pydantic の populate_by_name + alias_generator=to_camel が両対応するので
    そのまま model_validate に渡せる。想定外値（旧データ / 手動修正）が混じった
    要素は ValidationError で 1 件単位で skip し、他の要素は残す
    （全体を 500 にしたくない、UI 側で見える範囲を最大化する方針）。
    """
    if not raw:
        return []
    out: list[AttemptError] = []
    for elem in raw:
        try:
            out.append(AttemptError.model_validate(elem))
        except Exception:  # noqa: BLE001 - 1 要素の不正で全体を落とさない
            logger.warning("Skipping malformed attempt_error element: %r", elem)
    return out


class MeGenerationsService:
    """問題生成履歴 + キャンセル / 再試行のサービス。

    - 1 リクエストにつき 1 インスタンス生成
    - 再試行は ProblemGenerationService.enqueue_generation を内部で呼ぶ
      （enqueue ロジックの重複実装を避ける、backend.md §services）
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self.repo = MeGenerationsRepository(db_session)
        self.generation = ProblemGenerationService(db_session)

    async def list_history(
        self,
        *,
        user_id: UUID,
        page: int,
    ) -> MeGenerationsListResponse:
        """自分の生成リクエスト履歴を created_at DESC で 1 ページ返す。

        - 履歴ゼロは items=[] / totalPages=0 を返す（404 にはしない）
        - prompt_version は jobs.payload から JOIN 取得、消えていれば None
        - retry_count は WITH RECURSIVE で 1 クエリで取得（N+1 を避ける）
        """
        rows = await self.repo.list_for_user(
            user_id=user_id,
            page=page,
            page_size=ME_GENERATIONS_PAGE_SIZE,
        )
        total = await self.repo.count_for_user(user_id=user_id)
        total_pages = math.ceil(total / ME_GENERATIONS_PAGE_SIZE) if total > 0 else 0

        ids = [r.id for r in rows]
        prompt_versions = await self.repo.fetch_prompt_versions(generation_request_ids=ids)
        retry_depths = await self.repo.compute_retry_depths(
            user_id=user_id,
            request_ids=ids,
        )
        # attempt_errors: failed 行のデバッグ詳細表示用に JOIN 取得（R1-7-3）。
        #   failed 以外の行は本フェッチで取得しても Service 側で空配列に倒すため
        #   実害は無いが、ids を絞ると無駄な JOIN を減らせる。
        failed_ids = [r.id for r in rows if r.status == "failed"]
        attempt_errors_by_id = await self.repo.fetch_attempt_errors(
            generation_request_ids=failed_ids,
        )

        items = [
            GenerationRequestSummary(
                id=r.id,
                category=r.category,
                difficulty=r.difficulty,
                # status: DB の生文字列を Literal にそのまま流す。Pydantic 側で
                #   想定外値は ValidationError になり 500 として観測できる。
                status=r.status,  # type: ignore[arg-type]
                produced_problem_id=r.produced_problem_id,
                prompt_version=prompt_versions.get(r.id),
                retry_of=r.retry_of,
                retry_count=retry_depths.get(r.id, 0),
                # failure_reason: failed 行のみ enum 値を返す。Worker が書く 6 タグ
                #   以外の値（旧データ / 想定外）は _coerce_failure_reason で None に倒す。
                failure_reason=(
                    _coerce_failure_reason(r.failure_reason) if r.status == "failed" else None
                ),
                # progress_step: pending 行のみ enum 値を返す。pending 以外では
                #   ステップ列が NULL でない場合もあるが（古い遷移残り）、API では
                #   None に倒す（ステップ表示は pending 中だけの関心）。
                progress_step=(
                    _coerce_progress_step(r.progress_step) if r.status == "pending" else None
                ),
                # attempt_errors: failed 行のみ各試行のエラー履歴を返す。
                attempt_errors=(
                    _coerce_attempt_errors(attempt_errors_by_id.get(r.id))
                    if r.status == "failed"
                    else []
                ),
                created_at=r.created_at,
                completed_at=r.completed_at,
            )
            for r in rows
        ]
        return MeGenerationsListResponse(
            items=items,
            page=page,
            page_size=ME_GENERATIONS_PAGE_SIZE,
            total_pages=total_pages,
        )

    async def cancel(
        self,
        *,
        user_id: UUID,
        request_id: UUID,
    ) -> GenerationRequestCancelResponse:
        """pending のリクエストをキャンセルする。

        - 自分のものでない / 存在しない → GenerationRequestNotFoundError（404）
        - 自分のものだが pending でない → GenerationRequestNotCancelableError（409）
        - cancel 成功 → status='canceled' で返す
        """
        # SELECT と UPDATE を 1 つのトランザクションにまとめる。
        #   SQLAlchemy は SELECT 時に内部でトランザクションを自動で開くため、
        #   外側で begin() を 2 回開こうとするとエラーになる。最初から
        #   begin() ブロックの中に両方入れて、ブロック終了時に一括 commit する
        #   （途中で例外が出れば自動で rollback）。
        async with self.db_session.begin():
            gr = await self.repo.get_for_user(
                request_id=request_id, user_id=user_id,
            )
            if gr is None:
                raise GenerationRequestNotFoundError
            if gr.status != "pending":
                raise GenerationRequestNotCancelableError(current_status=gr.status)

            transitioned = await self.repo.cancel_pending(
                request_id=request_id,
                user_id=user_id,
            )
            if not transitioned:
                # race: 取得時点では pending だったが、cancel UPDATE 直前に
                # Worker が拾って completed / failed に進めた場合などはここに来る。
                # Worker は pending → completed / failed の 1 ステップ遷移しか書かない
                # ため、実際の current_status を再取得して 409 に乗せる
                # （ハードコードだと FE 側のメッセージが事実と食い違う）。
                refetched = await self.repo.get_for_user(
                    request_id=request_id, user_id=user_id,
                )
                actual = refetched.status if refetched is not None else "unknown"
                raise GenerationRequestNotCancelableError(current_status=actual)

        logger.info(
            "Generation request canceled: user_id=%s request_id=%s",
            user_id,
            request_id,
        )
        return GenerationRequestCancelResponse(id=request_id, status="canceled")

    async def retry(
        self,
        *,
        user_id: UUID,
        request_id: UUID,
    ) -> GenerationRequestRetryResponse:
        """failed のリクエストを再試行する（新規 generation_request として複製）。

        - 自分のものでない / 存在しない → GenerationRequestNotFoundError（404）
        - 自分のものだが failed でない → GenerationRequestNotRetryableError（409）
        - retry 成功 → 新規 generation_request の id + retry_of で返す

        ## 冪等性について
        本エンドポイントは冪等保証なし。同一 request_id への 2 回の呼び出しは
        2 つの新規 generation_request を生み、いずれも有効な pending として
        enqueue される。多重 retry の防御は以下に依存：
          - FE 側のボタン isPending 抑止（連打防止）
          - enqueue_generation の rate limit（1 分 5 回、要件 §ビジネスルール）
        将来 idempotency-key 受け取りに拡張する場合は API 仕様変更を伴うため、
        本実装は MVP 範囲として「rate limit が backstop」前提に留める。
        """
        # SELECT 部分を独立したトランザクションにまとめて commit までやってしまう。
        #   SQLAlchemy は SELECT 時にも内部でトランザクションを自動で開くため、
        #   ここで明示的に begin() で囲って閉じておかないと、後段で呼ぶ
        #   enqueue_generation が自前で begin() を開いた時に「もう開いてる」と
        #   エラーになる。
        async with self.db_session.begin():
            original = await self.repo.get_for_user(
                request_id=request_id, user_id=user_id,
            )
            if original is None:
                raise GenerationRequestNotFoundError
            if original.status != "failed":
                raise GenerationRequestNotRetryableError(
                    current_status=original.status,
                )
            # 後段で使う値を ORM 切り離し前に primitive に取り出しておく
            # （session 抜けた後の lazy load を避ける）。
            original_id = original.id
            original_category = original.category
            original_difficulty = original.difficulty

        # 既存 enqueue ロジックに retry_of を渡して再利用する。
        accepted = await self.generation.enqueue_generation(
            user_id=user_id,
            category=ProblemCategory(original_category),
            difficulty=ProblemDifficulty(original_difficulty),
            retry_of=original_id,
        )
        return GenerationRequestRetryResponse(
            id=accepted.request_id,
            status="pending",
            retry_of=original_id,
        )
