# このファイルの役割：
#   問題生成リクエスト関連 API の HTTP 境界 JSON の形を定義する SSoT。
#   FastAPI が response_model に渡された形を OpenAPI に書き出し、Frontend は
#   それを Hey API 経由で TypeScript 型に展開する（→ ADR 0006）。
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md
#     §API / §JSON 例 / §バリデーション

from enum import StrEnum
from typing import Literal
from uuid import UUID

# BaseModel:  Pydantic の親クラス。
# ConfigDict: モデル設定用 TypedDict（class Config より型補完が効く）。
# alias_generators.to_camel: snake_case → camelCase 自動変換。
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


# ProblemCategory: 問題のカテゴリ。
#   許可値はビジネスルール（problem-generation.md §バリデーション）で MVP の対応カテゴリに限定。
#   StrEnum なら OpenAPI に enum として公開され、Frontend の Hey API もリテラル型で受ける。
class ProblemCategory(StrEnum):
    STRING = "string"
    ARRAY = "array"
    RECURSION = "recursion"
    ASYNC = "async"
    TYPE_PUZZLE = "type-puzzle"


# ProblemDifficulty: 問題の難易度。
#   MVP では 3 段階（problem-generation.md §バリデーション）。
class ProblemDifficulty(StrEnum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


# GenerationStatus: 生成リクエストの状態。
#   ユーザー視点の遷移（pending → completed / failed）。マシン的な jobs.state とは別概念。
class GenerationStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


# CamelModel: snake_case 属性を camelCase JSON で入出力するための共通基底。
#   問題生成系のレスポンスは複数あるので、設定の重複を避けるためここに集約。
class _CamelModel(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


# ProblemGenerateRequest: POST /api/problems/generate のリクエスト JSON。
#   要件側 JSON 例：{ "category": "array", "difficulty": "easy" }
class ProblemGenerateRequest(_CamelModel):
    """問題生成リクエストの入力。

    category / difficulty とも Literal 縛りで MVP の許容値以外は 422 を返す
    （バリデーションは Pydantic が SSoT、problem-generation.md §バリデーション）。
    """

    category: ProblemCategory
    difficulty: ProblemDifficulty


# ProblemGenerateAcceptedResponse: POST /api/problems/generate の 202 レスポンス。
#   要件側 JSON 例：{ "requestId": "<uuid>", "status": "pending" }
class ProblemGenerateAcceptedResponse(_CamelModel):
    """生成リクエスト受付完了。クライアントは requestId でポーリングを始める。"""

    request_id: UUID
    status: Literal[GenerationStatus.PENDING] = GenerationStatus.PENDING


# ProblemGenerateStatusResponse: GET /api/problems/generate/:requestId の 200 レスポンス。
#   要件側 JSON 例（pending / completed / failed の 3 形）：
#     { "requestId": "<uuid>", "status": "pending" }
#     { "requestId": "<uuid>", "status": "completed", "problemId": "<uuid>" }
#     { "requestId": "<uuid>", "status": "failed" }
class ProblemGenerateStatusResponse(_CamelModel):
    """生成リクエストの現在ステータス。completed の時のみ problemId を含む。"""

    request_id: UUID
    status: GenerationStatus
    # problem_id: completed の時のみ非 None。pending / failed では None（JSON では省略される）。
    problem_id: UUID | None = None
