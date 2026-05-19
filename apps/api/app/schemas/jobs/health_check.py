# Job キュー境界の型同期パイプライン（ADR 0006）疎通確認用のサンプル JobPayload。
#
# 役割:
#   Pydantic（Backend）→ JSON Schema（apps/api/job-schemas/）→ quicktype → Go struct
#   （apps/workers/<worker>/internal/jobtypes/types.go）の end-to-end パイプラインを
#   R0-11 時点で 1 つの payload で疎通確認するための placeholder。
#
# クラス名の規約:
#   末尾を "JobPayload" にすると export_job_schemas.py が自動収集する。
#   出力名は CamelCase → kebab-case: HealthCheckJobPayload → health-check.schema.json
#
# 将来:
#   R1-2（LLM プロバイダ抽象化）/ R1-3（問題生成）/ R1-5（自動採点）等の機能実装時に
#   GradingJobPayload / GenerationJobPayload 等を同じパターンで追加していく。
#   本 placeholder は機能実装で実 payload が増えた後も「最小サンプル」として残してよい
#   （疎通確認用の最後の砦になる）。

# BaseModel: Pydantic の親クラス。継承すると JSON ⇄ Python の変換と入力検証が自動で効く。
from pydantic import BaseModel


# HealthCheckJobPayload: 型同期パイプライン疎通確認用のサンプル JobPayload。
class HealthCheckJobPayload(BaseModel):
    # job_id: ジョブを一意に識別する文字列。UUID 文字列を想定するが、ここでは型同期の
    #         疎通確認が目的なので str に留める（実 payload で UUID を使う場合は別途）。
    job_id: str

    # note: 任意メモ。空文字をデフォルトにして「必須でなくても通る」ことを確認する。
    note: str = ""
