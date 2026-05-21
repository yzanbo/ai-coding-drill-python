# MeGenerationsService の単体テスト（ADR 0044）。
#
# テスト方針：
#   - Repository を AsyncMock でスタブし、Service のビジネスロジック分岐を検証
#   - 観測対象：list_history の詰め替え、cancel / retry の状態ガード（404 / 409）
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md §履歴・状態管理

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import (
    GenerationRequestNotCancelableError,
    GenerationRequestNotFoundError,
    GenerationRequestNotRetryableError,
)
from app.schemas.me_generations import GenerationRequestSummary
from app.services.me_generations import MeGenerationsService


@pytest.fixture
def mock_session() -> MagicMock:
    # session.begin() は cancel が使うため、コンテキストマネージャを偽装する。
    sm = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=None)
    cm.__aexit__ = AsyncMock(return_value=None)
    sm.begin = MagicMock(return_value=cm)
    return sm


@pytest.fixture
def mock_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_generation() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    mock_session: MagicMock,
    mock_repo: AsyncMock,
    mock_generation: AsyncMock,
) -> MeGenerationsService:
    s = MeGenerationsService(mock_session)
    s.repo = mock_repo  # type: ignore[assignment]
    s.generation = mock_generation  # type: ignore[assignment]
    return s


def _gr(
    *,
    status: str = "completed",
    retry_of: uuid.UUID | None = None,
    produced: uuid.UUID | None = None,
    failure_reason: str | None = None,
    completed_at: datetime | None = None,
) -> SimpleNamespace:
    """ORM の代わりに使うダックタイプ。"""
    return SimpleNamespace(
        id=uuid.uuid4(),
        category="array",
        difficulty="easy",
        status=status,
        produced_problem_id=produced,
        retry_of=retry_of,
        failure_reason=failure_reason,
        created_at=datetime.now(UTC),
        completed_at=completed_at,
    )


class TestListHistory:
    async def test_正常系_履歴ゼロは空items_totalPages0(
        self, service: MeGenerationsService, mock_repo: AsyncMock
    ) -> None:
        mock_repo.list_for_user.return_value = []
        mock_repo.count_for_user.return_value = 0
        mock_repo.fetch_prompt_versions.return_value = {}
        mock_repo.compute_retry_depths.return_value = {}

        res = await service.list_history(user_id=uuid.uuid4(), page=1)

        assert res.items == []
        assert res.total_pages == 0
        assert res.page == 1

    async def test_正常系_prompt_version_retry_count_が詰め替えられる(
        self, service: MeGenerationsService, mock_repo: AsyncMock
    ) -> None:
        gr1 = _gr(status="completed", produced=uuid.uuid4(), completed_at=datetime.now(UTC))
        gr2 = _gr(status="failed", failure_reason="judge_below_threshold")
        mock_repo.list_for_user.return_value = [gr1, gr2]
        mock_repo.count_for_user.return_value = 2
        mock_repo.fetch_prompt_versions.return_value = {gr1.id: "v1", gr2.id: None}
        mock_repo.compute_retry_depths.return_value = {gr1.id: 0, gr2.id: 2}

        res = await service.list_history(user_id=uuid.uuid4(), page=1)

        assert len(res.items) == 2
        assert isinstance(res.items[0], GenerationRequestSummary)
        assert res.items[0].prompt_version == "v1"
        assert res.items[0].retry_count == 0
        assert res.items[1].prompt_version is None
        assert res.items[1].retry_count == 2
        assert res.items[1].failure_reason == "judge_below_threshold"

    async def test_境界値_total25_pageSize20_でtotalPages2(
        self, service: MeGenerationsService, mock_repo: AsyncMock
    ) -> None:
        mock_repo.list_for_user.return_value = []
        mock_repo.count_for_user.return_value = 25
        mock_repo.fetch_prompt_versions.return_value = {}
        mock_repo.compute_retry_depths.return_value = {}

        res = await service.list_history(user_id=uuid.uuid4(), page=1)
        assert res.total_pages == 2


