"""JSONL exports for research analysis (spec §21)."""
import json
from pathlib import Path

from sqlalchemy.orm import Session as DbSession

from app.core.config import settings
from app.db import models, serializers


def _write_jsonl(path: Path, rows: list[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def export_all(db: DbSession) -> dict[str, int]:
    out_dir = settings.export_dir
    spec = [
        ("sessions.jsonl", models.Session, serializers.session_to_dict),
        ("turns.jsonl", models.Turn, serializers.turn_to_dict),
        ("product_impressions.jsonl", models.ProductImpression, serializers.impression_to_dict),
        ("feedback_events.jsonl", models.FeedbackEvent, serializers.feedback_to_dict),
        ("ontology_topics.jsonl", models.IntentionTopic, serializers.topic_to_dict),
        ("ontology_relations.jsonl", models.IntentionRelation, serializers.relation_to_dict),
        ("preference_state_snapshots.jsonl", models.PreferenceStateSnapshot, serializers.snapshot_to_dict),
        ("conflicts.jsonl", models.PreferenceConflict, serializers.conflict_to_dict),
        ("conflict_resolutions.jsonl", models.ConflictResolutionEvent, serializers.resolution_to_dict),
        ("chosen_rejected_pairs.jsonl", models.ChosenRejectedPair, serializers.pair_to_dict),
        ("discovered_features.jsonl", models.DiscoveredFeature, serializers.feature_to_dict),
        # 유저스터디 분석 보강분: 그래프 재구성 + correction 시점 분석용
        ("concepts.jsonl", models.Concept, serializers.concept_to_dict),
        ("anchor_mappings.jsonl", models.AnchorMapping, serializers.anchor_mapping_to_dict),
        ("feature_clusters.jsonl", models.FeatureCluster, serializers.cluster_to_dict),
        ("correction_events.jsonl", models.CorrectionEvent, serializers.correction_to_dict),
        ("observation_markers.jsonl", models.ObservationMarker, serializers.marker_to_dict),
    ]
    counts: dict[str, int] = {}
    for filename, model, serialize in spec:
        rows = [serialize(r) for r in db.query(model).all()]
        counts[filename] = _write_jsonl(out_dir / filename, rows)
    # topic↔concept 링크 (그래프 재구성용)
    links = [
        {"topicId": l.topic_id, "conceptId": l.concept_id, "confidence": l.confidence}
        for l in db.query(models.TopicConcept).all()
    ]
    counts["topic_concepts.jsonl"] = _write_jsonl(out_dir / "topic_concepts.jsonl", links)
    return counts
