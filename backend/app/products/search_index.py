"""BM25(FTS5) 상품 검색 인덱스 — '전체 스캔'을 '인덱스 retrieve'로 대체(카탈로그 확장 대비).

retrieve()를 인터페이스로 분리 → 추후 임베딩 rerank 등 더 나은 retriever로 교체 가능.
한국어는 FTS5 'trigram' 토크나이저로 처리(조사·복합어 변형에 강건). retrieve 단계는 recall 우선,
정밀도는 상위 단계(태그 필터·trade-off 랭킹)가 담당한다.
"""
import re

from sqlalchemy import text as _sql
from sqlalchemy.orm import Session as DbSession

from app.db import models

_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")


def _doc(p: models.Product) -> str:
    """FTS 문서 — 임베딩 _product_text와 정합: 프로필이 있으면 정규화 필드를 추가로 색인
    (BM25 폴백 경로에서도 '커널형'·'유선' 같은 정규화 속성이 검색되게)."""
    from app.products import profiles

    tags = " ".join(p.tags or [])
    base = f"{p.title or ''} {tags} {p.description or ''} {p.category or ''}"
    prof = profiles.get(p.id)
    if prof:
        extra = " ".join(filter(None, [
            prof.get("productType") or "", " ".join(prof.get("keyAttributes") or []),
            prof.get("audience") or "",
        ]))
        return f"{base} {extra}"
    return base


def build_index(db: DbSession) -> int:
    """앱 시작 시 호출 — products로 FTS5 인덱스를 (재)구축."""
    db.execute(_sql("DROP TABLE IF EXISTS product_fts"))
    db.execute(_sql(
        "CREATE VIRTUAL TABLE product_fts USING fts5(doc, pid UNINDEXED, tokenize='trigram')"
    ))
    rows = [{"d": _doc(p), "p": p.id} for p in db.query(models.Product).all()]
    if rows:
        db.execute(_sql("INSERT INTO product_fts(doc, pid) VALUES(:d, :p)"), rows)
    db.commit()
    return len(rows)


def index_product(db: DbSession, p: models.Product) -> None:
    """상품 추가/변경 시 해당 pid 행 교체."""
    db.execute(_sql("DELETE FROM product_fts WHERE pid = :p"), {"p": p.id})
    db.execute(_sql("INSERT INTO product_fts(doc, pid) VALUES(:d, :p)"), {"d": _doc(p), "p": p.id})
    db.commit()


def _match_expr(query: str) -> str:
    # 영문/숫자/한글 토큰만 추출해 OR로 결합(따옴표로 감싸 FTS5 연산자 오인 방지).
    toks = [t for t in _TOKEN.findall(query or "") if len(t) >= 2]
    return " OR ".join(f'"{t}"' for t in toks)


def retrieve(db: DbSession, query: str, n: int = 200, category: str | None = None) -> list[str]:
    """BM25 상위 n개 product_id(랭킹순). category 주어지면 JOIN 필터. 매칭 없으면 []."""
    expr = _match_expr(query)
    if not expr:
        return []
    try:
        if category:
            rows = db.execute(_sql(
                "SELECT product_fts.pid FROM product_fts JOIN products ON products.id = product_fts.pid "
                "WHERE product_fts MATCH :q AND products.category = :c "
                "ORDER BY bm25(product_fts) LIMIT :n"
            ), {"q": expr, "c": category, "n": n}).fetchall()
        else:
            rows = db.execute(_sql(
                "SELECT pid FROM product_fts WHERE product_fts MATCH :q "
                "ORDER BY bm25(product_fts) LIMIT :n"
            ), {"q": expr, "n": n}).fetchall()
    except Exception:  # noqa: BLE001 — FTS 미구축/구문 문제는 폴백(빈 결과)로 강등
        return []
    return [r[0] for r in rows]
