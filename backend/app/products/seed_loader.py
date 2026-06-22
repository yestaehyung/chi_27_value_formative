"""Load seed products / scenarios / personas (spec §23, §12)."""
import json
from functools import lru_cache

from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.db import models
from app.products.cue_extractor import build_cue_summary


def reseed_products(db: DbSession) -> int:
    """상품 풀을 시드로 강제 교체 (VC_RESEED=1 전용).

    상품(Product)과 그에 딸린 노출(ProductImpression)만 비운다 — 참가자·세션·
    턴·설문·피드백 같은 연구 데이터는 절대 건드리지 않는다. 임베딩 캐시도 함께
    무효화해 새 상품 기준으로 다시 로드되게 한다.
    배포 볼륨처럼 '이미 상품이 있어 시드를 안 읽는' DB를 갱신할 때 쓴다.
    """
    db.query(models.ProductImpression).delete(synchronize_session=False)
    db.query(models.Product).delete(synchronize_session=False)
    db.commit()
    # 디스크 임베딩 캐시 무효화 — 다음 ensure_product_vectors가 새로 로드/생성하게
    try:
        cache = settings.seed_dir / "product_vectors.json"
        # repo에 커밋된 캐시는 남기되, 상품 id가 바뀌면 ensure_product_vectors가
        # id 집합 불일치로 알아서 재생성한다. (여기선 in-memory 플래그만 리셋)
        from app.products import embeddings
        embeddings._loaded = False
        embeddings._product_vectors.clear()
        _ = cache  # 캐시 파일 자체는 보존 (id 일치 시 재사용)
    except Exception:  # noqa: BLE001
        pass
    return load_seed_products(db)


def load_seed_products(db: DbSession) -> int:
    if db.query(models.Product).count() > 0:
        return 0
    raw = json.loads((settings.seed_dir / "products.json").read_text(encoding="utf-8"))
    # 카테고리 상대 분위수 기반 priceCue (cueSummary가 명시되지 않은 상품용)
    prices_by_category: dict[str, list[int]] = {}
    for item in raw:
        if item.get("price"):
            prices_by_category.setdefault(item.get("category", ""), []).append(item["price"])
    for item in raw:
        cue = item.get("cueSummary") or build_cue_summary(
            item, prices_by_category.get(item.get("category", ""))
        )
        db.add(models.Product(
            id=item["id"],
            title=item["title"],
            category=item.get("category"),
            brand=item.get("brand"),
            price=item.get("price"),
            list_price=item.get("listPrice"),
            discount_rate=item.get("discountRate"),
            delivery_fee=item.get("deliveryFee"),
            rating=item.get("rating"),
            review_count=item.get("reviewCount"),
            long_term_review_ratio=item.get("longTermReviewRatio"),
            recent_sales_count=item.get("recentSalesCount"),
            seller_name=item.get("sellerName"),
            seller_grade=item.get("sellerGrade"),
            seller_years=item.get("sellerYears"),
            image_url=item.get("imageUrl"),
            product_url=item.get("productUrl"),
            attributes=item.get("attributes") or {},
            tags=item.get("tags") or [],
            description=item.get("description"),
            cue_summary=cue,
        ))
    db.commit()
    return len(raw)


def load_seed_concepts(db: DbSession) -> int:
    """Top-down seed concepts (이론모듈 §5.3, §11.4) — status='seed', origin=['top_down_seed']."""
    from app.core.ids import new_id

    path = settings.seed_dir / "concepts.json"
    if not path.exists():
        return 0
    raw = json.loads(path.read_text(encoding="utf-8"))
    created = 0
    for item in raw:
        exists = (
            db.query(models.Concept)
            .filter(models.Concept.normalized_label == item["normalizedLabel"])
            .first()
        )
        if exists:
            # 기존(데이터 유래) concept에 seed 메타데이터 보강
            if "top_down_seed" not in (exists.origin or []):
                exists.origin = (exists.origin or []) + ["top_down_seed"]
            exists.description = exists.description or item.get("definition")
            exists.user_visible_label = exists.user_visible_label or item.get("userVisibleLabel")
            exists.sme_translation = exists.sme_translation or item.get("smeTranslation", [])
            exists.scenario_scope = exists.scenario_scope or item.get("scenarioScope", [])
            continue
        db.add(models.Concept(
            id=new_id("concept"),
            label=item["label"],
            normalized_label=item["normalizedLabel"],
            description=item.get("definition"),
            aliases=item.get("aliases", []),
            source_topic_ids=[],
            created_by="top_down_seed",
            status="seed",
            origin=["top_down_seed"],
            version=1.0,
            scenario_scope=item.get("scenarioScope", []),
            user_visible_label=item.get("userVisibleLabel"),
            sme_translation=item.get("smeTranslation", []),
        ))
        created += 1
    db.commit()
    return created


@lru_cache(maxsize=1)
def load_scenarios() -> list[dict]:
    return json.loads((settings.seed_dir / "scenarios.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_personas() -> list[dict]:
    """Simulation persona pool. Prefer the sampled Nemotron-Personas-Korea pool
    (seed/personas_nemotron.json); fall back to the hand-authored trait personas.
    Used by the simulation only — the study/shopping flow does not read personas."""
    nemotron = settings.seed_dir / "personas_nemotron.json"
    path = nemotron if nemotron.exists() else (settings.seed_dir / "personas.json")
    return json.loads(path.read_text(encoding="utf-8"))


def get_scenario(scenario_id: str) -> dict | None:
    return next((s for s in load_scenarios() if s["id"] == scenario_id), None)


def get_persona(persona_id: str) -> dict | None:
    found = next((p for p in load_personas() if p["id"] == persona_id), None)
    if found is not None:
        return found
    # Nemotron 풀이 기본 목록이지만, 수작업 trait persona(ua_*)는 결정론적
    # 데모/테스트가 계속 참조한다 — id로 직접 요청되면 hand-authored 풀에서도 찾는다.
    fallback = settings.seed_dir / "personas.json"
    if fallback.exists():
        hand_authored = json.loads(fallback.read_text(encoding="utf-8"))
        return next((p for p in hand_authored if p["id"] == persona_id), None)
    return None
