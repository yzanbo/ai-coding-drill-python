# このファイルの役割：
#   解答送信 API（grading.md §API）の HTTP 境界 JSON を定義する SSoT。
#   R1-4 では POST /api/submissions の Request / Response 2 つだけ持つ。
#   採点結果取得（GET /api/submissions/:id）は R1-5 で追加する。
#
# 関わる要件：
#   - docs/requirements/4-features/grading.md §API #post-submissions
#   - docs/requirements/4-features/problem-display-and-answer.md §「実行」ボタン

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


# SubmissionStatus: ユーザー視点の状態（data-model.md「状態カラム」）。
#   pending : 受付済み、採点待ち
#   graded  : 採点完了（R1-5 で Worker が遷移）
#   failed  : インフラ起因の失敗（R1-5 で Worker が遷移）
class SubmissionStatus(StrEnum):
    PENDING = "pending"
    GRADED = "graded"
    FAILED = "failed"


# _CamelModel: snake_case 属性 ↔ camelCase JSON 用の共通基底。
class _CamelModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


# SubmissionCreateRequest: POST /api/submissions の入力。
#   要件側 JSON 例：{ "problemId": "<uuid>", "code": "const solve = ..." }
#
#   code の長さ上限：
#     極端に長いコードを投げて DB / LLM への負荷を増やす攻撃面を防ぐため上限を設ける。
#     具体値は MVP では 100,000 文字（VS Code 1 ファイル相当の上限。要件側で確定したら
#     その値に差し替える）。422 で弾く。
class SubmissionCreateRequest(_CamelModel):
    """解答送信リクエスト。"""

    problem_id: UUID
    code: str = Field(min_length=1, max_length=100_000)


# SubmissionAcceptedResponse: POST /api/submissions の 202 レスポンス。
#   要件側 JSON 例：{ "submissionId": "<uuid>", "status": "pending" }
#
#   status は Literal[PENDING] 固定（受付時点では必ず pending）。
#   採点結果取得（R1-5）では SubmissionStatusResponse のような別モデルに分ける想定。
class SubmissionAcceptedResponse(_CamelModel):
    """解答送信の受付完了。クライアントは submissionId を持って結果取得 API を叩く。"""

    submission_id: UUID
    status: Literal[SubmissionStatus.PENDING] = SubmissionStatus.PENDING
