"""Graph materialization — docs/ontology-graph-design.md §2 (schema), §5 (scopes).

One store, three induced views; scope is a query parameter, not three databases:
  session     (local)           — one session's subgraph
  participant (personal global) — union of one participant's sessions
  population  (cross-user)      — everything except PSCon analysis batches

Node types (5): product, dialogue, intention, concept, theory.
Theory nodes are the 12 fixed elements (trait 5 + motivation 7), materialized
here only — they have no table. No theory–theory edges (decision D2).

A1: rejection enters as (i) feedback-edge valence and (ii) intention kind
("avoidance"); meta counts are split by kind so sought/avoided never aggregate.
D1: dialogue→intention evidence edges carry per-edge channel + explicitness;
an intention with no explicit edge is hidden.
"""
from sqlalchemy.orm import Session as DbSession

from app.db import models
from app.ontology.anchor_mapper import MOTIVATION_DIMS, TRAIT_ANCHORS
from app.ontology.relation_classifier import effective_nature, relation_nature

SCOPES = ("session", "participant", "population")


def _theory_id(name: str) -> str:
    return f"theory:{name}"


def _select_sessions(db: DbSession, scope: str, scope_id: str | None) -> list[models.Session]:
    q = db.query(models.Session)
    if scope == "session":
        s = db.get(models.Session, scope_id)
        return [s] if s else []
    if scope == "participant":
        return q.filter(models.Session.participant_id == scope_id).all()
    # population: PSCon 배치 분석 세션 제외 (연구/시뮬 데이터만)
    return q.filter(models.Session.mode != "pscon").all()


