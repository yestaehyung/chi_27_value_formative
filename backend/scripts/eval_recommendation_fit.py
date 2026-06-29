"""추천 결과 자동 검증 — deepseek flash로 여러 페르소나를 합성한 뒤, **deepseek 판정자(LLM-judge)**가
각 페르소나의 '숨은 의도'(GT)에 추천 상품이 맞는지 채점한다. 사람(Claude)이 눈으로 보지 않고
deepseek가 채점 = 확장 가능한 자동 검증.

  cd backend && VC_LLM_PROVIDER=deepseek VC_DEEPSEEK_MODEL=deepseek-v4-flash VC_DEEPSEEK_THINKING=off \
      PYTHONPATH=. .venv/bin/python scripts/eval_recommendation_fit.py 12

주의: v2 GT가 데모 시나리오에 묶여 있어 데모 시드(seed/)에서 동작(매칭 시나리오·상품 정합).
"""
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_receval_"), "e.db"))
os.environ.setdefault("VC_EXPORT_DIR", tempfile.mkdtemp(prefix="vc_receval_exp_"))

from app.core.config import settings  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402

SEED = Path(__file__).resolve().parent.parent / "seed"
PROFILES = SEED / "personas_nemotron_profiles_v2.json"
OUT = Path(__file__).resolve().parent.parent / "data" / "rec_eval"
TURNS = int(os.environ.get("VC_EVAL_TURNS", "6"))
CONC = int(os.environ.get("VC_EVAL_CONCURRENCY", "3"))

JUDGE_SYS = (
    "너는 쇼핑 추천 결과를 검증하는 객관적 평가자다. 사용자가 대화에서 직접 말하지 않은 '숨은 의도'"
    "(진짜 결정 기준) 목록과, 에이전트가 최종 추천한 상품들을 본다. 각 숨은 의도가 추천 상품들로 "
    "충족되는지 판정하고, 전체 추천 적합도를 1~5로 매긴다(5=숨은 의도를 잘 반영, 1=전혀 못 맞춤). "
    "상품 특성이 의도와 실제로 맞는지만 본다 — 친절함이나 말투는 보지 않는다.\n"
    '출력 JSON: {"satisfiedIntentions": [충족된 의도 인덱스 정수들], '
    '"missedIntentions": [놓친 인덱스들], "fitScore": 1~5 정수, "reason": "한 문장 근거"}'
)


def select_diverse(profiles: dict, n: int) -> list[dict]:
    order = ["Emotional", "Conditional", "Epistemic", "Social", "Functional"]
    buckets: dict[str, list] = {v: [] for v in order}
    for e in sorted(profiles.values(), key=lambda e: e["personaId"]):
        sid = e.get("matchedScenarioId")
        gt = (e.get("scenarios") or {}).get(sid)
        if not gt:
            continue
        dom = [a for a, lv in (gt.get("valueLevels") or {}).items() if lv == "dominant"]
        rep = next((v for v in order if v in dom), None)
        if rep:
            buckets[rep].append(e)
    picked: list[dict] = []
    while len(picked) < n and any(buckets[v] for v in order):
        for v in order:
            if buckets[v] and len(picked) < n:
                picked.append(buckets[v].pop(0))
    return picked


async def judge_rec(provider, hidden_intentions: list[str], products: list[dict]) -> dict:
    from app.llm.provider import LLMMessage
    ctx = {
        "hiddenIntentions": [f"[{i}] {h}" for i, h in enumerate(hidden_intentions)],
        "recommendedProducts": products,
    }
    out = await provider.generate_json(
        [LLMMessage(role="system", content=JUDGE_SYS),
         LLMMessage(role="user", content=json.dumps(ctx, ensure_ascii=False))],
        task=None,
    )
    return out if isinstance(out, dict) else {}


