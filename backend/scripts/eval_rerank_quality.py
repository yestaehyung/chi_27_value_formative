"""rerank 집행 품질 평가 — 위반품이 노출 5개에 새는지 기계 채점 (2026-07-06).

searchText 평가와 반대로, 여기선 **일부러 어려운 풀**(오염 쿼리로 검색)을 고정 입력으로
주고 rerank가 constraintsNote·criteria를 노출 셋에서 집행하는지 잰다. 체커는 전부
기계식(가격 산수·카테고리 필드·제목/속성 키워드) — LLM judge 없음.

측정치 (케이스별):
- violationsShown: 노출 셋 중 **비공지** 제약 위반 수 (주 지표, 낮을수록 좋음).
  ② 부분 정직(2026-07-07) 이후 노출은 프로덕션 select_shown 경로 그대로이며,
  nearMiss로 고지된 근접 대안은 위반으로 세지 않는다 — 죄는 '몰래 채우기'뿐.
- compliantInPool: 풀 30 중 비위반 후보 수 — rerank가 이길 수 *있었는지* 맥락
- score = 1 - violations / min(5, max(compliant,1)); compliant=0이면 비공지 위반이
  없을 때 1.0 (정직 경로 작동), 있으면 0.0

  cd backend && VC_SEED_DIR=seed_amazon VC_LLM_PROVIDER=deepseek VC_DEEPSEEK_MODEL=deepseek-v4-flash \
      PYTHONPATH=. LABEL=baseline .venv/bin/python scripts/eval_rerank_quality.py
출력: data/rerank_eval_{LABEL}.json
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("VC_SEED_DIR", str(BACKEND / "seed_amazon"))
os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_rrk_"), "r.db"))

LABEL = os.environ.get("LABEL", "run")


def _txt(p, prof):
    return (p.title or "") + " " + " ".join((prof or {}).get("keyAttributes") or []) + " " + ((prof or {}).get("productType") or "")


# (id, 풀 쿼리(일부러 원문·오염 포함), intent_ctx, 위반 판정 함수(product, profile)->bool, 설명)
def CASES():
    return [
        ("r1_스키니", "청바지 찾는데 스키니는 싫어요",
         {"recentUtterances": ["청바지 찾는데 스키니는 싫어요"], "statedConstraintsNote": "스키니 핏은 싫어함", "criteria": []},
         lambda p, pr: "스키니" in _txt(p, pr), "스키니 노출 = 위반"),
        ("r2_가격미만", "원피스",
         {"recentUtterances": ["원피스 보여줘", "더 저렴한 걸로 보여줘"], "statedConstraintsNote": "가격 16,200원 미만 위주로", "criteria": []},
         lambda p, pr: (p.price or 0) >= 16200, "16200원 이상 = 위반"),
        ("r3_복합", "방수 스마트워치",
         {"recentUtterances": ["방수 되는 스마트워치 30만원 이하로 찾아줘. 애플은 비싸서 빼주세요"], "statedConstraintsNote": "30만원 이하, 애플 제외, 방수 필수", "criteria": []},
         lambda p, pr: (p.price or 0) > 300000 or "애플" in (p.title or "") or "Apple" in (p.title or ""), "30만 초과/애플 = 위반"),
        ("r4_커널형", "무선이어폰",
         {"recentUtterances": ["무선이어폰 추천해줘", "10만원 이하로. 귀에 꽂는 커널형은 싫어요"], "statedConstraintsNote": "10만원 이하, 커널형(인이어)은 싫어함", "criteria": []},
         lambda p, pr: (p.price or 0) > 100000 or any(k in _txt(p, pr) for k in ("커널", "인이어")), "10만 초과/커널형 = 위반"),
        ("r5_캔들제외", "집들이 선물",
         {"recentUtterances": ["집들이 선물 추천해줘. 캔들 말고 다른 걸로"], "statedConstraintsNote": "캔들·디퓨저는 제외", "criteria": []},
         lambda p, pr: p.category == "캔들·디퓨저", "캔들 카테고리 = 위반"),
        ("r6_무늬제외", "원피스 단색",
         {"recentUtterances": ["원피스 찾고 있어요. 화려한 무늬는 싫고 단색이 좋아요"], "statedConstraintsNote": "화려한 무늬 제외, 단색 위주", "criteria": []},
         lambda p, pr: any(k in _txt(p, pr) for k in ("플로럴", "프린트", "패턴", "체크", "도트", "무늬")), "무늬 계열 = 위반"),
        ("r7_종류정합", "출퇴근할 때 노트북 넣고 다닐 가방을 찾고 있어요",
         {"recentUtterances": ["출퇴근할 때 노트북 넣고 다닐 가방을 찾고 있어요"], "statedConstraintsNote": "가방이어야 함 (노트북 본체 아님), 노트북 수납", "criteria": []},
         lambda p, pr: p.category != "가방·핸드백", "가방 아닌 카테고리 = 위반"),
        ("r8_가격상한", "시계",
         {"recentUtterances": ["동생 생일 선물로 5만원 이하 시계 찾아요"], "statedConstraintsNote": "5만원 이하", "criteria": []},
         lambda p, pr: (p.price or 0) > 50000, "5만 초과 = 위반"),
        # ② 수용 테스트 (2026-07-07): 카탈로그에 남성 버뮤다 0개 — compliantInPool=0에서
        # 비공지 위반 0(전부 exclude→nearMiss 고지)이면 정직 경로 작동 = 1.0.
        ("r9_버뮤다_공급0", "남성용 데님 버뮤다 팬츠",
         {"recentUtterances": ["남자 데님 버뮤다 팬츠 찾고 있어요"], "statedConstraintsNote": "남성용, 버뮤다(무릎 기장) 데님", "criteria": []},
         lambda p, pr: "버뮤다" not in _txt(p, pr) or "여성" in ((pr or {}).get("audience") or ""),
         "버뮤다 아님/여성용 = 위반"),
    ]


def main():
    from app.db.database import SessionLocal, engine
    from app.db import models
    models.Base.metadata.create_all(engine)
    from app.products.seed_loader import load_seed_products
    from app.products.search_index import build_index
    from app.products import embeddings, profiles
    from app.products.search import search_products
    from app.agents import response_generator as rg
    from app.agents.recommender import select_shown
    from app.llm.provider import get_provider

    db = SessionLocal()
    load_seed_products(db)
    build_index(db)
    embeddings.ensure_product_vectors(db.query(models.Product).all())
    provider = get_provider()

    async def one(cid, pool_q, ctx, is_violation, desc):
        pool = search_products(db, query=pool_q, category=None, hard_constraints=[],
                               return_pool=True, pool_size=30, alpha=0.3)
        compliant = sum(1 for sp in pool if not is_violation(sp.product, profiles.get(sp.product.id)))
        reranked, cards, excluded = await rg.rerank_by_intent(provider, pool, ctx)
        # 노출은 프로덕션 경로 그대로 (② select_shown) — 죄는 '비공지 위반'만:
        # nearMiss로 고지된 근접 대안은 위반으로 세지 않는다 (부분 정직의 채점 정의).
        shown, near_miss = select_shown(reranked, excluded, top_k=5)
        viols = [sp.product.title[:36] for sp in shown
                 if is_violation(sp.product, profiles.get(sp.product.id))
                 and sp.product.id not in near_miss]
        denom = min(5, max(compliant, 1))
        score = max(0.0, 1 - len(viols) / denom) if compliant else (1.0 if not viols else 0.0)
        return {"cid": cid, "desc": desc, "poolSize": len(pool), "compliantInPool": compliant,
                "llmExcludedCount": len(excluded),  # LLM의 exclude 판정 수 — 진동 진단용
                "shownCount": len(shown), "nearMissShown": len(near_miss),
                "violationsShown": len(viols), "violTitles": viols,
                "score": round(score, 3)}

    async def run():
        return [await one(*c) for c in CASES()]

    rows = asyncio.run(run())
    scored = [r for r in rows if r["score"] is not None]
    avg = sum(r["score"] for r in scored) / max(len(scored), 1)
    print(f"\n[{LABEL}] 평균 {avg:.3f} | 총 위반노출 {sum(r['violationsShown'] for r in rows)}")
    for r in rows:
        print(f"  {r['cid']}: 위반 {r['violationsShown']}/5 (풀내 준수후보 {r['compliantInPool']}/30) → {r['score']}"
              + (f"  예: {r['violTitles'][0]}" if r["violTitles"] else ""))
    out = BACKEND / "data" / f"rerank_eval_{LABEL}.json"
    out.write_text(json.dumps({"label": LABEL, "avg": avg, "rows": rows}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
