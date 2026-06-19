"""One-shot backfill: IntentionTopic.evidence_ids → IntentionEvidence edge rows.

Graph design D1 (docs/ontology-graph-design.md): explicitness becomes a
per-evidence-edge property. Pre-existing topics carry a flat evidence_ids list
and a node-level explicitness only; this script materializes one edge per
evidence id, recomputing structural explicitness from the same inputs used at
creation time (topic.source + hints.kind), then refreshes the node cache.

Idempotent: topics that already have evidence rows are skipped.

  cd backend && .venv/bin/python scripts/backfill_intention_evidence.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/ → import app

from app.db import models  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.ontology.merge import attach_evidence_edges  # noqa: E402


def main() -> None:
    init_db()
    db = SessionLocal()
    try:
        topics = db.query(models.IntentionTopic).all()
        backfilled = skipped = empty = 0
        for topic in topics:
            has_rows = (
                db.query(models.IntentionEvidence)
                .filter(models.IntentionEvidence.topic_id == topic.id)
                .first()
            )
            if has_rows:
                skipped += 1
                continue
            ev_ids = topic.evidence_ids or []
            if not ev_ids:
                empty += 1
                continue
            hints = topic.hints or {}
            stored = {e.get("id"): e for e in hints.get("evidence", []) if isinstance(e, dict)}
            entries = [stored.get(i) or {"id": i} for i in ev_ids]
            # Reconstruct the ext dict structural_explicitness expects. The stored
            # node label is the LLM-era result, so passing it back preserves the
            # original downgrade decisions (it can never upgrade to explicit).
            ext = {"kind": hints.get("kind", "preference"), "explicitness": topic.explicitness}
            attach_evidence_edges(db, topic, entries, ext, topic.source)
            backfilled += 1
        db.commit()
        print(f"backfilled={backfilled} skipped(existing)={skipped} no-evidence={empty} total={len(topics)}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
