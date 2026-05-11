from fastapi import APIRouter

# プローブ系エンドポイント（DB / Redis 等の外部依存を持たない軽量 router）。
#
# /healthz: liveness probe（プロセス生存確認）
# - k8s / ALB が定期的に叩き、応答が無ければコンテナを kill して再起動する想定の口。
# - 外部依存（DB / Redis 等）に**触らない**。依存先の一時障害でコンテナ再起動の嵐を
#   引き起こさないために、生存確認と依存疎通は別エンドポイントに分離する。
# - 依存込みの readiness 相当は /health（DB 往復、routers/health.py）が担う。
# - 末尾 `z` は Google 由来の慣習（業務エンドポイントと名前空間が衝突しないための suffix）。
#
# 将来追加する場合：/readyz（DB / Redis を含めた受付可否判定）、/livez 等も本ファイルに同居させる。

router = APIRouter(tags=["probes"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """liveness probe（DB 接続なし）。プロセスが生きていることだけを返す。"""
    return {"status": "ok"}
