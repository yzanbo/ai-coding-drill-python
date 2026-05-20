# services/me.MeService のユニットテスト（ADR 0044）。
#
# テスト方針：
#   - MeRepository を AsyncMock でスタブ化し、Service のビジネスロジックを
#     SQLAlchemy 依存なしに検証する
#   - 観測対象は accuracy 計算 / 弱点抽出のしきい値 / 並び順 / Pydantic 詰め替え
#
# 関わる要件：
#   - docs/requirements/4-features/learning.md §API §ビジネスルール
#   - docs/adr/0044-backend-repository-pattern-adoption.md

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.repositories.me import CategoryAggregate
from app.schemas.me import (
    ME_WEAKNESS_ACCURACY_THRESHOLD,
    ME_WEAKNESS_MIN_ATTEMPTS,
    ME_WEAKNESS_TOP_N,
)
from app.services.me import MeService


@pytest.fixture
def mock_session() -> MagicMock:
    # MeService は session.begin() を使わない（読み取り専用）。
    # それでも AsyncSession 互換のオブジェクトとして MagicMock を渡す。
    return MagicMock()


@pytest.fixture
def mock_me_repo() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(mock_session: MagicMock, mock_me_repo: AsyncMock) -> MeService:
    s = MeService(mock_session)
    s.me = mock_me_repo  # type: ignore[assignment]
    return s


class TestGetStats:
    async def test_正常系_カテゴリ別集計から_total_correct_accuracy_が計算される(
        self,
        service: MeService,
        mock_me_repo: AsyncMock,
    ) -> None:
        user_id = uuid.uuid4()
        # Repository は category ASC で並べて返す契約。
        mock_me_repo.aggregate_by_category.return_value = [
            CategoryAggregate(category="array", attempts=10, correct=8),
            CategoryAggregate(category="recursion", attempts=5, correct=1),
        ]

        res = await service.get_stats(user_id=user_id)

        mock_me_repo.aggregate_by_category.assert_called_once_with(user_id=user_id)
        # total / correct は全カテゴリ合算。
        assert res.total == 15
        assert res.correct == 9
        # accuracy = 9 / 15 = 0.6（浮動小数なので近似で比較）。
        assert res.accuracy == pytest.approx(0.6)
        # byCategory は Repository が返した順をそのまま採用、accuracy を付与。
        assert len(res.by_category) == 2
        assert res.by_category[0].category == "array"
        assert res.by_category[0].accuracy == pytest.approx(0.8)
        assert res.by_category[1].category == "recursion"
        assert res.by_category[1].accuracy == pytest.approx(0.2)

    async def test_正常系_履歴ゼロのユーザーは200相当で_total_0_accuracy_0_byCategory空(
        self,
        service: MeService,
        mock_me_repo: AsyncMock,
    ) -> None:
        # 履歴ゼロ：Repository は空配列を返す（learning.md §受け入れ条件）。
        mock_me_repo.aggregate_by_category.return_value = []

        res = await service.get_stats(user_id=uuid.uuid4())

        # ゼロ割を起こさず 0.0 を返す契約。404 ではなく 200 で空集計。
        assert res.total == 0
        assert res.correct == 0
        assert res.accuracy == 0.0
        assert res.by_category == []

    async def test_正常系_attempts0のカテゴリは現れないがaccuracy0でも詰め替えできる(
        self,
        service: MeService,
        mock_me_repo: AsyncMock,
    ) -> None:
        # Repository は GROUP BY 後の行を返す = attempts > 0 が保証される。
        # それでも _safe_accuracy のゼロ割ガードが効くことを境界値として確認する。
        # ここでは「全敗」（correct=0, attempts=3）のケースで accuracy=0.0 を確認。
        mock_me_repo.aggregate_by_category.return_value = [
            CategoryAggregate(category="async", attempts=3, correct=0),
        ]

        res = await service.get_stats(user_id=uuid.uuid4())

        assert res.total == 3
        assert res.correct == 0
        assert res.accuracy == 0.0
        assert res.by_category[0].accuracy == 0.0


