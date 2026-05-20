# このファイルの役割：
#   採点ジョブの payload を Pydantic で定義する SSoT。
#   末尾を "JobPayload" にすると export_job_schemas.py が自動収集して
#   apps/api/job-schemas/grading.schema.json に書き出す。
#   それを Worker 側で quicktype が読んで Go struct に変換する（ADR 0006）。
#
# 関わる要件：
#   - docs/requirements/4-features/grading.md §採点フロー対象認証ユーザー
#   - docs/requirements/3-cross-cutting/01-data-model.md「ジョブペイロード共通フィールド」
#   - docs/adr/0010-w3c-trace-context-in-job-payload.md

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.schemas.jobs.common import TraceContext


class GradingJobPayload(BaseModel):
    """採点 Worker が受け取るジョブ payload。

    Backend が POST /api/submissions のトランザクション内で INSERT INTO jobs
    （queue='grading' / type='submission.grade'）し、Worker が JSON として
    読み出してサンドボックス採点を実行する。Worker 側の Go struct は
    apps/workers/grading/internal/jobtypes/grading.go に quicktype で
    自動生成される。

    - submission_id : 採点対象 submissions 行の id。Worker が UPDATE する主キー
    - user_id      : 観測ログ・ownership 突合に使う
    - problem_id   : 採点対象の問題 id（test_cases / reference_solution を引く）
    - code         : ユーザーが提出した TS コード（solution.ts として保存）
    - trace_context : ADR 0010「全ジョブ payload に必須」
    """

    # alias_generator: snake_case ↔ camelCase。
    #   Worker 側で Go struct のフィールドは PascalCase だが、JSON タグは
    #   camelCase になる。Backend 側 JSON 出力を camelCase に揃えるため設定。
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )

    submission_id: UUID
    user_id: UUID
    problem_id: UUID
    code: str
    # Field(...): 必須を明示しつつ description で OpenAPI / JSON Schema に説明を残す。
    trace_context: TraceContext = Field(
        ...,
        description="W3C Trace Context（ADR 0010）。Worker 側で子スパンの親として使う。",
    )
