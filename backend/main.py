from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import DATABASE_PATH
from backend.database import init_db
from backend.routes.projects import router as projects_router
from backend.routes.tickets import router as tickets_router
from backend.routes.agents import router as agents_router
from backend.routes.runs import router as runs_router
from backend.routes.usage import router as usage_router
from backend.routes.providers import router as providers_router
from backend.routes.documents import router as documents_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db(DATABASE_PATH)
    yield

app = FastAPI(title="Game Studio Sub-Agents", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects_router)
app.include_router(tickets_router)
app.include_router(agents_router)
app.include_router(runs_router)
app.include_router(usage_router)
app.include_router(providers_router)
app.include_router(documents_router)

@app.get("/api/health")
async def health():
    return {"status": "ok"}
