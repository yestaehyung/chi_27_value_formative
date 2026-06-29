"""디버그: Functional rank-1 inflation 원인 추적 (systematic-debugging Phase 1 — 관측).

Social-GT인데 Functional이 1순위를 가로채는 persona(안우영)를 한 세션 돌리고,
추출 토픽 → anchor 매핑(anchor/confidence/strength/impact/intensity) → 최종 점수를
전부 덤프한다. 가설 분리:
  (A) Social 토픽 자체가 안 뽑힘(topic_extraction 누락)
  (B) Social 관련 토픽이 Functional로 매핑됨(anchor_mapping 오배정)
  (C) Social 매핑 intensity가 Functional보다 낮음(confidence/strength/impact 차이)
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_dbg_"), "dbg.db"))
os.environ.setdefault("VC_EXPORT_DIR", tempfile.mkdtemp(prefix="vc_dbg_exp_"))

import asyncio  # noqa: E402
import json  # noqa: E402

from app.db.database import SessionLocal, init_db  # noqa: E402

PID = os.environ.get("VC_DBG_PID", "")  # 비우면 첫 Social-only GT persona 자동 선택


async def main() -> None:
    init_db()
    from app.db import models
    from app.products import embeddings
    from app.products.search_index import build_index
    from app.products.seed_loader import (get_persona, get_scenario,
                                          load_seed_concepts, load_seed_products)
    sdb = SessionLocal()
    load_seed_products(sdb); load_seed_concepts(sdb); build_index(sdb)
    embeddings.ensure_product_vectors(sdb.query(models.Product).all())
    sdb.close()

    from app.agents.llm_user_agent import run_llm_simulation
    profs = json.loads((Path(__file__).resolve().parent.parent / "seed" / "personas_nemotron_profiles_v2.json").read_text("utf-8"))

    # Social-only dominant GT persona 선택
    pid = PID
    if not pid:
        for e in profs.values():
            sid = e.get("matchedScenarioId"); gt = (e.get("scenarios") or {}).get(sid) or {}
            dom = [a for a, lv in (gt.get("valueLevels") or {}).items() if lv == "dominant"]
            if dom == ["Social"]:
                pid = e["personaId"]; break
    entry = profs[pid]
    sid = entry["matchedScenarioId"]; gt = entry["scenarios"][sid]
    persona = get_persona(pid); scenario = get_scenario(sid)
    profile = {**gt, "speechStyle": entry.get("speechStyle")}
    print(f"persona={persona.get('name')} ({pid}) × {sid}")
    print(f"GT valueLevels   = {gt.get('valueLevels')}")
    print(f"GT hiddenIntent  = {gt.get('hiddenIntentions')}")

    db = SessionLocal()
    res = await run_llm_simulation(db, persona, profile, scenario, 6, gt_version="v2")
    sid_db = res["sessionId"]
    print(f"\nfinal anchorScores = { {k: round(v,2) for k,v in res['anchorScores'].items() if v>0} }\n")

    # 토픽 → anchor 매핑 덤프
    topics = db.query(models.IntentionTopic).filter(models.IntentionTopic.session_id == sid_db).all()
    print(f"=== {len(topics)} topics → anchor mappings (intensity=m.score) ===")
    for t in topics:
        ms = db.query(models.AnchorMapping).filter(models.AnchorMapping.topic_id == t.id).all()
        kind = (t.hints or {}).get("kind", "?")
        print(f"\n[{t.priority}/{t.status}/{kind}] {t.label!r}  (conf={t.confidence})")
        for m in sorted(ms, key=lambda x: -x.score):
            print(f"    {m.anchor:11} intensity={m.score:.2f}  conf={m.confidence:9} "
                  f"strength={m.evidence_strength:6} impact={m.decision_impact:6} status={m.temporal_status}")

    # breakdown
    from app.ontology.state_builder import compute_anchor_scores
    scores, bd = compute_anchor_scores(db, topics)
    print("\n=== per-anchor score + top contributors ===")
    for a in sorted(scores, key=lambda x: -scores[x]):
        if scores[a] <= 0 and not bd[a]["contributors"]:
            continue
        contribs = ", ".join(f"{c['topicLabel'][:14]}={c['contribution']}" for c in bd[a]["contributors"])
        print(f"  {a:11} score={scores[a]:.2f}  ← {contribs}")
    db.close()


if __name__ == "__main__":
    asyncio.run(main())
