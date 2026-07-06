"""하이브리드 검색 A/B — α∈{0, 0.3, 0.5}의 retrieval 풀 품질을 결정론 비교 (2026-07-06).

전체 파이프라인 스윕은 planner/rerank의 LLM 비결정성이 노이즈이므로, 여기서는 검색만
분리한다: 고정 쿼리(스윕 24케이스의 발화 원문) → search_products(pool 30) → 풀의
카테고리 정합률을 기계 채점. LLM chat 호출 0 (쿼리 임베딩만 케이스×α당 1회).

metric:
- fit@30: 풀 30 중 기대 카테고리 비율 (기대 카테고리 있는 20케이스)
- poison: 알려진 오염(가방→노트북, 주얼리→캔들 등)의 풀 내 개수

  cd backend && VC_SEED_DIR=seed_amazon VC_LLM_PROVIDER=deepseek PYTHONPATH=. \
      .venv/bin/python scripts/ab_hybrid_retrieval.py
출력: data/ab_hybrid_retrieval.json + 콘솔 표
"""
import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("VC_SEED_DIR", str(BACKEND / "seed_amazon"))
os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_ab_"), "ab.db"))

ALPHAS = [0.0, 0.3, 0.5]

# (id, 유형, 기대 카테고리들, 쿼리(발화 원문), 오염 카테고리(있다면))
CASES = [
    ("a1", "직접지목", ["시계"], "가볍게 찰 손목시계 추천해줘", None),
    ("a2", "직접지목", ["스커트"], "여름에 입을 스커트 찾고 있어요", None),
    ("a3", "직접지목", ["모니터"], "사무용 모니터 하나 추천해주세요", None),
    ("a4", "직접지목", ["텀블러·머그"], "텀블러 하나 사려고요", None),
    ("b1", "맥락어", ["주얼리"], "여자친구 생일 선물로 주얼리를 찾고 있어요. 너무 저렴해 보이는 건 싫어요", "캔들·디퓨저"),
    ("b2", "맥락어", ["캔들·디퓨저"], "집들이 선물로 캔들이나 디퓨저 추천해줘", None),
    ("b3", "맥락어", ["스카프·머플러"], "어머니 생신 선물로 스카프 알아보고 있어요", None),
    ("b4", "맥락어", ["스마트워치"], "아버지 은퇴 선물로 스마트워치 어떨까 해서요", None),
    ("c1", "크로스", ["가방·핸드백"], "출퇴근할 때 노트북 넣고 다닐 가방을 찾고 있어요", "노트북"),
    ("c2", "크로스", ["양말"], "러닝화 신을 때 신을 양말 추천해줘", "샌들"),
    ("c3", "크로스", ["키보드·마우스"], "맥북이랑 같이 쓸 키보드 찾아요", "노트북"),
    ("c4", "크로스", ["지갑"], "카드 많이 들어가는 지갑 찾고 있어요. 휴대폰도 같이 들어가면 좋고요", None),
    ("c5", "크로스", ["가방·핸드백"], "아이패드 케이스 찾아요", "태블릿"),  # 풀밖(케이스 없음) — 최소한 태블릿 본체·아동복은 아니어야
    ("d1", "부정제약", ["청바지"], "청바지 찾는데 스키니는 싫어요", None),
    ("d2", "부정제약", ["니트·스웨터"], "니트 사고 싶은데 따가운 소재는 싫어요", None),
    ("d3", "부정제약", ["샌들"], "여름 샌들 찾는데 굽 높은 건 싫어요", None),
    ("d4", "부정제약", ["원피스"], "원피스 찾고 있어요. 화려한 무늬는 싫고 단색이 좋아요", None),
    ("e1", "속성제약", ["반바지"], "무릎 위로 오는 여름 반바지 추천해줘", None),
    ("e2", "속성제약", ["수영복"], "래시가드 스타일 수영복 찾아요", None),
    ("e3", "속성제약", ["후드·맨투맨"], "기모 있는 따뜻한 후드티 추천해줘", None),
    ("e4", "속성제약", ["블루투스 스피커"], "캠핑에서 쓸 방수 블루투스 스피커 추천해주세요", None),
    ("f1", "선물가격", ["지갑"], "남자친구 선물로 10만원대 지갑 보고 있어요", None),
    ("f2", "선물가격", ["텀블러·머그"], "회사 동료 선물로 부담 없는 머그컵 추천해줘", None),
    ("f3", "선물가격", ["시계"], "부모님 선물로 고급스러운 시계 찾고 있어요", None),
]


def main():
    from app.db.database import SessionLocal, engine
    from app.db import models
    models.Base.metadata.create_all(engine)
    from app.products.seed_loader import load_seed_products
    from app.products.search_index import build_index
    from app.products import embeddings
    from app.products.search import search_products

    db = SessionLocal()
    load_seed_products(db)
    prods = db.query(models.Product).all()
    build_index(db)
    embeddings.ensure_product_vectors(prods)
    assert embeddings.enabled(), "임베딩 비활성 — OPENAI_API_KEY/provider 확인"
    print(f"상품 {len(prods)} · 케이스 {len(CASES)} · α {ALPHAS}\n", flush=True)

    results = []
    for cid, kind, cats, query, poison in CASES:
        row = {"id": cid, "kind": kind, "expected": cats, "query": query, "poison": poison, "alphas": {}}
        for a in ALPHAS:
            pool = search_products(db, query=query, category=None, hard_constraints=[],
                                   return_pool=True, pool_size=30, alpha=a)
            fit = sum(1 for sp in pool if sp.product.category in cats)
            n_poison = sum(1 for sp in pool if poison and sp.product.category == poison)
            row["alphas"][str(a)] = {
                "fit30": fit, "fitRatio": round(fit / max(len(pool), 1), 3),
                "poisonCount": n_poison,
                "top5": [f"[{sp.product.category}] {sp.product.title[:30]}" for sp in pool[:5]],
            }
        results.append(row)
        fits = " | ".join(f"α={a}: {row['alphas'][str(a)]['fit30']:2d}/30" for a in ALPHAS)
        print(f"[{cid}] {kind:5s} {fits}  {query[:30]}", flush=True)

    outp = BACKEND / "data" / "ab_hybrid_retrieval.json"
    outp.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")

    # 요약: α별 평균 fit / 유형별 / 오염 총량
    print("\n=== α별 평균 fit@30 (전체 / 유형별) ===")
    from collections import defaultdict
    for a in ALPHAS:
        overall = sum(r["alphas"][str(a)]["fitRatio"] for r in results) / len(results)
        by_kind = defaultdict(list)
        for r in results:
            by_kind[r["kind"]].append(r["alphas"][str(a)]["fitRatio"])
        kinds = " ".join(f"{k}={sum(v)/len(v):.2f}" for k, v in by_kind.items())
        poison_total = sum(r["alphas"][str(a)]["poisonCount"] for r in results if r["poison"])
        print(f"  α={a}: 전체 {overall:.3f} | {kinds} | 오염합계 {poison_total}")
    print(f"\n→ {outp}")


if __name__ == "__main__":
    main()
