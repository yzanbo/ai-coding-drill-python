# services/problem_generation.ProblemGenerationService のユニットテスト。
#
# テスト方針（ADR 0044）：
#   - GenerationRequestRepository / JobRepository は AsyncMock でスタブ化
#   - DB セッションは MagicMock（async with session.begin() を素通り）
#   - LLM 呼び出しは Service には無い（Worker 側、ADR 0040）ためモック不要
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md §API / §JSON 例
#   - docs/adr/0044-backend-repository-pattern-adoption.md

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import GenerationRequestNotFoundError
from app.models.generation_requests import GenerationRequest
from app.models.jobs import Job
from app.schemas.problems import (
    GenerationStatus,
    ProblemCategory,
    ProblemDifficulty,
)
from app.services.problem_generation import ProblemGenerationService


# mock_session: DB セッションのモック。
#   ProblemGenerationService は ADR 0044 規約どおり
#   `async with session.begin():` でトランザクション境界を握る。
#   session.begin() は同期で context manager を返す API のため MagicMock 側に置き、
#   返ってきた context manager の __aenter__ / __aexit__ は awaitable で
#   あってほしいので AsyncMock を入れる（test_auth_service.py と同じ）。
@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=None)
    cm.__aexit__ = AsyncMock(return_value=None)
    session.begin.return_value = cm
    return session


@pytest.fixture
def mock_requests_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_jobs_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    mock_session: MagicMock,
    mock_requests_repo: AsyncMock,
    mock_jobs_repo: AsyncMock,
) -> ProblemGenerationService:
    # 通常の生成 → 内部の Repository を AsyncMock 版に差し替えてビジネスロジックだけ観察する。
    s = ProblemGenerationService(mock_session)
    s.requests = mock_requests_repo  # type: ignore[assignment]
    s.jobs = mock_jobs_repo  # type: ignore[assignment]
    # me_repo は get_status 内で failed 行の attempt_errors フェッチに使う。
    # 既定で空辞書を返す AsyncMock に差し替えて SQL 発行を抑止する。
    me_repo_mock = AsyncMock()
    me_repo_mock.fetch_attempt_errors.return_value = {}
    s.me_repo = me_repo_mock  # type: ignore[assignment]
    return s


def _make_generation_request(
    *,
    request_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    status: str = "pending",
    produced_problem_id: uuid.UUID | None = None,
    category: str = "array",
    difficulty: str = "easy",
) -> GenerationRequest:
    """ORM オブジェクトを最小フィールドで組み立てる（実 DB を経由しない）。"""
    gr = GenerationRequest(
        user_id=user_id or uuid.uuid4(),
        category=category,
        difficulty=difficulty,
    )
    gr.id = request_id or uuid.uuid4()
    gr.status = status
    gr.produced_problem_id = produced_problem_id
    return gr


def _make_job(job_id: int = 1) -> Job:
    j = Job(queue="generation", type="problem.generate", payload={})
    j.id = job_id
    return j


class TestEnqueueGeneration:
    async def test_正常系_generation_requestsとjobsの両方に書き込み202レスポンスを返す(
        self,
        service: ProblemGenerationService,
        mock_requests_repo: AsyncMock,
        mock_jobs_repo: AsyncMock,
    ) -> None:
        user_id = uuid.uuid4()
        new_gr = _make_generation_request(user_id=user_id)
        mock_requests_repo.create.return_value = new_gr
        mock_jobs_repo.enqueue.return_value = _make_job(job_id=42)

        result = await service.enqueue_generation(
            user_id=user_id,
            category=ProblemCategory.ARRAY,
            difficulty=ProblemDifficulty.EASY,
        )

        # generation_requests.create が user_id / category / difficulty を文字列で受け取る。
        mock_requests_repo.create.assert_called_once_with(
            user_id=user_id,
            category="array",
            difficulty="easy",
            retry_of=None,
        )

        # jobs.enqueue が generation キュー + problem.generate type で呼ばれる。
        mock_jobs_repo.enqueue.assert_called_once()
        kwargs = mock_jobs_repo.enqueue.call_args.kwargs
        assert kwargs["queue"] == "generation"
        assert kwargs["type_"] == "problem.generate"

        # payload は dict で、必要キーが camelCase で詰まっている（JSON 経由で Worker に渡るため）。
        payload = kwargs["payload"]
        assert payload["generationRequestId"] == str(new_gr.id)
        assert payload["userId"] == str(user_id)
        assert payload["category"] == "array"
        assert payload["difficulty"] == "easy"
        # trace_context は ADR 0010 で必須。R1 期間は traceparent=None で送る契約。
        assert "traceContext" in payload
        assert payload["traceContext"]["traceparent"] is None
        assert payload["traceContext"]["tracestate"] == ""

        # 返り値は 202 用の Pydantic で、request_id が新規 generation_request の id。
        assert result.request_id == new_gr.id
        assert result.status is GenerationStatus.PENDING

    async def test_正常系_カテゴリと難易度の組み合わせがそのまま渡る(
        self,
        service: ProblemGenerationService,
        mock_requests_repo: AsyncMock,
        mock_jobs_repo: AsyncMock,
    ) -> None:
        """Enum → DB 文字列 / payload Enum の対応がずれないことを別組み合わせでも確認。"""
        user_id = uuid.uuid4()
        mock_requests_repo.create.return_value = _make_generation_request(
            user_id=user_id, category="type-puzzle", difficulty="hard"
        )
        mock_jobs_repo.enqueue.return_value = _make_job()

        await service.enqueue_generation(
            user_id=user_id,
            category=ProblemCategory.TYPE_PUZZLE,
            difficulty=ProblemDifficulty.HARD,
        )

        mock_requests_repo.create.assert_called_once_with(
            user_id=user_id,
            category="type-puzzle",
            difficulty="hard",
            retry_of=None,
        )
        payload = mock_jobs_repo.enqueue.call_args.kwargs["payload"]
        assert payload["category"] == "type-puzzle"
        assert payload["difficulty"] == "hard"

    async def test_正常系_INSERTとNOTIFYは1つのbeginブロックに収まる(
        self,
        service: ProblemGenerationService,
        mock_session: MagicMock,
        mock_requests_repo: AsyncMock,
        mock_jobs_repo: AsyncMock,
    ) -> None:
        """ADR 0044 / 0004：Service が明示 begin で tx 境界を握る契約。

        deps/auth.py の get_current_user_optional が認証 SELECT 用の短命 tx を
        commit で閉じておくので、Service は ADR 0044 規約どおり
        `async with session.begin():` を呼べる前提（pre-auth / post-auth で
        挙動を分けなくて済む設計）。generation_requests INSERT + jobs INSERT +
        NOTIFY を 1 つの tx に収める契約は ADR 0004。
        """
        mock_requests_repo.create.return_value = _make_generation_request()
        mock_jobs_repo.enqueue.return_value = _make_job()

        await service.enqueue_generation(
            user_id=uuid.uuid4(),
            category=ProblemCategory.STRING,
            difficulty=ProblemDifficulty.MEDIUM,
        )

        # session.begin() が 1 回だけ呼ばれている（INSERT × 2 + NOTIFY が
        # 1 つの context manager 配下に集約されている契約）。
        mock_session.begin.assert_called_once_with()


