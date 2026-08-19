"""오프라인 온톨로지 백필 — AnchorMapping·Concept·Relation을 분석 시점에 일괄 계산.

2026-08-19 결정: 이 세 산출물은 추천·발화에 쓰이지 않는 측정층이라 실시간 커밋
파이프라인에서 제거했다 (commit_engine — 턴당 LLM 호출·flash 오류 표면 축소).
분석 전에 이 스크립트를 한 번 돌리면 연구 뷰(가치 프로필·궤적·그래프·RIG)와
export가 이전과 동일한 데이터를 갖는다. 멱등: 이미 매핑/개념이 있는 토픽은 건너뛴다.

    cd backend && PYTHONPATH=. .venv/bin/python scripts/backfill_offline_ontology.py [session_id ...]
    (인자 없으면 매핑 없는 전체 토픽 대상. 실 LLM 키 필요 — .env)
"""
import asyncio
import logging
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.db import models  # noqa: E402
from app.db.database import SessionLocal  # noqa: E402
from app.llm.provider import get_provider  # noqa: E402
from app.ontology.anchor_mapper import apply_anchor_mappings, fetch_anchor_mappings  # noqa: E402
from app.ontology.conceptualizer import apply_concepts, fetch_concepts  # noqa: E402
from app.ontology.relation_classifier import apply_relations, fetch_relations  # noqa: E402

logger = logging.getLogger("backfill")


def _topics_missing_anchors(db, session_id: str) -> list[models.IntentionTopic]:
    mapped = {
        row[0] for row in db.query(models.AnchorMapping.topic_id)
        .join(models.IntentionTopic, models.IntentionTopic.id == models.AnchorMapping.topic_id)
        .filter(models.IntentionTopic.session_id == session_id)
    }
    return [
        t for t in db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id == session_id)
        .filter(models.IntentionTopic.status.notin_(("rejected_by_user", "inactive")))
        if t.id not in mapped
    ]


async def backfill_session(db, provider, session: models.Session,
                           stages: tuple = ("anchors", "concepts", "relations")) -> dict:
    """한 세션의 앵커 매핑 + 개념 + 관계를 채운다. 반환: 단계별 생성 수."""
    stats = {"anchors": 0, "concepts": 0, "relations": 0}

    pending = _topics_missing_anchors(db, session.id) if "anchors" in stages else []
    if pending:
        as_dicts = [
            {"label": t.label,
             "sourceEvidence": (t.hints or {}).get("evidence") or
             [{"type": "turn", "id": ev, "quoteOrSummary": t.description or t.label}
              for ev in (t.evidence_ids or [])]}
            for t in pending
        ]
        by_label = await fetch_anchor_mappings(provider, as_dicts)
        before = db.query(models.AnchorMapping).count()
        apply_anchor_mappings(db, pending, by_label)
        db.flush()
        stats["anchors"] = db.query(models.AnchorMapping).count() - before

    all_topics = (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id == session.id)
        .filter(models.IntentionTopic.status.notin_(("rejected_by_user", "inactive")))
        .all()
    )
    linked = {
        row[0] for row in db.query(models.TopicConcept.topic_id)
        .join(models.IntentionTopic, models.IntentionTopic.id == models.TopicConcept.topic_id)
        .filter(models.IntentionTopic.session_id == session.id)
    }
    unlinked = [t for t in all_topics if t.id not in linked and "concepts" in stages]
    if unlinked:
        as_dicts = [{"label": t.label, "description": t.description} for t in unlinked]
        concepts_by_label = await fetch_concepts(provider, as_dicts)
        stats["concepts"] = len(apply_concepts(db, unlinked, concepts_by_label) or [])

    has_relations = db.query(models.IntentionRelation).filter(
        models.IntentionRelation.session_id == session.id).count() > 0
    if "relations" in stages and not has_relations and len(all_topics) >= 2:
        raw = await fetch_relations(provider, [t.label for t in all_topics])
        rels = apply_relations(db, session, raw)
        stats["relations"] = len(rels or [])

    db.commit()
    return stats


async def main(session_ids: list[str]) -> None:
    db = SessionLocal()
    provider = get_provider()
    try:
        if session_ids:
            sessions = [db.get(models.Session, sid) for sid in session_ids]
            sessions = [s for s in sessions if s is not None]
        else:
            sessions = db.query(models.Session).all()
        total = {"anchors": 0, "concepts": 0, "relations": 0}
        for s in sessions:
            stats = await backfill_session(db, provider, s)
            if any(stats.values()):
                print(f"{s.id}: {stats}")
            for k, v in stats.items():
                total[k] += v
        print(f"완료 — 세션 {len(sessions)}개, 생성: {total}")
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main(sys.argv[1:]))
