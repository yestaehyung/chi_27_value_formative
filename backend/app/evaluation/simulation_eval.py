"""Simulation evaluation against user-agent ground truth (spec §22.2)."""
from sqlalchemy.orm import Session as DbSession

from app.db import models
from app.ontology.anchor_mapper import VALUE_ANCHORS


def _label_matches(gt_label: str, topic_labels: list[str]) -> bool:
    """Keyword-overlap match between a ground-truth intention and extracted topics."""
    keywords = {
        "운동": ["운동", "친구에게 맞는"],
        "저렴해 보이지": ["저렴해 보이지 않기"],
        "사회적 적절성": ["저렴해 보이지 않기", "체면"],
        "장기 사용": ["장기 사용"],
        "실패 회피": ["실패", "브랜드를 잘 몰라", "신뢰"],
        "예산": ["예산", "부담"],
        "특별": ["특별함", "흔하지 않은"],
        "탐색": ["브랜드를 잘 몰라"],
    }
    for key, alts in keywords.items():
        if key in gt_label:
            return any(any(a in tl for a in alts) for tl in topic_labels)
    return any(gt_label[:4] in tl for tl in topic_labels)


def evaluate_simulation(db: DbSession, session: models.Session, scenario: dict) -> dict:
    topics = (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id == session.id)
        .all()
    )
    topic_labels = [t.label for t in topics]
    gt = scenario.get("groundTruthHiddenIntentions", [])

    matched = sum(1 for g in gt if _label_matches(g["label"], topic_labels))
    topic_recall = round(matched / len(gt), 2) if gt else None

    last_snap = (
        db.query(models.PreferenceStateSnapshot)
        .filter(models.PreferenceStateSnapshot.session_id == session.id)
        .order_by(models.PreferenceStateSnapshot.turn_index.desc())
        .first()
    )
    anchor_mae = None
    if last_snap and gt:
        gt_anchor = {a: 0.0 for a in VALUE_ANCHORS}
        for g in gt:
            for a, v in (g.get("anchors") or {}).items():
                if a in gt_anchor:  # trait(TCV5)만 비교; 구 Hedonic/Utilitarian 키는 무시
                    gt_anchor[a] = max(gt_anchor[a], v)
        pred = last_snap.anchor_scores or {}
        errs = [abs(gt_anchor[a] - pred.get(a, 0.0)) for a in VALUE_ANCHORS]
        anchor_mae = round(sum(errs) / len(errs), 3)

    purchase = (
        db.query(models.FeedbackEvent)
        .filter(models.FeedbackEvent.session_id == session.id)
        .filter(models.FeedbackEvent.type == "purchase")
        .first()
    )
    chosen_rank = None
    if purchase and purchase.turn_id:
        imp = (
            db.query(models.ProductImpression)
            .filter(models.ProductImpression.turn_id == purchase.turn_id)
            .filter(models.ProductImpression.product_id == purchase.product_id)
            .first()
        )
        chosen_rank = imp.rank if imp else None

    conflicts = (
        db.query(models.PreferenceConflict)
        .filter(models.PreferenceConflict.session_id == session.id)
        .all()
    )
    resolved = [c for c in conflicts if c.status not in ("open", "shown_to_user")]

    last_topic = max(topics, key=lambda t: t.created_at) if topics else None
    last_topic_turn = None
    if last_topic:
        snap_after = (
            db.query(models.PreferenceStateSnapshot)
            .filter(models.PreferenceStateSnapshot.session_id == session.id)
            .filter(models.PreferenceStateSnapshot.created_at >= last_topic.created_at)
            .order_by(models.PreferenceStateSnapshot.turn_index)
            .first()
        )
        last_topic_turn = snap_after.turn_index if snap_after else None

    from app.evaluation.ontology_eval import compute_latent_yield

    ly = compute_latent_yield(db, session.id)
    return {
        "anchorScoreMAE": anchor_mae,
        "topicRecall": topic_recall,
        "implicitLatentRatio": ly["implicitLatentRatio"],
        "latentYield": ly["latentYield"],
        "priorityAccuracy": None,  # requires researcher coding (spec §22.1)
        "conflictDetectionAccuracy": round(len(resolved) / len(conflicts), 2) if conflicts else None,
        "conflictCount": len(conflicts),
        "recommendationFitScore": None,
        "chosenProductRank": chosen_rank,
        "turnsToStablePreferenceState": last_topic_turn,
        "extractedTopicCount": len(topics),
        "groundTruthCount": len(gt),
    }
