"""Public metadata for the participant-facing UI (scenarios, personas, products)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from app.db import models, serializers
from app.db.database import get_db
from app.products.seed_loader import load_personas, load_scenarios

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/scenarios")
def scenarios():
    # ground truth hidden intentions are for user-agent simulation only — not exposed here
    return {
        "scenarios": [
            {k: v for k, v in s.items() if k != "groundTruthHiddenIntentions"}
            for s in load_scenarios()
        ]
    }


@router.get("/personas")
def personas():
    return {"personas": load_personas()}


@router.get("/products")
def products(db: DbSession = Depends(get_db)):
    return {"products": [serializers.product_to_dict(p) for p in db.query(models.Product).all()]}