class TestGetStatus:
    async def test_正常系_pendingならproblem_idはNoneのまま返る(
        self,
        service: ProblemGenerationService,
        mock_requests_repo: AsyncMock,
    ) -> None:
        user_id = uuid.uuid4()
        request_id = uuid.uuid4()
        # produced_problem_id が埋まっていても pending 中は出さない契約。
        gr = _make_generation_request(
            request_id=request_id,
            user_id=user_id,
            status="pending",
            produced_problem_id=uuid.uuid4(),
        )
        mock_requests_repo.get_by_id_for_user.return_value = gr

        res = await service.get_status(user_id=user_id, request_id=request_id)

        mock_requests_repo.get_by_id_for_user.assert_called_once_with(
            request_id=request_id,
            user_id=user_id,
        )
        assert res.request_id == request_id
        assert res.status is GenerationStatus.PENDING
        # pending 中は produced_problem_id を返さない（completed まで隠す）。
        assert res.problem_id is None

    async def test_正常系_completedなら同梱されたproblem_idがそのまま返る(
        self,
        service: ProblemGenerationService,
        mock_requests_repo: AsyncMock,
    ) -> None:
        user_id = uuid.uuid4()
        request_id = uuid.uuid4()
        problem_id = uuid.uuid4()
        gr = _make_generation_request(
            request_id=request_id,
            user_id=user_id,
            status="completed",
            produced_problem_id=problem_id,
        )
        mock_requests_repo.get_by_id_for_user.return_value = gr

        res = await service.get_status(user_id=user_id, request_id=request_id)

        assert res.status is GenerationStatus.COMPLETED
        assert res.problem_id == problem_id

    async def test_正常系_failedならproblem_idはNoneで返る(
        self,
        service: ProblemGenerationService,
        mock_requests_repo: AsyncMock,
    ) -> None:
        user_id = uuid.uuid4()
        request_id = uuid.uuid4()
        gr = _make_generation_request(
            request_id=request_id,
            user_id=user_id,
            status="failed",
            produced_problem_id=None,
        )
        mock_requests_repo.get_by_id_for_user.return_value = gr

        res = await service.get_status(user_id=user_id, request_id=request_id)

        assert res.status is GenerationStatus.FAILED
        assert res.problem_id is None

    async def test_異常系_他人または存在しないIDならGenerationRequestNotFoundError(
        self,
        service: ProblemGenerationService,
        mock_requests_repo: AsyncMock,
    ) -> None:
        """Repository が None を返す＝「自分のものとして存在しない」契約（情報漏洩防止）。"""
        mock_requests_repo.get_by_id_for_user.return_value = None

        with pytest.raises(GenerationRequestNotFoundError):
            await service.get_status(user_id=uuid.uuid4(), request_id=uuid.uuid4())

    async def test_異常系_DBに想定外のstatus文字列が入っているとValueError(
        self,
        service: ProblemGenerationService,
        mock_requests_repo: AsyncMock,
    ) -> None:
        """CHECK 制約を張らない代わりに Enum 変換で気付く設計（services/problem_generation.py）。"""
        gr = _make_generation_request(status="rate_limited")
        mock_requests_repo.get_by_id_for_user.return_value = gr

        with pytest.raises(ValueError):
            await service.get_status(user_id=gr.user_id, request_id=gr.id)
