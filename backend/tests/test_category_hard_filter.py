"""세션 카테고리 하드필터 (2026-08-18 복원) — 계약 변경의 기록.

2026-06-23에는 category 인자가 detect_category(발화 추측)에서 와서 오탐이 정답을
지웠고, 필터를 제거하는 게 맞았다. 지금 category는 **세션의 과제 카테고리**
(참가자가 고른 DB 사실)만 들어온다(호출자는 recommender 한 곳) — 검색은 절대
이 카테고리를 넘지 않는다. 라이브 실측(2026-08-18): '사무실·주말용 편한 바지'
1턴에 전역 임베딩이 사무용 의자 5개를 올림 → 바지 세션에 의자 노출.

새 계약: ① 카테고리 지정 시 풀은 그 카테고리만 ② 검색 결과에 그 카테고리가
없어도 타 카테고리로 채우지 않고 카테고리 전체에서 재선별 ③ category=None
(자유 대화·데모)은 종전대로 무필터.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.database import Base
from app.db import models
from app.products import embeddings, search_index
from app.products.search import search_products


@pytest.fixture
def db(monkeypatch):
    # 임베딩 강제 비활성 → BM25 경로(결정론적, 네트워크 없음)
    monkeypatch.setattr(embeddings, "enabled", lambda: False)
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # 단일 연결 → 인메모리 DB + FTS 테이블 일관성 보장
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.add_all([
        models.Product(id="p1", title="편한 스트레이트 치노 팬츠", category="팬츠·바지",
                       tags=[], description="사무실과 주말에 입는 바지"),
        models.Product(id="c1", title="사무용 메쉬 의자 편한 착석감", category="데스크체어",
                       tags=[], description="사무실에서 쓰는 편한 의자"),
        models.Product(id="c2", title="사무용 인체공학 의자", category="데스크체어",
                       tags=[], description="편한 사무용 의자"),
    ])
    session.commit()
    search_index.build_index(session)
    yield session
    session.close()


def test_session_category_is_hard(db, monkeypatch):
    """검색이 타 카테고리(의자)를 위로 올려도 세션 카테고리(바지)만 풀에 남는다."""
    monkeypatch.setattr(
        embeddings, "retrieve_scored",
        lambda q, n=200, include_ids=None: [("c1", 0.93), ("c2", 0.90), ("p1", 0.41)],
    )
    pool = search_products(
        db, query="사무실과 주말에 입을 편한 바지", category="팬츠·바지",
        hard_constraints=[], return_pool=True, pool_size=15,
    )
    cats = {sp.product.category for sp in pool}
    assert cats == {"팬츠·바지"}, f"세션 카테고리 밖 상품이 풀에 들어옴: {cats}"


def test_no_cross_category_fill(db, monkeypatch):
    """검색 결과에 세션 카테고리가 0개여도 타 카테고리로 채우지 않는다 —
    그 카테고리 전체에서 재선별한다."""
    monkeypatch.setattr(
        embeddings, "retrieve_scored",
        lambda q, n=200, include_ids=None: [("c1", 0.95), ("c2", 0.92)],  # 의자만 검색됨
    )
    pool = search_products(
        db, query="편한 사무용", category="팬츠·바지",
        hard_constraints=[], return_pool=True, pool_size=15,
    )
    ids = [sp.product.id for sp in pool]
    assert ids == ["p1"], f"카테고리 전체 재선별이 아니라 타 카테고리 채움: {ids}"


def test_none_category_unfiltered(db):
    """category=None(자유 대화·데모)은 종전대로 무필터 — 검색 적합도가 결정한다."""
    pool = search_products(
        db, query="사무용 의자", category=None,
        hard_constraints=[], return_pool=True, pool_size=15,
    )
    cats = {sp.product.category for sp in pool}
    assert "데스크체어" in cats
