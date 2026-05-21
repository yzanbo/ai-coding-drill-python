# MeService: 学習履歴・統計ドメインのビジネスロジック層（ADR 0044）。
#
#   - get_stats    : GET /api/me/stats 用に全期間 + カテゴリ別を集計して返す
#   - get_weakness : GET /api/me/weakness 用に弱点カテゴリ Top N を返す
#
#   Repository から受け取った CategoryAggregate（カテゴリ別 attempts / correct）を
#   元に accuracy 計算 + 弱点抽出 + 並び替えを Service で行う。
#   SQL 側は集計のみに留め、しきい値・並び順の判断は Python 側で扱う（要件側で
#   しきい値が変わっても SQL を触らずに済む設計）。
#
# 関わる要件：
#   - docs/requirements/4-features/learning.md §API
#   - docs/requirements/4-features/learning.md §ビジネスルール

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.me import CategoryAggregate, MeRepository
from app.schemas.me import (
    ME_WEAKNESS_ACCURACY_THRESHOLD,
    ME_WEAKNESS_MIN_ATTEMPTS,
    ME_WEAKNESS_TOP_N,
    MeCategoryStat,
    MeStatsResponse,
    MeWeakCategoryItem,
    MeWeaknessResponse,
)


# _safe_accuracy: ゼロ割を防ぎつつ accuracy を計算するヘルパ。
#   attempts=0 の時は 0.0 を返す（履歴ゼロのユーザーで NaN を返さない）。
def _safe_accuracy(correct: int, attempts: int) -> float:
    if attempts <= 0:
        return 0.0
    return correct / attempts


class MeService:
    """学習履歴・統計サービス。

    - 1 リクエストにつき 1 インスタンス生成
    - 引数の db_session を保持して Repository を組み立てる
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self.db_session = db_session
        self.me = MeRepository(db_session)

    async def get_stats(
        self,
        *,
        user_id: UUID,
    ) -> MeStatsResponse:
        """全期間の正答率 + カテゴリ別習熟度を返す。

        振る舞い：
          - 採点完了行のみを集計（pending / failed はカウントしない）
          - ソフトデリートは無視（履歴永続保存、learning.md §ビジネスルール）
          - 履歴ゼロのユーザーには total=0 / correct=0 / accuracy=0.0 / byCategory=[]
            を返す（200 OK のまま、404 は使わない）
        """
        aggregates = await self.me.aggregate_by_category(user_id=user_id)

        # by_category: Repository が category ASC で並べた順をそのまま採用。
        #   accuracy を Python 側で計算して詰める。
        by_category = [
            MeCategoryStat(
                category=agg.category,
                attempts=agg.attempts,
                correct=agg.correct,
                accuracy=_safe_accuracy(agg.correct, agg.attempts),
            )
            for agg in aggregates
        ]

        # total / correct: カテゴリ別の合計を Python 側で足し上げる。
        #   SQL に追加クエリを発行するより 1 クエリで取って合算する方が安い。
        total = sum(agg.attempts for agg in aggregates)
        correct = sum(agg.correct for agg in aggregates)

        return MeStatsResponse(
            total=total,
            correct=correct,
            accuracy=_safe_accuracy(correct, total),
            by_category=by_category,
        )

    async def get_weakness(
        self,
        *,
        user_id: UUID,
    ) -> MeWeaknessResponse:
        """弱点カテゴリ Top N を返す。

        抽出ルール（learning.md §ビジネスルール）：
          - attempts >= ME_WEAKNESS_MIN_ATTEMPTS（3 問以上）
          - accuracy < ME_WEAKNESS_ACCURACY_THRESHOLD（50% 未満）
          - 並び順は accuracy ASC（弱い順）、tie-break は attempts DESC
            （同率なら解答数が多い方を上：サンプル信頼度が高い順）
          - 先頭 ME_WEAKNESS_TOP_N 件まで返す

        履歴が少ないユーザーは weakCategories=[] を返す（200 OK のまま）。
        """
        aggregates = await self.me.aggregate_by_category(user_id=user_id)

        # 弱点候補に絞る。accuracy 計算は 1 度きりで済むよう一時的に
        # (CategoryAggregate, accuracy) のペアにする。
        candidates: list[tuple[CategoryAggregate, float]] = []
        for agg in aggregates:
            if agg.attempts < ME_WEAKNESS_MIN_ATTEMPTS:
                continue
            accuracy = _safe_accuracy(agg.correct, agg.attempts)
            if accuracy >= ME_WEAKNESS_ACCURACY_THRESHOLD:
                continue
            candidates.append((agg, accuracy))

        # 並び替え：accuracy ASC、tie-break で attempts DESC。
        #   Python の sort は stable なので 2 段階に分けるより
        #   tuple キーで一発ソートする。attempts は DESC のため負号で反転。
        candidates.sort(key=lambda x: (x[1], -x[0].attempts))

        weak_categories = [
            MeWeakCategoryItem(
                category=agg.category,
                attempts=agg.attempts,
                correct=agg.correct,
                accuracy=accuracy,
            )
            for agg, accuracy in candidates[:ME_WEAKNESS_TOP_N]
        ]

        return MeWeaknessResponse(weak_categories=weak_categories)
