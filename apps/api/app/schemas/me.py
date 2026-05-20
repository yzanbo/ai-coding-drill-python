# このファイルの役割：
#   学習履歴・統計 API（learning.md §API）の HTTP 境界 JSON を定義する SSoT。
#   - GET /api/me/stats    : 全期間の正答率 + カテゴリ別習熟度（R1-6）
#   - GET /api/me/weakness : 正答率の低いカテゴリ Top N（R1-6）
#
# 関わる要件：
#   - docs/requirements/4-features/learning.md §API
#   - docs/requirements/3-cross-cutting/01-data-model.md（ソフトデリート方針）

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


# _CamelModel: snake_case 属性 ↔ camelCase JSON 用の共通基底。
#   submissions.py 側と同じ規約で、属性は snake_case / JSON は camelCase に揃える。
class _CamelModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


# MeCategoryStat: 1 カテゴリの集計結果。
#   要件側 JSON 例（learning.md §JSON 例 #get-mestats）：
#     { "category": "array", "attempts": 10, "correct": 8, "accuracy": 0.8 }
#
#   accuracy: 0.0〜1.0 の小数。クライアント側で × 100 して % 表示する。
#             attempts > 0 が保証された行のみ含めるため、ゼロ割は発生しない。
class MeCategoryStat(_CamelModel):
    """カテゴリ別の解答数・正解数・正答率。"""

    category: str
    attempts: int = Field(ge=0)
    correct: int = Field(ge=0)
    accuracy: float = Field(ge=0.0, le=1.0)


# MeStatsResponse: GET /api/me/stats の 200 レスポンス。
#   要件側 JSON 例（learning.md §JSON 例 #get-mestats）：
#     { "total": 42, "correct": 30, "accuracy": 0.714, "byCategory": [...] }
#
#   total / correct: 全期間・全カテゴリ合計（採点完了行のみカウント）。
#   accuracy: total > 0 の時は correct/total、total = 0 の時は 0.0 を返す
#             （初心者ユーザーで履歴ゼロのケースに 422 / NaN を返さない）。
class MeStatsResponse(_CamelModel):
    """全期間の正答率 + カテゴリ別習熟度。"""

    total: int = Field(ge=0)
    correct: int = Field(ge=0)
    accuracy: float = Field(ge=0.0, le=1.0)
    by_category: list[MeCategoryStat] = Field(default_factory=list)


# MeWeakCategoryItem: 弱点カテゴリ 1 件。
#   要件側 JSON 例（learning.md §JSON 例 #get-meweakness）：
#     { "category": "recursion", "attempts": 5, "correct": 1, "accuracy": 0.2 }
#
#   構造は MeCategoryStat と同じだが、別 API のレスポンス契約として
#   別クラスに分けておく（将来 weakness 側だけ「練習導線」のフィールドが
#   増える等の片側拡張に備える、learning.md §弱点カテゴリ画面の
#   「練習する」ボタンが R6 以降で生える伏線）。
class MeWeakCategoryItem(_CamelModel):
    """弱点に該当するカテゴリ 1 件。"""

    category: str
    attempts: int = Field(ge=0)
    correct: int = Field(ge=0)
    accuracy: float = Field(ge=0.0, le=1.0)


# MeWeaknessResponse: GET /api/me/weakness の 200 レスポンス。
#   要件側 JSON 例（learning.md §JSON 例 #get-meweakness）：
#     { "weakCategories": [...] }
#
#   抽出ルール（learning.md §ビジネスルール）：
#     - attempts >= ME_WEAKNESS_MIN_ATTEMPTS（3 問以上、サンプル不足で誤判定を避ける）
#     - accuracy < ME_WEAKNESS_ACCURACY_THRESHOLD（50% 未満）
#   並び順は accuracy ASC（弱い順）、tie-break は attempts DESC（同率なら解答数が多い方を上）。
#   Top N は ME_WEAKNESS_TOP_N（5）まで返す。
class MeWeaknessResponse(_CamelModel):
    """弱点カテゴリ Top N。"""

    weak_categories: list[MeWeakCategoryItem] = Field(default_factory=list)


# しきい値定数（learning.md §ビジネスルール）。
#   要件側に「例：50% 未満」「例：3 問以上」と緩く書かれている数値の SSoT。
#   将来 UX 検証で変更する時はここを直す（要件 .md も合わせて更新する）。
ME_WEAKNESS_MIN_ATTEMPTS = 3
ME_WEAKNESS_ACCURACY_THRESHOLD = 0.5
ME_WEAKNESS_TOP_N = 5
