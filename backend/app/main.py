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
        if settings.reseed_products:
            from app.products.seed_loader import reseed_products
            n = reseed_products(db)
            import logging
            logging.warning("VC_RESEED on — product pool force-reloaded from seed (%d items). "
                            "Turn this env off after deploy.", n)
        elif settings.seed_upsert:
            from app.products.seed_loader import upsert_seed_products
            n = upsert_seed_products(db)
            import logging
            logging.warning("VC_SEED_UPSERT on — %d new products added; existing products + "
                            "impressions/feedback preserved. Turn this env off after.", n)
        else:
            load_seed_products(db)
        load_seed_concepts(db)
        from app.products.search_index import build_index
        build_index(db)
        # 의미 검색용 상품 임베딩 (디스크 캐시 우선; mock/무키면 no-op → BM25 폴백)
        from app.products import embeddings
        from app.db import models
        embeddings.ensure_product_vectors(db.query(models.Product).all())
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

from fastapi import Depends  # noqa: E402

from app.api import conflicts, exports, feedback, meta, preferences, pscon, research, sessions, simulations, study, synthesis, turns  # noqa: E402
from app.core.research_gate import require_research_key  # noqa: E402

# ── 참가자 스터디 플로우 (항상 마운트) ─────────────────────────────────
app.include_router(sessions.router)
app.include_router(turns.router)
app.include_router(feedback.router)
app.include_router(conflicts.router)
app.include_router(preferences.router)
app.include_router(meta.router)
app.include_router(study.router)

# ── 연구자 읽기 표면 (항상 마운트하되 키로 보호 — research_gate 규칙 참조) ──
# 라이브 모니터링·download_study_sessions.py가 키를 들고 계속 쓸 수 있게 한다.
app.include_router(research.router, dependencies=[Depends(require_research_key)])
app.include_router(exports.router, dependencies=[Depends(require_research_key)])

# ── 연구 전용 (스터디 배포에서는 아예 마운트 안 함 → 404) ─────────────────
# 시뮬레이션·합성은 세션을 "쓰는" 표면이라, study 모드에서 빼는 것으로
# 참가자 DB에 시뮬 데이터가 섞이는 일이 구조적으로 불가능해진다.
if settings.app_mode != "study":
    app.include_router(simulations.router)
    app.include_router(pscon.router)
    app.include_router(synthesis.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "llmProvider": settings.llm_provider}
