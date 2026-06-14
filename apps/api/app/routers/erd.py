# このファイルの役割：
#   開発者向けに DB スキーマの ER 図 + 各テーブルの物理名 / 論理名を
#   ブラウザで見られる dev 専用 HTML ページ（GET /dev/erd）を提供する。
#
#   中身は app/db/docs.py が SQLAlchemy モデル（= スキーマの唯一の正）から
#   毎リクエスト生成する。モデルを変えればこの画面も即更新される（再生成不要）。
#
#   本番では公開しない：main.py 側で app_env != "production" の時だけ登録する。
#   ドメインのリソース API ではない dev/ops 用ページのため、health / probes と同じく
#   models/db を直接参照する trivial 例外として扱う（→ .claude/rules/backend.md）。

# APIRouter: URL をグループ単位でまとめる箱。
from fastapi import APIRouter

# HTMLResponse: JSON ではなく HTML 文字列をそのまま返すためのレスポンス型。
from fastapi.responses import HTMLResponse

# render_html: モデルの metadata から ER 図 + カラム表の HTML を組み立てる関数。
from app.db.docs import render_html

# prefix="/dev": 開発用ページであることをパスで明示し、リソース系 API と分離する。
router = APIRouter(prefix="/dev", tags=["dev"])


# response_class=HTMLResponse: 既定の JSON ではなく HTML として返す指定（/docs にも反映）。
# include_in_schema=False: dev 専用ページなので OpenAPI（Swagger）には載せない。
@router.get("/erd", response_class=HTMLResponse, include_in_schema=False)
async def get_erd() -> HTMLResponse:
    """DB スキーマの ER 図 + 物理名 / 論理名を表示する HTML を返す。"""
    return HTMLResponse(content=render_html())