class TestGetWeakness:
    async def test_正常系_しきい値未満かつ3問以上のカテゴリのみ抽出される(
        self,
        service: MeService,
        mock_me_repo: AsyncMock,
    ) -> None:
        user_id = uuid.uuid4()
        # 候補 4 つを与え、抽出条件で 2 つだけ残ることを観測する。
        mock_me_repo.aggregate_by_category.return_value = [
            # accuracy=0.2、attempts=5 → 該当
            CategoryAggregate(category="recursion", attempts=5, correct=1),
            # accuracy=0.8、attempts=10 → 弱点ではない（50% 以上）
            CategoryAggregate(category="array", attempts=10, correct=8),
            # accuracy=0.0、attempts=2 → サンプル不足で除外（3 問未満）
            CategoryAggregate(category="async", attempts=2, correct=0),
            # accuracy=0.25、attempts=4 → 該当
            CategoryAggregate(category="string", attempts=4, correct=1),
        ]

        res = await service.get_weakness(user_id=user_id)

        mock_me_repo.aggregate_by_category.assert_called_once_with(user_id=user_id)
        # 弱点 2 件、accuracy 昇順で recursion (0.2) → string (0.25)。
        assert len(res.weak_categories) == 2
        assert res.weak_categories[0].category == "recursion"
        assert res.weak_categories[0].accuracy == pytest.approx(0.2)
        assert res.weak_categories[1].category == "string"
        assert res.weak_categories[1].accuracy == pytest.approx(0.25)

    async def test_境界値_attempts3ちょうどは弱点候補に含まれる(
        self,
        service: MeService,
        mock_me_repo: AsyncMock,
    ) -> None:
        # attempts == ME_WEAKNESS_MIN_ATTEMPTS（3）は「>=」境界の内側。
        mock_me_repo.aggregate_by_category.return_value = [
            CategoryAggregate(category="recursion", attempts=3, correct=1),
        ]
        assert ME_WEAKNESS_MIN_ATTEMPTS == 3  # 期待値の固定化（しきい値の SSoT）

        res = await service.get_weakness(user_id=uuid.uuid4())

        assert len(res.weak_categories) == 1
        assert res.weak_categories[0].category == "recursion"

    async def test_境界値_accuracyしきい値ちょうどは弱点に含まれない(
        self,
        service: MeService,
        mock_me_repo: AsyncMock,
    ) -> None:
        # accuracy == ME_WEAKNESS_ACCURACY_THRESHOLD（0.5）は「<」境界の外側。
        # learning.md §ビジネスルール「正答率が一定以下（50% 未満）」の解釈。
        assert ME_WEAKNESS_ACCURACY_THRESHOLD == 0.5
        mock_me_repo.aggregate_by_category.return_value = [
            # accuracy=0.5 ちょうど → 含めない
            CategoryAggregate(category="array", attempts=4, correct=2),
            # accuracy=0.4 → 含める
            CategoryAggregate(category="recursion", attempts=5, correct=2),
        ]

        res = await service.get_weakness(user_id=uuid.uuid4())

        assert [w.category for w in res.weak_categories] == ["recursion"]

    async def test_並び順_accuracy昇順_tie時はattempts降順(
        self,
        service: MeService,
        mock_me_repo: AsyncMock,
    ) -> None:
        # accuracy が同率（0.2）の 2 カテゴリで attempts を変えて並び順を観測する。
        mock_me_repo.aggregate_by_category.return_value = [
            CategoryAggregate(category="b_small", attempts=5, correct=1),  # 0.2
            CategoryAggregate(category="a_big", attempts=10, correct=2),  # 0.2
            CategoryAggregate(category="c_other", attempts=4, correct=1),  # 0.25
        ]

        res = await service.get_weakness(user_id=uuid.uuid4())

        # accuracy 昇順 = 0.2, 0.2, 0.25。
        # 0.2 同率の中で attempts 多い順 = a_big (10) → b_small (5)。
        assert [w.category for w in res.weak_categories] == [
            "a_big",
            "b_small",
            "c_other",
        ]

    async def test_top_n_を超える候補は先頭ME_WEAKNESS_TOP_N件で切られる(
        self,
        service: MeService,
        mock_me_repo: AsyncMock,
    ) -> None:
        assert ME_WEAKNESS_TOP_N == 5
        # 6 候補すべて弱点条件を満たす（attempts=20, accuracy=0.00〜0.25 で
        # しきい値 0.5 未満）。Top 5 で切られて 6 件目が落ちることを観測する。
        mock_me_repo.aggregate_by_category.return_value = [
            CategoryAggregate(category=f"cat{i}", attempts=20, correct=i)
            for i in range(6)
        ]

        res = await service.get_weakness(user_id=uuid.uuid4())

        assert len(res.weak_categories) == ME_WEAKNESS_TOP_N

    async def test_履歴ゼロのユーザーはweak_categoriesが空(
        self,
        service: MeService,
        mock_me_repo: AsyncMock,
    ) -> None:
        # 履歴ゼロ：200 / weakCategories=[]（learning.md §受け入れ条件）。
        mock_me_repo.aggregate_by_category.return_value = []

        res = await service.get_weakness(user_id=uuid.uuid4())

        assert res.weak_categories == []
