# 役割:
#   FastAPI が起動時にメモリ上で組み立てる OpenAPI 3.1 ドキュメントを、
#   ファイル（apps/api/openapi.json）として固定する。
#   Frontend の型生成（Hey API）と CI の drift 検出から参照する artifact。
#
# 出力先:
#   apps/api/openapi.json（Frontend や CI からはこの 1 ファイルだけを見る）
#
# 設計判断:
#   1) uvicorn で HTTP serve せず、app.openapi() を直接呼ぶ。
#      DB / Redis / GitHub OAuth の起動なしで CI でも空 .env で完走させたいため。
#   2) 整形 JSON（indent=2 + 末尾改行 + キーソート）にする。
#      生成物コミット運用（ADR 0006）では git diff の可読性が必須。
#   3) 既存ファイルと内容が同一なら write を skip して mtime を保つ。
#      git diff ノイズを避けるため。
#
# 相互参照:
#   ジョブ payload 側は export_job_schemas.py（同ディレクトリ）。
#   両者で「Pydantic SSoT → 境界別 artifact」の 2 本柱を構成する（ADR 0006）。
#
# 実行方法:
#   uv run python -m scripts.export_openapi
#   （mise タスク: mise run api:openapi-export）

import json
import sys
from pathlib import Path

# app.main: FastAPI インスタンス（app）を import するだけで OpenAPI dict が取れる。
from app.main import app


def main() -> int:
    # apps/api/ ディレクトリ（このスクリプトの 1 階層上の親）
    api_root = Path(__file__).resolve().parent.parent
    output_path = api_root / "openapi.json"

    # FastAPI 標準 API。OpenAPI 3.1 の dict を返す。
    spec = app.openapi()

    # 整形して文字列化。
    # sort_keys=True: 出力順を機械的に固定し、無意味な順序差分を抑制。
    # ensure_ascii=False: 日本語をそのまま出す（\uXXXX エスケープを避けて diff を読みやすく）。
    payload = json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

    # 既存と同一なら write を skip（mtime を保つ）。
    if output_path.exists() and output_path.read_text(encoding="utf-8") == payload:
        print(f"unchanged apps/api/openapi.json ({len(payload)} bytes)")
        return 0

    output_path.write_text(payload, encoding="utf-8")
    print(f"wrote apps/api/openapi.json ({len(payload)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
