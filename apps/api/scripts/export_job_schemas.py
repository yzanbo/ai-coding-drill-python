# 役割:
#   Job キュー境界の payload を表す Pydantic モデル群を自動収集し、
#   各モデルから個別の JSON Schema ファイルを書き出す。
#   Worker（Go）側の quicktype に渡す入力源。
#
# 出力先:
#   apps/api/job-schemas/<job-name>.schema.json
#   （Worker 側合流フェーズで quicktype --src で読み込む）
#
# 命名規約（収集対象）:
#   - 配置先:   apps/api/app/schemas/jobs/<job_type>.py
#   - 対象クラス: BaseModel を継承し、クラス名が "JobPayload" で終わるもの
#   - 出力名:   クラス名 → "JobPayload" を取り除き → CamelCase を kebab-case 化
#               例: GradingJobPayload → grading.schema.json
#
# 設計判断:
#   1) suffix 規約で誤検出を防ぐ。
#      "JobPayload" で終わらない補助クラス（共通基底等）は出力対象にしない。
#   2) 対象 0 個でもエラーにしない。
#      本フェーズ時点ではジョブ payload Pydantic は未追加。スクリプトと mise
#      タスクは先に配線完了させ、機能実装フェーズで Pydantic が追加されると
#      自動でファイルが増える設計（ADR 0006）。
#   3) JSON フォーマットは OpenAPI export と完全に同条件
#      （indent=2 + sort_keys=True + ensure_ascii=False + 末尾改行 + 同一なら skip）。
#      git diff の可読性と drift 検出の安定性を揃える。
#
# 相互参照:
#   HTTP API 境界側は export_openapi.py（同ディレクトリ）。
#   両者で「Pydantic SSoT → 境界別 artifact」の 2 本柱を構成する（ADR 0006）。
#
# 実行方法:
#   uv run python -m scripts.export_job_schemas
#   （mise タスク: mise run api:job-schemas-export）

import importlib
import json
import pkgutil
import re
import sys
from pathlib import Path

from pydantic import BaseModel

# app.schemas.jobs パッケージを起点に再帰 import するための import。
import app.schemas.jobs as jobs_pkg


def camel_to_kebab(name: str) -> str:
    # CamelCase → kebab-case 変換。
    # 例: GradingJob → grading-job / HTMLParser → html-parser
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1-\2", name)
    s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s1)
    return s2.lower()


def collect_job_payload_classes() -> list[type[BaseModel]]:
    # app.schemas.jobs 配下を再帰的に import し、各モジュール内の
    # BaseModel subclass のうち、クラス名が "JobPayload" で終わるものを返す。
    found: list[type[BaseModel]] = []
    seen: set[type] = set()

    for module_info in pkgutil.walk_packages(
        jobs_pkg.__path__, prefix=f"{jobs_pkg.__name__}."
    ):
        module = importlib.import_module(module_info.name)
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if not isinstance(obj, type):
                continue
            if obj is BaseModel or not issubclass(obj, BaseModel):
                continue
            if not obj.__name__.endswith("JobPayload"):
                continue
            if obj in seen:
                continue
            seen.add(obj)
            found.append(obj)

    return found


def main() -> int:
    # apps/api/ ディレクトリ（このスクリプトの 1 階層上の親）
    api_root = Path(__file__).resolve().parent.parent
    output_dir = api_root / "job-schemas"
    output_dir.mkdir(parents=True, exist_ok=True)

    classes = collect_job_payload_classes()

    if not classes:
        print(
            "wrote 0 schemas（対象クラスなし、"
            "apps/api/app/schemas/jobs/ に *JobPayload を追加すると自動収集される）"
        )
        return 0

    wrote = 0
    skipped = 0
    for cls in classes:
        # クラス名末尾の "JobPayload" を落とし、kebab-case にする。
        base = cls.__name__.removesuffix("JobPayload")
        file_name = f"{camel_to_kebab(base)}.schema.json"
        output_path = output_dir / file_name

        schema = cls.model_json_schema()
        payload = json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

        if output_path.exists() and output_path.read_text(encoding="utf-8") == payload:
            skipped += 1
            continue

        output_path.write_text(payload, encoding="utf-8")
        wrote += 1
        print(f"wrote apps/api/job-schemas/{file_name} ({len(payload)} bytes)")

    print(f"summary: wrote {wrote}, unchanged {skipped}, total {len(classes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
