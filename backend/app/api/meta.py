"""Public metadata for the participant-facing UI (scenarios, personas, products)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from app.db import models, serializers
from app.db.database import get_db
from app.products.seed_loader import load_personas, load_scenarios

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/scenarios")
def scenarios():
    # 참가자 picker용: 스터디에 제공하는 시나리오(offered)만, studyOrder순.
    # researcher 전용 필드는 비노출 — GT(시뮬용)와 hiddenIntentionMechanism(연구설계 메모)는 §36상
    # 참가자에게 "무엇을 추론 중인지" 알려 편향시키지 않도록 제거. (get_scenario(id)는 전체 유지 — 시뮬 무손상.)
    hide = {"groundTruthHiddenIntentions", "hiddenIntentionMechanism"}
    all_scenarios = load_scenarios()
    offered = [s for s in all_scenarios if s.get("offered")]
    if not offered:  # seed에 플래그가 없으면 빈 picker 방지 — 전체로 폴백
        offered = all_scenarios
    offered = sorted(offered, key=lambda s: s.get("studyOrder", 999))
    return {"scenarios": [{k: v for k, v in s.items() if k not in hide} for s in offered]}


@router.get("/personas")
def personas():
    return {"personas": load_personas()}


@router.get("/products")
def products(db: DbSession = Depends(get_db)):
    return {"products": [serializers.product_to_dict(p) for p in db.query(models.Product).all()]}
