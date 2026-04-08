from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.config import DATABASE_PATH
from backend.database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(DATABASE_PATH)
    yield

app = FastAPI(title="Game Studio Sub-Agents", version="0.1.0", lifespan=lifespan)

@app.get("/api/health")
async def health():
    return {"status": "ok"}
