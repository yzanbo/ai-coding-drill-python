from fastapi import FastAPI

app = FastAPI(title="AI Coding Drill API")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
