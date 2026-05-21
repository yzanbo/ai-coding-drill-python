# このファイルの役割：
#   問題生成リクエスト関連 API の HTTP 境界 JSON の形を定義する SSoT。
#   FastAPI が response_model に渡された形を OpenAPI に書き出し、Frontend は
#   それを Hey API 経由で TypeScript 型に展開する（→ ADR 0006）。
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md
#     §API / §JSON 例 / §バリデーション

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

# BaseModel:  Pydantic の親クラス。
# ConfigDict: モデル設定用 TypedDict（class Config より型補完が効く）。
# alias_generators.to_camel: snake_case → camelCase 自動変換。
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

# 生成ステータス画面で使う enum を履歴側 schema から再利用する。
#   FailureReasonTag / ProgressStep は schemas/me_generations.py が SSoT
#   （Worker classifyFailureReason / progress_step UPDATE と 1:1 対応）。
from app.schemas.me_generations import AttemptError, FailureReasonTag, ProgressStep


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
#     { "requestId": "<uuid>", "status": "pending", "progressStep": "llm_generating", ... }
#     { "requestId": "<uuid>", "status": "completed", "problemId": "<uuid>", ... }
#     { "requestId": "<uuid>", "status": "failed", "failureReason": "judge_below_threshold", ... }
#
#   R1-7-2 で created_at / completed_at / progress_step / failure_reason を追加。
#   生成ステータス画面で「開始時刻 / 所要時間 / 現在ステップ / 失敗理由」を表示するため。
#   履歴画面 (GenerationRequestSummary) と同じ enum を再利用する。
class ProblemGenerateStatusResponse(_CamelModel):
    """生成リクエストの現在ステータス。completed の時のみ problemId を含む。"""

    request_id: UUID
    status: GenerationStatus
    # problem_id: completed の時のみ非 None。pending / failed では None（JSON では省略される）。
    problem_id: UUID | None = None
    # progress_step: pending 行の現在処理ステップ。Service 側で status=='pending'
    #   の時だけ詰める。詳細は schemas/me_generations.py の ProgressStep 参照。
    progress_step: ProgressStep | None = None
    # failure_reason: failed 行のみ enum 値を返す。同じく schemas/me_generations.py
    #   の FailureReasonTag を再利用する（情報漏洩懸念は固定 enum で構造的に解消済み）。
    failure_reason: FailureReasonTag | None = None
    # attempt_errors: failed 行のみ、全試行のエラー履歴を返す（本人のリクエスト
    #   へのデバッグ詳細）。詳細は schemas/me_generations.py
    #   GenerationRequestSummary.attempt_errors 参照。
    attempt_errors: list[AttemptError] = []
    # created_at / completed_at: 開始時刻 / 終了時刻。所要時間表示に使う。
    #   pending の間は completed_at=None（FE 側で「now との差分」を出す）。
    created_at: datetime | None = None
    completed_at: datetime | None = None


# ----------------------------------------------------------------------------
# 問題閲覧（一覧 / 詳細）— problem-display-and-answer.md §API（R1-4）
# ----------------------------------------------------------------------------

# PROBLEMS_PAGE_SIZE: 1 ページあたりの件数（サーバ側固定）。
#   将来 limit クエリで可変にする時はここを既定値に格上げする。
PROBLEMS_PAGE_SIZE = 20


# ProblemExample: 入出力例 1 件（テストケースの一部を「見える化」したもの）。
#   要件側 JSON 例：{ "input": "[1,2,3]", "output": "6" }
class ProblemExample(_CamelModel):
    """画面表示用の入出力例。input / output は表示用の文字列。"""

    input: str
    output: str


# ProblemSummaryResponse: GET /api/problems の items 要素 1 件。
#   一覧用に最小限のカラムだけを返す（description / examples は詳細でのみ返す）。
class ProblemSummaryResponse(_CamelModel):
    """問題一覧の 1 行分。タイトル / カテゴリ / 難易度のみで一覧 UI に必要十分。"""

    id: UUID
    title: str
    category: ProblemCategory
    difficulty: ProblemDifficulty


# ProblemListResponse: GET /api/problems の 200 レスポンス全体。
#   要件側 JSON 例：{ "items": [...], "page": 1, "totalPages": 10 }
class ProblemListResponse(_CamelModel):
    """問題一覧 + ページネーション情報。

    一覧クエリ単発で SSoT が固定されており、PaginationMeta + Page の
    汎用化（backend.md 推奨）は 2 つ目の paginated エンドポイントが
    出てきた時点で行う（YAGNI、CLAUDE.md §設計原則）。
    """

    items: list[ProblemSummaryResponse]
    page: int
    total_pages: int


# ProblemDetailResponse: GET /api/problems/:id の 200 レスポンス。
#   ★マスキングの実体★：本モデルは test_cases / reference_solution /
#   judge_scores を持たない。SQLAlchemy モデル（models/problems.py）には
#   それらが存在するが、Pydantic レスポンスに含めないことで
#   「API レスポンスから完全な test_cases が読み出せない」要件
#   （problem-display-and-answer.md §受け入れ条件）を満たす。
#   from_attributes=True で ORM から余分なフィールドが付くことはない。
class ProblemDetailResponse(_CamelModel):
    """問題詳細。テストケースの一部のみ examples として公開する。"""

    id: UUID
    title: str
    description: str
    examples: list[ProblemExample]
    category: ProblemCategory
    difficulty: ProblemDifficulty
