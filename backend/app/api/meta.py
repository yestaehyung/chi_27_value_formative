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


#: 참가자 선택 화면에 띄울 카테고리 표시 정보. 상품 풀에 실제로 있는 카테고리만 노출되므로
#: (아래 category_options가 DB와 교집합을 낸다) 여기 없는 카테고리는 자동으로 빠진다.
#: 문구는 "무엇을 사는 상황인가"를 참가자가 즉시 알아보게 쓴다 — 시나리오를 폐기한 뒤
#: 과제 설정을 전달하는 유일한 텍스트다(2026-08-06).
CATEGORY_LABELS: dict[str, dict[str, str]] = {
    "블루투스 스피커": {"emoji": "🔊", "blurb": "집·야외에서 쓸 무선 스피커"},
    "티셔츠": {"emoji": "👕", "blurb": "일상에서 입을 티셔츠"},
    "책상": {"emoji": "🪑", "blurb": "작업용 책상"},
    "데스크체어": {"emoji": "💺", "blurb": "오래 앉아 일할 의자"},
    # 2026-08-11 전량 풀 확장으로 추가된 6개 — 모든 카테고리가 blurb를 가져야 한다
    # (일부만 설명이 있으면 선택 화면에서 정보량 비대칭 = 선택 편향).
    "노트북": {"emoji": "💻", "blurb": "작업·학업에 쓸 노트북"},
    "니트·가디건": {"emoji": "🧶", "blurb": "쌀쌀할 때 걸칠 니트와 가디건"},
    "셔츠·블라우스": {"emoji": "👔", "blurb": "단정하게 입을 셔츠·블라우스"},
    "후드·맨투맨": {"emoji": "🧥", "blurb": "편하게 입는 후드·맨투맨"},
    "청바지": {"emoji": "👖", "blurb": "일상에서 입을 데님"},
    "팬츠·바지": {"emoji": "👖", "blurb": "출근·일상용 바지"},
    # 2026-08-13 Amazon Reviews 2023 확장 staging. DB에 실제 상품이 들어온 뒤에만
    # 노출되므로, 프로필/벡터/업서트 전에는 현재 참가자 화면에 영향을 주지 않는다.
    "이어폰": {"emoji": "🎧", "blurb": "음악·통화에 쓸 유선·무선 이어폰"},
    "헤드폰": {"emoji": "🎧", "blurb": "집·이동 중 사용할 헤드폰"},
    "키보드·마우스": {"emoji": "⌨️", "blurb": "작업·게임용 키보드와 마우스"},
    "모니터": {"emoji": "🖥️", "blurb": "업무·게임·영상용 모니터"},
    "스마트워치": {"emoji": "⌚", "blurb": "운동·알림·일상용 스마트워치"},
    "커피테이블": {"emoji": "🛋️", "blurb": "거실에 둘 커피테이블"},
    "책장": {"emoji": "📚", "blurb": "책과 소품을 정리할 책장"},
}


@router.get("/categories")
def category_options(db: DbSession = Depends(get_db)):
    """참가자가 고를 수 있는 쇼핑 카테고리 — **DB에 상품이 실제로 있는 것만**.

    시나리오(scenarios.json)를 대체한다. 이전에는 참가자가 시나리오를 골랐는데, 상품 풀을
    본실험용으로 재구성하면서 옛 시나리오의 카테고리(태블릿·코트 등)에 상품이 0개가 됐다.
    카테고리를 DB에서 직접 읽으면 그런 어긋남이 구조적으로 생기지 않는다.

    `count`는 참가자에게 보여줄 값이 아니라 연구자가 풀 깊이를 확인하기 위한 것이다.
    """
    from sqlalchemy import func

    rows = (
        db.query(models.Product.category, func.count(models.Product.id))
        .filter(models.Product.category.isnot(None))
        .group_by(models.Product.category)
        .all()
    )
    counts = {c: n for c, n in rows}
    # 노출 화이트리스트(VC_OFFERED_CATEGORIES) — 풀에는 더 많은 카테고리가 있어도
    # 스터디 선택지는 지정된 것만 (미설정 = 전체, 기존 동작).
    from app.core.config import settings

    if settings.offered_categories:
        counts = {c: n for c, n in counts.items() if c in settings.offered_categories}
    # CATEGORY_LABELS 순서를 유지한다 — 매번 같은 순서로 보여야 선택 편향이 일정하다.
    # (순서 자체의 편향은 참가자별 카운터밸런싱으로 다룬다.)
    out = [
        {"category": c, "count": counts[c], **meta}
        for c, meta in CATEGORY_LABELS.items() if c in counts
    ]
    # 라벨이 없는 카테고리도 빠뜨리지 않는다 — 풀에 새 카테고리를 넣고 라벨을 깜빡해도
    # 선택지에서 조용히 사라지지 않게.
    out += [
        {"category": c, "count": n, "emoji": "🛍️", "blurb": ""}
        for c, n in sorted(counts.items()) if c not in CATEGORY_LABELS
    ]
    return {"categories": out}


@router.get("/personas")
def personas():
    return {"personas": load_personas()}


@router.get("/products")
def products(db: DbSession = Depends(get_db)):
    return {"products": [serializers.product_to_dict(p) for p in db.query(models.Product).all()]}


@router.get("/product-pool")
def product_pool(db: DbSession = Depends(get_db)):
    """카테고리별 상품 수 — 데모 화면에서 '새 상품이 실제로 DB에 들어왔는지'를 확인한다.
    시드 파일을 바꿔도 `load_seed_products`가 기존 상품이 있으면 스킵하므로(VC_SEED_UPSERT 필요),
    파일이 아니라 **DB 기준**으로 세는 이 값이 실제로 추천될 수 있는 풀이다."""
    from sqlalchemy import func

    rows = (
        db.query(models.Product.category, func.count(models.Product.id))
        .group_by(models.Product.category)
        .order_by(func.count(models.Product.id).desc())
        .all()
    )
    return {
        "total": sum(n for _, n in rows),
        "categories": [{"category": c or "(미분류)", "count": n} for c, n in rows],
    }
