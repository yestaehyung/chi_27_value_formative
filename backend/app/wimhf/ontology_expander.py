"""Phase E — fold researcher-approved discovered features into the ontology (spec §11)."""
from sqlalchemy.orm import Session as DbSession

from app.core.ids import new_id
from app.db import models


def approve_feature(db: DbSession, feature: models.DiscoveredFeature) -> models.Concept | None:
    """DiscoveredFeature → Concept candidate → ontology node (created_by='wimhf')."""
    label = feature.suggested_concept_label or feature.label
    normalized = label.replace(" ", "_")
    concept = (
        db.query(models.Concept)
        .filter(models.Concept.normalized_label == normalized)
        .first()
    )
    if concept is None:
        concept = models.Concept(
            id=new_id("concept"),
            label=label,
            normalized_label=normalized,
            description=feature.description,
            aliases=[feature.label] if feature.label != label else [],
            source_topic_ids=[],
            created_by="wimhf",
            status="confirmed",  # researcher 승인 = validated→confirmed (이론모듈 §11.2)
            origin=["bottom_up_feature"],
        )
        db.add(concept)
    else:
        # 기존 node에 bottom-up 근거가 추가됨 → revised + version bump (이론모듈 §11.3)
        if "bottom_up_feature" not in (concept.origin or []):
            concept.origin = (concept.origin or []) + ["bottom_up_feature"]
        concept.status = "confirmed"
        concept.version = round((concept.version or 1.0) + 0.1, 1)
    feature.status = "merged_into_concept"
    db.commit()
    return concept
