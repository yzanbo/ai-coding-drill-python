from fastapi import FastAPI

from app.routers import health, probes

app = FastAPI(title="AI Coding Drill API")

app.include_router(probes.router)
app.include_router(health.router)