async def main(n: int) -> None:
    init_db()
    from app.db import models
    from app.products import embeddings
    from app.products.search_index import build_index
    from app.products.seed_loader import (get_persona, get_scenario,
                                          load_seed_concepts, load_seed_products)
    _sdb = SessionLocal()
    load_seed_products(_sdb)
    load_seed_concepts(_sdb)
    build_index(_sdb)
    embeddings.ensure_product_vectors(_sdb.query(models.Product).all())
    _sdb.close()

    from app.agents.llm_user_agent import run_llm_simulation
    from app.llm.provider import get_provider

    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
    picked = select_diverse(profiles, n)
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"[rec-eval] model={settings.deepseek_model} thinking={settings.deepseek_thinking} "
          f"personas={len(picked)} turns={TURNS} conc={CONC}", flush=True)

    sem = asyncio.Semaphore(CONC)
    rows: list[dict] = []

    async def worker(entry: dict) -> None:
        pid = entry["personaId"]
        persona = get_persona(pid)
        sid = entry.get("matchedScenarioId")
        gt = (entry.get("scenarios") or {}).get(sid)
        scenario = get_scenario(sid)
        if not (persona and scenario and gt):
            return
        profile = {**gt, "speechStyle": entry.get("speechStyle")}
        db = SessionLocal()
        try:
            async with sem:
                res = await run_llm_simulation(db, persona, profile, scenario, TURNS, gt_version="v2")
            # 최종 추천 상품 (마지막 recommend 턴 기준, 중복 제거 후 상위 3)
            imps = (db.query(models.ProductImpression)
                    .filter(models.ProductImpression.session_id == res["sessionId"])
                    .order_by(models.ProductImpression.created_at.desc()).all())
            seen, prods = set(), []
            for i in imps:
                if i.product_id in seen:
                    continue
                seen.add(i.product_id)
                p = db.get(models.Product, i.product_id)
                if p:
                    prods.append({"title": p.title, "price": p.price, "cues": p.cue_summary or {}})
                if len(prods) >= 3:
                    break
            hi = gt.get("hiddenIntentions") or []
            verdict = await judge_rec(get_provider(), hi, prods) if prods else {}
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {pid}: {type(e).__name__} {str(e)[:100]}", flush=True)
            return
        finally:
            db.close()
        fit = verdict.get("fitScore")
        sat = verdict.get("satisfiedIntentions") or []
        rate = (len(sat) / len(hi)) if hi else None
        rows.append({
            "personaId": pid, "name": persona.get("name"), "scenario": sid,
            "nProducts": len(prods), "fitScore": fit,
            "intentSatRate": round(rate, 2) if rate is not None else None,
            "reason": verdict.get("reason"), "products": [p["title"] for p in prods],
            "hiddenIntentions": hi,
        })
        print(f"  ✓ {persona.get('name')} × {sid}: fit={fit}/5 "
              f"satRate={round(rate, 2) if rate is not None else None} · {(verdict.get('reason') or '')[:60]}",
              flush=True)

    await asyncio.gather(*(worker(e) for e in picked))

    fits = [r["fitScore"] for r in rows if isinstance(r.get("fitScore"), (int, float))]
    sats = [r["intentSatRate"] for r in rows if r.get("intentSatRate") is not None]
    agg = {
        "model": settings.deepseek_model, "n": len(rows),
        "avgFitScore": round(sum(fits) / len(fits), 2) if fits else None,
        "avgIntentSatRate": round(sum(sats) / len(sats), 2) if sats else None,
        "fitDistribution(1-5)": {s: sum(1 for f in fits if round(f) == s) for s in (1, 2, 3, 4, 5)},
    }
    (OUT / f"rec_fit_{settings.deepseek_model}.json").write_text(
        json.dumps({"aggregate": agg, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n==== 추천 적합도 자동검증 (deepseek-judge, 사람 X) ====", flush=True)
    for k, v in agg.items():
        print(f"  {k}: {v}", flush=True)
    print(f"\n저장: {OUT}/rec_fit_{settings.deepseek_model}.json", flush=True)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 12
    asyncio.run(main(n))
