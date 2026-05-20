# このファイルの役割：
#   問題生成ジョブの payload を Pydantic で定義する SSoT。
#   末尾を "JobPayload" にすると export_job_schemas.py が自動収集して
#   apps/api/job-schemas/problem-generation.schema.json に書き出す。
#   それを Worker 側で quicktype が読んで Go struct に変換する（ADR 0006）。
#
# 関わる要件：
#   - docs/requirements/4-features/problem-generation.md §ユーザーフロー
#   - docs/requirements/3-cross-cutting/01-data-model.md「ジョブペイロード共通フィールド」
#   - docs/adr/0010-w3c-trace-context-in-job-payload.md

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.schemas.jobs.common import TraceContext
from app.schemas.problems import ProblemCategory, ProblemDifficulty


class ProblemGenerationJobPayload(BaseModel):
    """問題生成 Worker が受け取るジョブ payload。

    Backend が INSERT INTO jobs (payload, ...) で書き込み、Worker が JSON として
    読み出して生成プロンプトを組み立てる。Worker 側の Go struct は
    apps/workers/<name>/internal/jobtypes/types.go に quicktype で自動生成される。

    - generation_request_id : generation_requests テーブルの主キー（Worker が完了時に
                              status / produced_problem_id を更新する対象）
    - user_id              : 観測ログ / レート制限の集計に使う
    - category / difficulty : 生成プロンプトの変数として埋め込む
    - trace_context        : ADR 0010「全ジョブ payload に必須」
    """

    # alias_generator=to_camel:
    #   Worker 側で Go struct のフィールドは PascalCase だが、JSON タグは
    #   camelCase になる。Backend 側 JSON 出力を camelCase に揃えるため設定。
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )

    generation_request_id: UUID
    user_id: UUID
    category: ProblemCategory
    difficulty: ProblemDifficulty
    # Field(...): 必須を明示しつつ description で OpenAPI / JSON Schema に説明を残す。
    trace_context: TraceContext = Field(
        ...,
        description="W3C Trace Context（ADR 0010）。Worker 側で子スパンの親として使う。",
    )
