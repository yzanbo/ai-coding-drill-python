# MeRepository: 学習履歴・統計ドメインの集計 SQL を集約する層（ADR 0044）。
#
#   - aggregate_by_category : submissions × problems を JOIN して
#                             カテゴリ別の attempts / correct を返す
#                             （GET /api/me/stats / GET /api/me/weakness 兼用）
#
# 関わる要件：
#   - docs/requirements/4-features/learning.md §API
#   - docs/requirements/4-features/learning.md §ビジネスルール
#     「統計クエリは deleted_at を無視して全行を集計する」

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.problems import Problem
from app.models.submissions import Submission


# CategoryAggregate: カテゴリ別の集計結果 1 行分。
#   ORM オブジェクトではないが、Repository が「集計クエリの結果」を表現する
#   軽量データ型として返す。Service 側で Pydantic に詰め替える。
@dataclass(frozen=True)
class CategoryAggregate:
    category: str
    attempts: int
    correct: int


class MeRepository:
    """学習履歴・統計の集計クエリ実装。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def aggregate_by_category(
        self,
        *,
        user_id: UUID,
    ) -> list[CategoryAggregate]:
        """自分の submissions をカテゴリ別に集計する。

        集計対象（learning.md §ビジネスルール）：
          - 自分（user_id 一致）の submissions のみ
          - 採点完了行（status='graded'）のみ
            ※ pending / failed（インフラ起因失敗）は「正答かどうか判定できない」
              ためカウントしない（要件 .md には明記が無いが、UX 上自然な解釈で
              受け入れ条件にも追加する）
          - submissions / problems の deleted_at は無視（履歴永続保存の意図、
            learning.md §ビジネスルール「統計クエリは deleted_at を無視」）

        correct の定義：
          - submissions.result->>'passed' が true → 正答
          - それ以外 → 不正答
          - result が NULL の行は status='graded' フィルタで弾かれるため、
            NULL 個別ガードは不要だが念のため COALESCE で false 扱いにする

        並び順は category ASC（読みやすさのため）。Service 側で並べ替え不要に。
        """
        # passed_expr: submissions.result の JSONB から passed を抜く式。
        #   ->> 'passed' は text を返すため、'true' との比較で boolean を作る。
        #   result が NULL の行は status='graded' フィルタで除外されるが、
        #   万一 graded かつ result NULL の異常データが残っても false 扱いになる。
        passed_expr = Submission.result["passed"].astext == "true"

        # correct_expr: passed=true なら 1、それ以外 0 を返す SUM 対象。
        #   COUNT(*) で attempts、SUM(case when passed) で correct を 1 クエリで取る。
        correct_expr = func.sum(case((passed_expr, 1), else_=0))

        stmt = (
            select(
                Problem.category,
                func.count().label("attempts"),
                correct_expr.label("correct"),
            )
            .join(Problem, Problem.id == Submission.problem_id)
            .where(
                Submission.user_id == user_id,
                Submission.status == "graded",
            )
            .group_by(Problem.category)
            .order_by(Problem.category.asc())
        )

        rows = (await self.session.execute(stmt)).all()
        # correct は SUM の結果なので、空グループでは None になりうるが、
        # GROUP BY 後は最低 1 行存在するため常に int が返る。型安全のため int 化。
        return [
            CategoryAggregate(
                category=row.category,
                attempts=int(row.attempts),
                correct=int(row.correct or 0),
            )
            for row in rows
        ]
