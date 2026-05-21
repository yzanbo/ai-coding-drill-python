# このファイルの役割：
#   問題生成履歴・状態管理 API（R1-7）の HTTP 境界 JSON を定義する SSoT。
#   - GET  /api/me/generations            : 自分の生成リクエスト履歴一覧
#   - POST /api/me/generations/:id/cancel : pending のキャンセル
#   - POST /api/me/generations/:id/retry  : failed の再試行（新規 generation_request 作成）
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md §履歴・状態管理

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

# GenerationStatus: generation_requests.status の許可値。
#   DB CHECK 制約は無いので、Pydantic Literal が唯一の SSoT。
#   既存 3 値 (pending / completed / failed) に R1-7 で canceled を追加した。
GenerationStatus = Literal["pending", "completed", "failed", "canceled"]


# FailureReasonTag: failed 行で API が返す失敗理由カテゴリ。
#   Worker (apps/workers/grading/internal/grading/problem_generate.go の
#   classifyFailureReason) が dead 確定時に generation_requests.failure_reason に
#   書く 6 タグと 1:1 対応。FE はこの enum を switch して日本語文言に変換する
#   (apps/web/src/app/(routing)/(authed)/me/generations/page.tsx の
#   FAILURE_MESSAGES)。
#
#   生エラー文字列ではなく固定の enum に絞ることで、API 境界での「内部状態漏洩」
#   懸念を解消しつつ、ユーザーには有用な分類情報を渡せる（例: 認証エラーなら
#   「もう一度試す」ではなく管理者連絡を促す等、文言を最適化できる）。
FailureReasonTag = Literal[
    "llm_unauthorized",
    "llm_cost_exceeded",
    "judge_below_threshold",
    "sandbox_failed",
    "sandbox_infrastructure",
    "llm_invalid_output",
    "llm_rate_limit",
    "llm_timeout",
    "llm_schema_invalid",
    "max_attempts_exceeded",
]


# ProgressStep: pending 行で Worker が現在どのステップを処理中かを表す。
#   Worker (apps/workers/grading/internal/grading/problem_generate.go の Handle) が
#   各ステップ開始時に generation_requests.progress_step を UPDATE する。
#   terminal 行（completed / failed / canceled）では NULL（status から終了状態が
#   分かるため、ステップ列は不要）。
#
#   ステップ意味：
#     - llm_generating    : LLM に問題生成を依頼中
#     - sandbox_verifying : 生成された reference_solution を sandbox で実行検証中
#     - judging           : judge LLM で問題品質を評価中
#     - persisting        : problems INSERT + generation_requests 完了処理中
#
#   FE はこの enum を switch して進捗インジケータの「現在ステップ」を描画する。
ProgressStep = Literal[
    "llm_generating",
    "sandbox_verifying",
    "judging",
    "persisting",
]


# ME_GENERATIONS_PAGE_SIZE: 履歴 1 ページあたりの行数。
#   要件 .md にはサイズ指定が無いため、解答履歴 (/me/history) と同じ 20 に揃える。
ME_GENERATIONS_PAGE_SIZE = 20


class _CamelModel(BaseModel):
    """snake_case 属性 ↔ camelCase JSON 用の共通基底。"""

    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


# AttemptError: Worker が 1 回の試行（MarkFailed / MarkDead）ごとに jobs.attempt_errors
# JSONB array に append する 1 要素。failureReason は単一試行に対する classifyFailureReason
# の出力で、最終的な generation_requests.failure_reason と意味は同じ enum を再利用する。
class AttemptError(_CamelModel):
    """1 回分の試行エラー（jobs.attempt_errors の 1 要素）。"""

    # attempt: jobs.attempts と同じ値（1, 2, 3...）。MarkDead 経路（即 dead）では
    #   Worker が attempt=0 を入れるため min は 0 まで許容する。
    attempt: int = Field(ge=0)
    # failure_reason: その回の error から classifyFailureReason で分類したタグ。
    failure_reason: FailureReasonTag
    # message: 生のエラー文字列（Worker 側で長さ上限 1000 文字に truncate 済）。
    message: str
    # failed_at: その試行が失敗した時刻（jobs.MarkFailed/MarkDead 呼び出し時の NOW()）。
    failed_at: datetime