class TestCancel:
    async def test_異常系_存在しない_他人なら404(
        self, service: MeGenerationsService, mock_repo: AsyncMock
    ) -> None:
        mock_repo.get_for_user.return_value = None
        with pytest.raises(GenerationRequestNotFoundError):
            await service.cancel(user_id=uuid.uuid4(), request_id=uuid.uuid4())

    @pytest.mark.parametrize("status", ["completed", "failed", "canceled"])
    async def test_異常系_pending以外は409(
        self, service: MeGenerationsService, status: str, mock_repo: AsyncMock
    ) -> None:
        mock_repo.get_for_user.return_value = _gr(status=status)
        with pytest.raises(GenerationRequestNotCancelableError) as ei:
            await service.cancel(user_id=uuid.uuid4(), request_id=uuid.uuid4())
        assert ei.value.current_status == status

    async def test_正常系_pending_を_canceled_に倒す(
        self, service: MeGenerationsService, mock_repo: AsyncMock
    ) -> None:
        mock_repo.get_for_user.return_value = _gr(status="pending")
        mock_repo.cancel_pending.return_value = True

        req_id = uuid.uuid4()
        res = await service.cancel(user_id=uuid.uuid4(), request_id=req_id)

        assert res.id == req_id
        assert res.status == "canceled"
        mock_repo.cancel_pending.assert_awaited_once()

    async def test_異常系_race_でUPDATEが0行なら409_実状態を返す(
        self, service: MeGenerationsService, mock_repo: AsyncMock
    ) -> None:
        # 取得時点では pending だったが、UPDATE 直前に Worker が completed に進めた。
        # 再 SELECT で取れた実状態（completed）が 409 detail に乗ることを確認。
        mock_repo.get_for_user.side_effect = [
            _gr(status="pending"),    # cancel 本体の SELECT
            _gr(status="completed"),  # race 検知後の再 SELECT
        ]
        mock_repo.cancel_pending.return_value = False
        with pytest.raises(GenerationRequestNotCancelableError) as ei:
            await service.cancel(user_id=uuid.uuid4(), request_id=uuid.uuid4())
        assert ei.value.current_status == "completed"

    async def test_異常系_race_で再SELECTが消えていたらunknown(
        self, service: MeGenerationsService, mock_repo: AsyncMock
    ) -> None:
        # 再 SELECT で None（極端ケース：TTL 削除等）が返った時の保険。
        mock_repo.get_for_user.side_effect = [
            _gr(status="pending"),
            None,
        ]
        mock_repo.cancel_pending.return_value = False
        with pytest.raises(GenerationRequestNotCancelableError) as ei:
            await service.cancel(user_id=uuid.uuid4(), request_id=uuid.uuid4())
        assert ei.value.current_status == "unknown"


class TestRetry:
    async def test_異常系_存在しない_他人なら404(
        self, service: MeGenerationsService, mock_repo: AsyncMock
    ) -> None:
        mock_repo.get_for_user.return_value = None
        with pytest.raises(GenerationRequestNotFoundError):
            await service.retry(user_id=uuid.uuid4(), request_id=uuid.uuid4())

    @pytest.mark.parametrize("status", ["pending", "completed", "canceled"])
    async def test_異常系_failed以外は409(
        self, service: MeGenerationsService, status: str, mock_repo: AsyncMock
    ) -> None:
        mock_repo.get_for_user.return_value = _gr(status=status)
        with pytest.raises(GenerationRequestNotRetryableError) as ei:
            await service.retry(user_id=uuid.uuid4(), request_id=uuid.uuid4())
        assert ei.value.current_status == status

    async def test_正常系_failed_は_enqueue_に_retry_of_を渡して新規作成(
        self, service: MeGenerationsService, mock_repo: AsyncMock, mock_generation: AsyncMock
    ) -> None:
        original = _gr(status="failed")
        mock_repo.get_for_user.return_value = original
        new_id = uuid.uuid4()
        mock_generation.enqueue_generation.return_value = SimpleNamespace(
            request_id=new_id
        )

        res = await service.retry(user_id=uuid.uuid4(), request_id=original.id)

        assert res.id == new_id
        assert res.status == "pending"
        assert res.retry_of == original.id
        # enqueue_generation が retry_of=original.id 付きで呼ばれた
        kwargs = mock_generation.enqueue_generation.await_args.kwargs
        assert kwargs["retry_of"] == original.id
