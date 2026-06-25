"""카테고리 하드필터 제거 회귀 테스트.

버그: 발화는 모니터를 원하는데 detect_category가 문장 속 '노트북'을 집어
search가 category=='노트북'으로 하드필터 → 임베딩/BM25가 올린 모니터를 제거한다.
하드필터를 빼면, 검색 적합도(여기선 BM25)가 올린 모니터가 풀에 남아야 한다.

임베딩은 mock/미로드 시 자동 비활성 → BM25 경로를 탄다(외부 호출 없음).
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
        models.Product(id="m1", title="LG 27인치 모니터 FHD 사무용", category="모니터",
                       tags=["모니터"], description="노트북과 함께 쓰기 좋은 사무용 모니터"),
        models.Product(id="l1", title="삼성 갤럭시북 노트북", category="노트북",
                       tags=["노트북"], description="사무용 노트북"),
        models.Product(id="l2", title="LG 그램 노트북", category="노트북",
                       tags=["노트북"], description="가벼운 노트북"),
    ])
    session.commit()
    search_index.build_index(session)
    yield session
    session.close()


def test_monitor_query_keeps_monitors_despite_wrong_detected_category(db):
    # query는 실제 파이프라인처럼 발화 + 시나리오 카테고리("모니터")를 포함한다.
    # category 인자는 detect_category가 잘못 집은 "노트북"(버그 상황).
    pool = search_products(
        db,
        query="나 모니터 사고 싶어 노트북이랑 같이 쓰게 모니터",
        category="노트북",
        hard_constraints=[], soft_preferences=[], topic_labels=[], avoidances=[],
        return_pool=True, pool_size=15,
    )
    cats = {sp.product.category for sp in pool}
    assert "모니터" in cats, f"모니터가 추천 풀에서 빠짐(카테고리 하드필터 탓). got={cats}"


def test_embedding_path_keeps_monitor_despite_wrong_category(db, monkeypatch):
    # 임베딩 경로 시뮬레이션: 코사인 검색이 모니터를 1위로 올렸다고 가정한다.
    # 하드필터가 살아있으면 category=="노트북"이 이 모니터를 제거한다(버그).
    monkeypatch.setattr(
        embeddings, "retrieve_scored",
        lambda q, n=200: [("m1", 0.92), ("l1", 0.51), ("l2", 0.40)],
    )
    pool = search_products(
        db,
        query="노트북이랑 같이 쓸 모니터",
        category="노트북",
        hard_constraints=[], soft_preferences=[], topic_labels=[], avoidances=[],
        return_pool=True, pool_size=15,
    )
    cats = {sp.product.category for sp in pool}
    assert "모니터" in cats, f"임베딩이 1위로 올린 모니터를 하드필터가 제거함. got={cats}"


def test_search_falls_back_when_retrieved_ids_missing_from_db(db, monkeypatch):
    """인덱스/임베딩이 DB에 없는 id를 돌려줘도(재시드 등 불일치) 추천 풀이 비면 안 된다 → 전체 폴백.
    버그 증상: recommend인데 카드 0개 = search_products가 빈 풀을 반환."""
    monkeypatch.setattr(embeddings, "retrieve_scored",
                        lambda q, n=200: [("ghost1", 0.9), ("ghost2", 0.8)])  # DB에 없는 id
    pool = search_products(
        db, query="모니터", category="노트북",
        hard_constraints=[], soft_preferences=[], topic_labels=[], avoidances=[],
        return_pool=True, pool_size=15,
    )
    assert pool, "retrieve가 DB에 없는 id만 줘도 추천 풀이 비면 안 됨(폴백 필요)"
