from fastapi import FastAPI

from app.routers import health

app = FastAPI(title="AI Coding Drill API")

app.include_router(health.router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """liveness probe（DB 接続なし）。/health は DB 往復用、こちらはプロセス生存確認用。"""
    return {"status": "ok"}
