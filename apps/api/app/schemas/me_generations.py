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
#   failure_reason は API 境界で意図的に露出しない：
#     - DB の generation_requests.failure_reason は内部タグ（"judge_below_threshold"
#       / "sandbox_failed" / "llm_invalid_output" 等）を持ち、運用ログ・ops 用途
#     - 要件 problem-generation.md §94 / §122 で「内部の失敗種別はユーザーには
#       区別せず表示」と定めており、API レスポンス JSON で生タグを返すと
#       DevTools / curl 経由で内部状態が漏れるため、フィールド自体を返さない
#     - UI が見せるべきは「失敗した」事実のみで、FE は status==='failed' を
#       見て固定文言を出す（formatFailureReason は不要）
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
