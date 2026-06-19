"""ValueCommit Shopping Agent Demo — FastAPI backend (spec §4, §20)."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import logging as _app_logging  # noqa: F401 — configures root logger
from app.core.config import settings
from app.db.database import SessionLocal, init_db
from app.products.seed_loader import load_seed_concepts, load_seed_products


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        load_seed_products(db)
        load_seed_concepts(db)
        from app.products.search_index import build_index
        build_index(db)
    finally:
        db.close()
    yield


app = FastAPI(title="ValueCommit Shopping Agent Demo", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api import conflicts, exports, feedback, meta, preferences, pscon, research, sessions, simulations, study, synthesis, turns  # noqa: E402

app.include_router(sessions.router)
app.include_router(turns.router)
app.include_router(feedback.router)
app.include_router(conflicts.router)
app.include_router(preferences.router)
app.include_router(simulations.router)
app.include_router(research.router)
app.include_router(exports.router)
app.include_router(meta.router)
app.include_router(study.router)
app.include_router(pscon.router)
app.include_router(synthesis.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "llmProvider": settings.llm_provider}