# GenerationRequestSummary: 履歴 1 行分の表示用サマリ。
#   要件 .md JSON 例 (#get-apimegenerations) と整合：
#     id / category / difficulty / status / producedProblemId / promptVersion /
#     retryOf / retryCount / createdAt / completedAt
#
#   retry_count: retry_of チェーンを辿って「N 回目の再試行」を表す整数。
#                元リクエスト = 0、その retry = 1、その retry の retry = 2 ...
#                Service 側で再帰的に計算する（DB 列としては持たない、計算で済む）。
#   prompt_version: jobs.payload.prompt_version を JOIN で取得した値。
#                   jobs が TTL で物理削除された後は NULL を返す（履歴永続化はしない方針）。
#
#   failure_reason:
#     - failed 行のみ FailureReasonTag を返す（completed/pending/canceled では None）。
#     - DB の generation_requests.failure_reason 列は生 string だが、Worker が書く
#       値は classifyFailureReason の 6 タグに正規化されている。Service 側で
#       enum 範囲チェックを挟んで、想定外値が紛れ込んだ場合は None に倒す
#       （旧データや手動修正に対する防御線）。
#     - FE は本フィールドを switch して日本語文言に変換する（page.tsx の
#       FAILURE_MESSAGES）。生タグ文字列を画面に出さないので「内部状態漏洩」
#       懸念は固定 enum + FE マップで解消される。
class GenerationRequestSummary(_CamelModel):
    """生成リクエスト履歴の 1 行分。"""

    id: UUID
    category: str
    difficulty: str
    status: GenerationStatus
    produced_problem_id: UUID | None = None
    prompt_version: str | None = None
    retry_of: UUID | None = None
    retry_count: int = Field(ge=0)
    failure_reason: FailureReasonTag | None = None
    # progress_step: pending 行の現在ステップ。pending 以外では None。
    #   Service 側で status=='pending' の時だけ詰める（completed/failed/canceled では
    #   ステップ列が残っていても返さない）。
    progress_step: ProgressStep | None = None
    # attempt_errors: failed 行のみ、全 MaxAttempts 回の試行ごとのエラー履歴を返す。
    #   Worker が jobs.MarkFailed / MarkDead で append した JSONB array を読み出す。
    #   「3 回試行のうち何が起きたか」が分かり、「全部 rate_limit」「初回 sandbox、
    #   2 回目 judge 不合格」等のパターン特定が DB / UI から可能になる。
    #   本人のリクエストしか取得経路が無い（user_id 一致 WHERE 完備）ため、内部詳細の
    #   漏洩懸念は構造的に解消されている。jobs が TTL で消えていれば空配列。
    attempt_errors: list[AttemptError] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None


class MeGenerationsListResponse(_CamelModel):
    """生成履歴一覧 + ページネーション情報。"""

    items: list[GenerationRequestSummary]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)


# GenerationRequestCancelResponse: cancel 成功時の最小レスポンス。
#   キャンセル後の確定 status は必ず 'canceled' なので Literal で固定する
#   （FE 側で型 narrow できる）。
class GenerationRequestCancelResponse(_CamelModel):
    """キャンセル後の最終状態。"""

    id: UUID
    status: Literal["canceled"]


# GenerationRequestRetryResponse: retry 成功時のレスポンス。
#   新規 generation_request の id と retry_of（元 ID）を返す。
#   status は必ず 'pending'（新規作成直後なので Literal で固定）。
class GenerationRequestRetryResponse(_CamelModel):
    """再試行で作られた新規 generation_request の最小情報。"""

    id: UUID
    status: Literal["pending"]
    retry_of: UUID
