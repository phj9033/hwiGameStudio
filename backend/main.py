from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.config import DATABASE_PATH
from backend.database import init_db
from backend.routes.projects import router as projects_router
from backend.routes.tickets import router as tickets_router
from backend.routes.agents import router as agents_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(DATABASE_PATH)
    yield

app = FastAPI(title="Game Studio Sub-Agents", version="0.1.0", lifespan=lifespan)

app.include_router(projects_router)
app.include_router(tickets_router)
app.include_router(agents_router)

@app.get("/api/health")
async def health():
    return {"status": "ok"}
