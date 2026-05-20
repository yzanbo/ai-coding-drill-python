# このファイルの役割：
#   全 Job payload で共通して使うフィールドの Pydantic 定義。
#   現状は W3C Trace Context（traceparent / tracestate）の埋め込み（ADR 0010）。
#
# なぜ共通化するか：
#   data-model.md「ジョブペイロード共通フィールド」で「全ジョブ payload に
#   traceContext を必須として含める」と決めている。各 Job ごとに同じ型を
#   重複定義するとずれる（Pydantic は構造的等価性を持たないので JSON Schema 上
#   別物として扱われる）ため、ここで 1 個に集約する。
#
# 関わる要件：
#   - docs/requirements/3-cross-cutting/01-data-model.md「ジョブペイロード共通フィールド」
#   - docs/adr/0010-w3c-trace-context-in-job-payload.md

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class TraceContext(BaseModel):
    """W3C Trace Context の最小表現（traceparent + tracestate）。

    Backend（Producer）が現在の OTel Span のコンテキストをジョブ payload に
    詰めることで、Worker（Consumer）側が同一トレースの子スパンを発行できる。
    詳細仕様は ADR 0010。

    - traceparent : "00-<trace-id>-<span-id>-<flags>" の固定書式（W3C 仕様）
    - tracestate  : ベンダー固有の追加情報。未使用なら空文字
    """

    # alias_generator=to_camel:
    #   Job payload は JSON Schema → Go quicktype 経由で Worker に展開されるため、
    #   キーは API レスポンスと同じく camelCase で統一する。
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )

    traceparent: str
    tracestate: str = ""
