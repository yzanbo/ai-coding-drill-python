# APIRouter: URL をグループ単位でまとめる箱。
from fastapi import APIRouter

# プローブ系エンドポイント（DB / Redis 等の外部依存を持たない軽量 router）。
#
# プローブ:  運用基盤（k8s / ALB 等）が定期的に叩いてアプリの状態を確認するための口。
# liveness:  プロセスが生きているか。NG なら**コンテナを kill して再起動**する。
# readiness: 依存先（DB / Redis）まで含めて受付可能か。
#            NG ならロードバランサから**一時切り離し**する。
#
# 用途を分ける理由：
# - DB 一時切断で liveness を落とすと、再起動しても DB が戻らない限り NG のまま無意味な
#   再起動ループに陥る。だから liveness は依存先を見ない「最も浅い生存確認」に留める。
# - 依存込みの確認は別エンドポイント（/health や将来の /readyz）に分離する。
#
# このファイルで定義しているエンドポイント：
# /healthz: liveness probe（プロセス生存確認）。外部依存に触らず、常に {"status": "ok"} を返す。
#
# 命名規則：
# 末尾 `z`: Google 由来の慣習。業務エンドポイント（/health 等）と名前空間が衝突しないための suffix。
#
# 将来追加する予定：
# /readyz: readiness probe（DB / Redis を含めた受付可否判定）。
# /livez:  liveness の別名（k8s 公式ドキュメントで使われる綴り。揃えるなら検討）。
# いずれも本ファイルに同居させる（routers/health.py は DB 往復を含むため責務が違う）。

# APIRouter: URL をグループ単位でまとめる箱。複数のエンドポイントを 1 つの router に登録し、
#            main.py で app.include_router(router) する流れ。prefix と tags をここで決める。
# APIRouter(tags=["probes"]):
#   - prefix なし: /healthz / /readyz のようにトップレベル直下のパスを使うため
#   - tags:        /docs（Swagger UI）上の見出し名
router = APIRouter(tags=["probes"])


# @router.get("/healthz"): GET /healthz でこの関数が呼ばれるよう登録する。
@router.get("/healthz")
# async def:           非同期関数。DB を待つわけではないが他のエンドポイントと書き方を揃える。
# healthz:             関数名。/docs の見出しや、自動生成される TS クライアントの関数名にもなる。
# -> dict[str, str]:   返り値の型。FastAPI が自動で JSON 化する。
async def healthz() -> dict[str, str]:
    """liveness probe（DB 接続なし）。プロセスが生きていることだけを返す。"""
    # {"status": "ok"}: 固定値。中身に意味は無く「200 が返ること」自体が生存の証。
    return {"status": "ok"}
