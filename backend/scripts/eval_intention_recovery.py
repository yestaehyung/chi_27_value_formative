"""Intention 복원 평가 — 에이전트가 숨은 의도(TCV5 가치 / H+U 동기)를 대화에서 잘 파악하는가?

핵심 함정(메모리 synthesis-multi-v2): GT가 Functional/Role/Utilitarian로 편향 →
'항상 Functional·Role 찍기' 베이스라인이 그냥 높게 나옴. 그래서:
  1) GT-다양 persona를 고른다(비-Functional dominant 가치 + 희귀 동기 우선).
  2) 점수를 **베이스라인 대비**로 본다(에이전트가 자명한 추측을 넘어서는가).

LLM user agent(숨은 GT로 롤플레이) ↔ 실제 service agent. .env=deepseek.
모델/추론은 환경변수로: VC_DEEPSEEK_MODEL, VC_DEEPSEEK_THINKING, VC_DEEPSEEK_REASONING_EFFORT.

  cd backend && VC_LLM_PROVIDER=deepseek VC_DEEPSEEK_MODEL=deepseek-v4-pro VC_DEEPSEEK_THINKING=on \
      PYTHONPATH=. .venv/bin/python scripts/eval_intention_recovery.py 6
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 임시 DB로 격리 — 데모/스터디 DB 미오염 + 레거시 'Affective'(옛 6-anchor) 행 회피. 앱 import 전 설정.
import tempfile  # noqa: E402
os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_inteval_"), "eval.db"))
os.environ.setdefault("VC_EXPORT_DIR", tempfile.mkdtemp(prefix="vc_inteval_exp_"))

from app.core.config import settings  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402

SEED = Path(__file__).resolve().parent.parent / "seed"
PROFILES = SEED / "personas_nemotron_profiles_v2.json"
OUT = Path(__file__).resolve().parent.parent / "data" / "intention_eval"
TURNS = int(os.environ.get("VC_EVAL_TURNS", "6"))
CONC = int(os.environ.get("VC_EVAL_CONCURRENCY", "3"))
MOT_HI = 0.4  # 복원 동기를 'high로 봄' 임계 (covered_dims 기준과 동일)

VALUES = ["Functional", "Social", "Emotional", "Epistemic", "Conditional"]
BASE_VALUE = "Functional"            # 항상-Functional 베이스라인
BASE_MOT = {"Role", "Utilitarian"}   # 항상-Role/Util 베이스라인


def top_keys(scores: dict, k: int, thr: float = 0.0) -> list[str]:
    return [a for a, v in sorted((scores or {}).items(), key=lambda kv: -kv[1]) if v > thr][:k]


def select_diverse(profiles: dict, n: int) -> list[dict]:
    """matched-scenario GT의 value-dominant 기준으로 버킷 → 희귀(Emotional>Conditional>Epistemic>Social>Functional)
    우선 라운드로빈. 결정론(정렬, 난수 없음)."""
    order = ["Emotional", "Conditional", "Epistemic", "Social", "Functional"]
    buckets: dict[str, list] = {v: [] for v in order}
    for entry in sorted(profiles.values(), key=lambda e: e["personaId"]):
        sid = entry.get("matchedScenarioId")
        gt = (entry.get("scenarios") or {}).get(sid)
        if not gt:
            continue
        dom = [a for a, lv in (gt.get("valueLevels") or {}).items() if lv == "dominant"]
        # 대표 dominant = order상 가장 희귀한 것
        rep = next((v for v in order if v in dom), None)
        if rep:
            buckets[rep].append(entry)
    picked: list[dict] = []
    while len(picked) < n and any(buckets[v] for v in order):
        for v in order:
            if buckets[v] and len(picked) < n:
                picked.append(buckets[v].pop(0))
    return picked


def score_one(gt: dict, anchor_scores: dict, motivation_scores: dict) -> dict:
    val_dom = [a for a, lv in (gt.get("valueLevels") or {}).items() if lv == "dominant"]
    mot_hi = [d for d, lv in (gt.get("motivationLevels") or {}).items() if lv == "high"]
    rec_v1 = top_keys(anchor_scores, 1, 0.0)
    rec_v2 = top_keys(anchor_scores, 2, 0.0)
    rec_mot = {d for d, v in (motivation_scores or {}).items() if (v or 0) >= MOT_HI}

    val_hit1 = bool(set(val_dom) & set(rec_v1))
    val_hit2 = bool(set(val_dom) & set(rec_v2))
    non_func = bool(set(val_dom) - {"Functional"})           # 비자명 케이스인가
    mot_recall = (len(set(mot_hi) & rec_mot) / len(mot_hi)) if mot_hi else None
    # precision: 복원한 high 동기 중 실제 GT-high 비율 (과다발화 탐지 — recall=1.0 함정 보정)
    mot_prec = (len(set(mot_hi) & rec_mot) / len(rec_mot)) if rec_mot else None
    base_v = (BASE_VALUE in val_dom)                          # 항상-Functional가 맞히는가
    base_m = (len(set(mot_hi) & BASE_MOT) / len(mot_hi)) if mot_hi else None
    return {
        "gtValueDominant": val_dom, "recoveredValueTop2": rec_v2,
        "valueHit@1": val_hit1, "valueHit@2": val_hit2, "nonFunctionalCase": non_func,
        "gtMotivationHigh": mot_hi, "recoveredMotHigh": sorted(rec_mot),
        "motRecall": mot_recall, "motPrecision": mot_prec,
        "baselineValueHit": base_v, "baselineMotRecall": base_m,
    }


async def main(n: int) -> None:
    init_db()
    # 신선한 temp DB → 프로덕션 startup과 동일하게 시드/FTS색인/임베딩벡터 구축.
    from app.db import models
    from app.products import embeddings
    from app.products.search_index import build_index
    from app.products.seed_loader import (load_seed_concepts, load_seed_products)
    _sdb = SessionLocal()
    load_seed_products(_sdb)
    load_seed_concepts(_sdb)
    build_index(_sdb)
    embeddings.ensure_product_vectors(_sdb.query(models.Product).all())
    _sdb.close()
    from app.agents.llm_user_agent import run_llm_simulation
    from app.products.seed_loader import get_persona, get_scenario

    profiles = json.loads(PROFILES.read_text(encoding="utf-8"))
    picked = select_diverse(profiles, n)
    OUT.mkdir(parents=True, exist_ok=True)
    tag = f"{settings.deepseek_model}_think-{settings.deepseek_thinking}"
    print(f"[eval] model={settings.deepseek_model} thinking={settings.deepseek_thinking} "
          f"effort={settings.deepseek_reasoning_effort} · personas={len(picked)} turns={TURNS} conc={CONC}", flush=True)

    sem = asyncio.Semaphore(CONC)
    rows: list[dict] = []

    async def worker(entry: dict) -> None:
        pid = entry["personaId"]
        persona = get_persona(pid)
        sid = entry.get("matchedScenarioId")
        gt = (entry.get("scenarios") or {}).get(sid)
        scenario = get_scenario(sid)
        if not (persona and scenario and gt):
            print(f"  skip {pid}", flush=True)
            return
        profile = {**gt, "speechStyle": entry.get("speechStyle")}
        db = SessionLocal()
        try:
            async with sem:
                res = await run_llm_simulation(db, persona, profile, scenario, TURNS, gt_version="v2")
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {pid}: {type(e).__name__} {str(e)[:120]}", flush=True)
            return
        finally:
            db.close()
        sc = score_one(gt, res["anchorScores"], res["motivationScores"])
        rows.append({"personaId": pid, "name": persona.get("name"), "scenario": sid,
                     "userTurns": sum(1 for t in res["transcript"] if t["role"] == "user"), **sc})
        print(f"  ✓ {persona.get('name')} × {sid}: GTval={sc['gtValueDominant']} "
              f"rec={sc['recoveredValueTop2']} hit@2={sc['valueHit@2']} | "
              f"GTmot={sc['gtMotivationHigh']} recMot={sc['recoveredMotHigh']} motR={sc['motRecall']}", flush=True)

    await asyncio.gather(*(worker(e) for e in picked))

    # 집계 (베이스라인 대비)
    def rate(items, key):
        vals = [r[key] for r in items if r.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None
    nonfunc = [r for r in rows if r["nonFunctionalCase"]]
    agg = {
        "model": settings.deepseek_model, "thinking": settings.deepseek_thinking,
        "n": len(rows), "nonFunctionalN": len(nonfunc),
        "valueHit@1": rate(rows, "valueHit@1"), "valueHit@2": rate(rows, "valueHit@2"),
        "valueHit@1_nonFunctionalOnly": rate(nonfunc, "valueHit@1"),
        "valueHit@2_nonFunctionalOnly": rate(nonfunc, "valueHit@2"),
        "baselineValueHit(alwaysFunctional)": rate(rows, "baselineValueHit"),
        "motRecall": rate(rows, "motRecall"),
        "motPrecision": rate(rows, "motPrecision"),
        "baselineMotRecall(alwaysRole+Util)": rate(rows, "baselineMotRecall"),
    }
    result = {"aggregate": agg, "rows": rows}
    (OUT / f"result_{tag}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n==== 집계 (intention 복원, 베이스라인 대비) ====", flush=True)
    for k, v in agg.items():
        print(f"  {k}: {v}", flush=True)
    print(f"\n저장: {OUT}/result_{tag}.json", flush=True)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 6
    asyncio.run(main(n))
