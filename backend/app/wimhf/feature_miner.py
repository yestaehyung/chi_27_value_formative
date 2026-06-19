"""WIMHF-style lightweight feature miner (spec §11 Phase C-D)."""
from sqlalchemy.orm import Session as DbSession

from app.core.ids import new_id
from app.db import models
from app.db.serializers import pair_to_dict
from app.llm.provider import LLMProvider


async def cluster_features(
    db: DbSession,
    provider: LLMProvider,
    features: list[models.DiscoveredFeature],
) -> list[models.FeatureCluster]:
    """이론모듈 §9.4 Step 4 — 반복되는 feature를 상위 가치 cluster로 묶는다."""
    if len(features) < 2:
        return []
    context = {"features": [{"label": f.label, "description": f.description} for f in features]}
    out = await provider.generate_json([], task="feature_clustering", context=context)

    by_label = {f.label: f for f in features}
    clusters: list[models.FeatureCluster] = []
    for c in out.get("clusters") or []:
        if not isinstance(c, dict) or not c.get("label"):
            continue
        members = [m for m in (c.get("memberFeatureLabels") or []) if m in by_label]
        if len(members) < 2:
            continue
        existing = (
            db.query(models.FeatureCluster)
            .filter(models.FeatureCluster.label == c["label"])
            .first()
        )
        if existing:
            existing.member_feature_ids = [by_label[m].id for m in members]
            existing.member_feature_labels = members
            existing.scenario_distribution = c.get("scenarioDistribution", {})
            clusters.append(existing)
            continue
        cluster = models.FeatureCluster(
            id=new_id("cluster"),
            label=c["label"],
            description=c.get("description"),
            member_feature_ids=[by_label[m].id for m in members],
            member_feature_labels=members,
            scenario_distribution=c.get("scenarioDistribution", {}),
        )
        db.add(cluster)
        clusters.append(cluster)
    db.commit()
    return clusters


async def mine_features(
    db: DbSession,
    provider: LLMProvider,
    session_ids: list[str] | None,
    min_pairs: int = 5,
) -> tuple[list[models.DiscoveredFeature], int]:
    q = db.query(models.ChosenRejectedPair)
    if session_ids:
        q = q.filter(models.ChosenRejectedPair.session_id.in_(session_ids))
    pairs = q.all()
    if len(pairs) < min_pairs:
        return [], len(pairs)

    context = {"pairs": [pair_to_dict(p) for p in pairs]}
    out = await provider.generate_json([], task="feature_mining", context=context)

    features: list[models.DiscoveredFeature] = []
    for f in out.get("features") or []:
        if not isinstance(f, dict) or not f.get("label"):
            continue
        existing = (
            db.query(models.DiscoveredFeature)
            .filter(models.DiscoveredFeature.label == f["label"])
            .first()
        )
        if existing:
            existing.source_pair_ids = f.get("sourcePairIds", [])
            existing.example_pairs = f.get("examplePairs", [])
            existing.coverage_score = f.get("coverageScore")
            existing.predictiveness_score = f.get("predictivenessScore")
            existing.novelty_score = f.get("noveltyScore")
            existing.interpretability_score = f.get("interpretabilityScore")
            features.append(existing)
            continue
        feature = models.DiscoveredFeature(
            id=new_id("feat"),
            label=f["label"],
            description=f.get("description"),
            source_pair_ids=f.get("sourcePairIds", []),
            example_pairs=f.get("examplePairs", []),
            candidate_anchor_mappings=f.get("candidateAnchorMappings", []),
            novelty_score=f.get("noveltyScore"),
            coverage_score=f.get("coverageScore"),
            predictiveness_score=f.get("predictivenessScore"),
            interpretability_score=f.get("interpretabilityScore"),
            status="candidate",
            suggested_concept_label=f.get("suggestedConceptLabel"),
            suggested_ontology_action=f.get("suggestedOntologyAction"),
        )
        db.add(feature)
        features.append(feature)
    db.commit()
    return features, len(pairs)
