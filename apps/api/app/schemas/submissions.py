# このファイルの役割：
#   解答送信 API（grading.md §API）の HTTP 境界 JSON を定義する SSoT。
#   - POST /api/submissions の Request / Response（R1-4）
#   - GET  /api/submissions/:id の Response（R1-5、ポーリング用）
#   - GET  /api/submissions の Response（R1-5、自分の解答履歴一覧）
#
# 関わる要件：
#   - docs/requirements/4-features/grading.md §API
#   - docs/requirements/4-features/problem-display-and-answer.md §「実行」ボタン

from datetime import datetime
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
class SubmissionAcceptedResponse(_CamelModel):
    """解答送信の受付完了。クライアントは submissionId を持って結果取得 API を叩く。"""

    submission_id: UUID
    status: Literal[SubmissionStatus.PENDING] = SubmissionStatus.PENDING


# SubmissionFailureKind: 採点が「正常終了したが解答が正解でない」場合の原因分類。
#   grading.md §採点フロー「失敗系のユーザー観測」と一致させる：
#     test_failed : 一部テスト不合格
#     timeout     : 実行時間 5 秒超過
#     oom         : メモリ使用量超過（コンテナ OOMKilled）
#     syntax      : 構文エラー（コードがそもそも実行できない）
#     runtime     : 実行時例外（throw / 未捕捉例外）
#     type_error  : 型エラー（tsc --noEmit が失敗）。型パズル系カテゴリ専用。
#   いずれも submissions.status='graded' で確定する。
#   インフラ起因の障害（docker daemon 切断等）は status='failed' 側で表現するため
#   本 enum には含めない。
class SubmissionFailureKind(StrEnum):
    TEST_FAILED = "test_failed"
    TIMEOUT = "timeout"
    OOM = "oom"
    SYNTAX = "syntax"
    RUNTIME = "runtime"
    TYPE_ERROR = "type_error"


# SubmissionTestResultItem: 1 件のテストケース実行結果。
#   要件側 JSON 例（grading.md §JSON 例 #get-submissionsid）：
#     { "name": "case1", "passed": true, "durationMs": 120 }
#   失敗ケースは expected / actual / message を画面に出すため optional で持つ。
class SubmissionTestResultItem(_CamelModel):
    """1 テストケース分の結果。passed=false の時に expected/actual/message が埋まる。"""

    name: str
    passed: bool
    duration_ms: int
    # expected / actual / message:
    #   passed=true の時は通常 None。failed 時は人間が読める文字列に整形済み。
    expected: str | None = None
    actual: str | None = None
    message: str | None = None


# SubmissionResultPayload: 採点結果本体（submissions.result JSONB に対応）。
#   passed: 全テスト通過したか。failureKind とは独立に持つ（passed=false でも
#           failureKind=None になりうる：例 部分点なしで test_failed 確定など）。
#   durationMs: サンドボックス全体の実行時間ミリ秒。
#   failureKind: SubmissionFailureKind を参照。
class SubmissionResultPayload(_CamelModel):
    """採点完了時の結果ペイロード。Worker が submissions.result に書き込む形と一致。"""

    passed: bool
    duration_ms: int
    failure_kind: SubmissionFailureKind | None = None
    test_results: list[SubmissionTestResultItem] = Field(default_factory=list)


# SubmissionStatusResponse: GET /api/submissions/:id の 200 レスポンス。
#   要件側 JSON 例（grading.md §JSON 例 #get-submissionsid）：
#     id / problemId / status / score / totalCount / result / gradedAt
#
#   pending の間は score / totalCount / result / gradedAt は None。
#   graded / failed に遷移してから埋まる。
class SubmissionStatusResponse(_CamelModel):
    """解答 + 採点結果。クライアントは pending の間ポーリングする。"""

    id: UUID
    problem_id: UUID
    status: SubmissionStatus
    score: int | None = None
    total_count: int | None = None
    result: SubmissionResultPayload | None = None
    graded_at: datetime | None = None


# SubmissionSummary: GET /api/submissions の items 要素 1 件。
#   要件側 JSON 例（grading.md §JSON 例 #get-submissions）：
#     id / problemId / problemTitle / status / score / totalCount / gradedAt
#
#   problemTitle は problems テーブル JOIN で取る（Repository 側）。
class SubmissionSummary(_CamelModel):
    """解答履歴の 1 行分。問題タイトルまで含めて一覧 UI に必要十分。"""

    id: UUID
    problem_id: UUID
    problem_title: str
    status: SubmissionStatus
    score: int | None = None
    total_count: int | None = None
    graded_at: datetime | None = None


# SubmissionsListResponse: GET /api/submissions の 200 レスポンス全体。
#   要件側 JSON 例：{ "items": [...], "page": 1, "pageSize": 20, "totalPages": 3 }
#
#   既存 ProblemListResponse と同じく flat な items + page 情報。
#   PaginationMeta + Page[T] への汎用化（backend.md 推奨）は 3 つ目以降の
#   paginated エンドポイントが増えた時にまとめて行う（YAGNI、現状 2 つで
#   インライン記述のコストが小さい）。
class SubmissionsListResponse(_CamelModel):
    """解答履歴一覧 + ページネーション情報。"""

    items: list[SubmissionSummary]
    page: int
    page_size: int
    total_pages: int


# SUBMISSIONS_PAGE_SIZE: GET /api/submissions のデフォルト 1 ページ件数。
#   ProblemListResponse 側と同じく 20。クライアントから ?pageSize= で上書き可能。
SUBMISSIONS_PAGE_SIZE = 20
# SUBMISSIONS_PAGE_SIZE_MAX: 1 リクエストで取れる上限。
#   巨大値で DB を引き倒される攻撃を防ぐためのサーバ側の天井。
SUBMISSIONS_PAGE_SIZE_MAX = 100
