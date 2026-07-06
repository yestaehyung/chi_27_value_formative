"""종단 게이트 — 실제 운영 action_decision 프롬프트가 만드는 searchText의 풀 품질 측정.

DSPy 컴파일은 고립된 Signature에서 했으므로(고립-배포 격차), 이식 판정은 반드시
실제 planner 경로(fetch_plan → SYSTEM_BY_TASK["action_decision"])로 잰다.
이식 전/후로 각각 실행해 비교한다. 23케이스 × (flash 1 + 임베딩 1) 호출.

  cd backend && VC_SEED_DIR=seed_amazon VC_LLM_PROVIDER=deepseek VC_DEEPSEEK_MODEL=deepseek-v4-flash \
      PYTHONPATH=. LABEL=preport .venv/bin/python scripts/eval_planner_searchtext.py
출력: data/planner_searchtext_eval_{LABEL}.json + 콘솔 요약
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
os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_gate_"), "g.db"))

LABEL = os.environ.get("LABEL", "run")

# dspy_compile_searchtext.py와 동일 케이스/채점 (단일 진실)
from scripts_cases_shared import CASES  # noqa: E402  (아래에서 생성)


def main():
    from app.db.database import SessionLocal, engine
    from app.db import models
    models.Base.metadata.create_all(engine)
    from app.products.seed_loader import load_seed_products
    from app.products.search_index import build_index
    from app.products import embeddings
    from app.products.search import search_products
    from app.llm.provider import get_provider
    from app.agents import planner

    db = SessionLocal()
    load_seed_products(db)
    build_index(db)
    embeddings.ensure_product_vectors(db.query(models.Product).all())
    provider = get_provider()

    async def one(cid, cats, utt, forbidden):
        ctx = {"recentTurns": [{"role": "user", "content": utt}], "userUtterances": [utt],
               "feedbackEvents": [], "lastShownProducts": [], "values": {}, "motivations": {},
               "ragPrediction": None, "hasRecommendations": False, "lastAgentAction": None,
               "scenarioGoal": ""}
        d = await planner.fetch_plan(provider, ctx, fallback_search_text=utt)
        st = d.search_text or utt
        pool = search_products(db, query=st, category=None, hard_constraints=[],
                               return_pool=True, pool_size=30, alpha=0.3)
        fit = sum(1 for sp in pool if sp.product.category in cats) / max(len(pool), 1)
        dirty = [t for t in forbidden if t in st]
        return {"cid": cid, "action": d.action, "searchText": st,
                "constraintsNote": d.constraints_note, "fit": round(fit, 3),
                "dirtyTokens": dirty, "score": round(max(0.0, fit - (0.6 if dirty else 0)), 3)}

    async def run():
        return [await one(*c) for c in CASES]

    rows = asyncio.run(run())
    avg = sum(r["score"] for r in rows) / len(rows)
    dirty_n = sum(1 for r in rows if r["dirtyTokens"])
    print(f"\n[{LABEL}] 평균 {avg:.3f} | 오염 searchText {dirty_n}/{len(rows)}")
    for r in sorted(rows, key=lambda x: x["score"])[:6]:
        print(f"  최저: {r['cid']} {r['score']} | '{r['searchText'][:36]}' {r['dirtyTokens']}")
    out = BACKEND / "data" / f"planner_searchtext_eval_{LABEL}.json"
    out.write_text(json.dumps({"label": LABEL, "avg": avg, "rows": rows},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"→ {out}")


if __name__ == "__main__":
    main()