def build_graph(db: DbSession, scope: str, scope_id: str | None = None) -> dict:
    if scope not in SCOPES:
        raise ValueError(f"unknown scope '{scope}' (expected one of {SCOPES})")
    if scope in ("session", "participant") and not scope_id:
        raise ValueError(f"scope '{scope}' requires an id")

    sessions = _select_sessions(db, scope, scope_id)
    session_ids = [s.id for s in sessions]
    nodes: list[dict] = []
    edges: list[dict] = []
    if not session_ids:
        return {"scope": scope, "scopeId": scope_id, "nodes": nodes, "edges": edges,
                "meta": {"sessions": 0}}

    # ── dialogue nodes ──────────────────────────────────────────────────
    for s in sessions:
        nodes.append({
            "id": s.id, "type": "dialogue", "mode": s.mode,
            "scenarioId": s.scenario_id, "participantId": s.participant_id,
            "stage": s.current_stage, "status": s.status,
        })

    # ── intention nodes + dialogue→intention evidence edges (D1) ──────
    topics = (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id.in_(session_ids))
        .all()
    )
    topic_ids = [t.id for t in topics]
    ev_rows = (
        db.query(models.IntentionEvidence)
        .filter(models.IntentionEvidence.topic_id.in_(topic_ids))
        .all()
    ) if topic_ids else []
    ev_by_topic: dict[str, list[models.IntentionEvidence]] = {}
    for e in ev_rows:
        ev_by_topic.setdefault(e.topic_id, []).append(e)

    kind_counts: dict[str, int] = {}
    hidden_count = 0
    for t in topics:
        kind = (t.hints or {}).get("kind", "preference")
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
        t_edges = ev_by_topic.get(t.id, [])
        # hidden := explicit 증거 엣지 부재 (엣지 없는 구 데이터는 노드 라벨 폴백)
        is_hidden = (
            not any(e.explicitness == "explicit" for e in t_edges)
            if t_edges else t.explicitness in ("implicit", "latent")
        )
        hidden_count += is_hidden
        nodes.append({
            "id": t.id, "type": "intention", "label": t.label, "kind": kind,
            "status": t.status, "priority": t.priority, "confidence": t.confidence,
            "explicitness": t.explicitness, "isHidden": is_hidden,
            "source": t.source, "sessionId": t.session_id,
        })
        if t_edges:
            for e in t_edges:
                edges.append({
                    "source": t.session_id, "target": t.id, "type": "evidence",
                    "channel": e.channel, "explicitness": e.explicitness,
                    "evidenceType": e.evidence_type, "evidenceId": e.evidence_id,
                })
        else:  # legacy topic without backfill — single fallback edge
            edges.append({
                "source": t.session_id, "target": t.id, "type": "evidence",
                "channel": t.source, "explicitness": t.explicitness,
                "evidenceType": "legacy", "evidenceId": None,
            })

    # ── product nodes + product→dialogue edges (impression / feedback) ──
    impressions = (
        db.query(models.ProductImpression)
        .filter(models.ProductImpression.session_id.in_(session_ids))
        .all()
    )
    feedbacks = (
        db.query(models.FeedbackEvent)
        .filter(models.FeedbackEvent.session_id.in_(session_ids))
        .all()
    )
    product_ids = {i.product_id for i in impressions} | {f.product_id for f in feedbacks}
    if product_ids:
        for p in db.query(models.Product).filter(models.Product.id.in_(product_ids)).all():
            nodes.append({
                "id": p.id, "type": "product", "title": p.title,
                "category": p.category, "price": p.price,
            })
    seen_impressions = set()
    for i in impressions:
        key = (i.product_id, i.session_id)
        if key in seen_impressions:
            continue
        seen_impressions.add(key)
        edges.append({"source": i.product_id, "target": i.session_id, "type": "impression"})
    for f in feedbacks:
        edges.append({
            "source": f.product_id, "target": f.session_id, "type": "feedback",
            "feedbackType": f.type, "valence": f.valence, "reasonCode": f.reason_code,
        })

    # ── concept nodes + intention→concept edges ────────────────────────
    links = (
        db.query(models.TopicConcept)
        .filter(models.TopicConcept.topic_id.in_(topic_ids))
        .all()
    ) if topic_ids else []
    concept_ids = {l.concept_id for l in links}
    concepts = (
        db.query(models.Concept).filter(models.Concept.id.in_(concept_ids)).all()
        if concept_ids else []
    )
    for c in concepts:
        nodes.append({
            "id": c.id, "type": "concept", "label": c.label,
            "normalizedLabel": c.normalized_label, "status": c.status,
            "origin": c.origin or [],
        })
    for l in links:
        edges.append({"source": l.topic_id, "target": l.concept_id,
                      "type": "intention_concept", "confidence": l.confidence})

    # ── theory nodes (fixed 12; D2 — no theory–theory edges) ───────────
    for name in TRAIT_ANCHORS:
        nodes.append({"id": _theory_id(name), "type": "theory", "tier": "trait", "label": name})
    for name in MOTIVATION_DIMS:
        nodes.append({"id": _theory_id(name), "type": "theory", "tier": "motivation", "label": name})

    # intention→theory (trait)
    anchor_maps = (
        db.query(models.AnchorMapping)
        .filter(models.AnchorMapping.topic_id.in_(topic_ids))
        .all()
    ) if topic_ids else []
    for a in anchor_maps:
        edges.append({
            "source": a.topic_id, "target": _theory_id(a.anchor), "type": "intention_theory",
            "score": a.score, "confidence": a.confidence,
            "temporalStatus": a.temporal_status,
        })

    # concept→theory (canonical, cross-session aggregate)
    cams = (
        db.query(models.ConceptAnchorMapping)
        .filter(models.ConceptAnchorMapping.concept_id.in_(concept_ids))
        .all()
    ) if concept_ids else []
    for ca in cams:
        edges.append({
            "source": ca.concept_id, "target": _theory_id(ca.anchor), "type": "concept_theory",
            "score": ca.score, "supportCount": ca.support_count,
        })

    # dialogue→theory (motivation은 세션 한정 local 층 — 의도가 아니라 대화에 붙는다)
    for s in sessions:
        snap = (
            db.query(models.PreferenceStateSnapshot)
            .filter(models.PreferenceStateSnapshot.session_id == s.id)
            .order_by(models.PreferenceStateSnapshot.created_at.desc())
            .first()
        )
        for dim, score in ((snap.motivation_scores or {}).items() if snap else []):
            if dim in MOTIVATION_DIMS and score:
                edges.append({"source": s.id, "target": _theory_id(dim),
                              "type": "dialogue_motivation", "score": score})

    # ── intention↔intention relations (session-scoped only — A2) ───────
    relations = (
        db.query(models.IntentionRelation)
        .filter(models.IntentionRelation.session_id.in_(session_ids))
        .all()
    )
    for r in relations:
        edges.append({
            "source": r.source_topic_id, "target": r.target_topic_id,
            "type": "intention_relation", "relationType": r.type,
            "nature": relation_nature(r.type),
            "effectiveNature": effective_nature(r.type, r.verification),  # D4
            "verification": r.verification, "plausibility": r.plausibility,
            "strength": r.strength,
        })

    mode_counts: dict[str, int] = {}
    for s in sessions:
        mode_counts[s.mode] = mode_counts.get(s.mode, 0) + 1
    return {
        "scope": scope,
        "scopeId": scope_id,
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "sessions": len(sessions),
            "sessionModes": mode_counts,  # population 분석 시 합성/사람 구분용
            "intentions": len(topics),
            "intentionsByKind": kind_counts,  # A1 — sought/avoided 분리 집계
            "hiddenIntentions": hidden_count,  # D1 — explicit 엣지 부재
            "concepts": len(concepts),
            "products": len(product_ids),
            "relations": len(relations),
        },
    }
