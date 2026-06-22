"""ORM → camelCase JSON dicts matching the frontend TypeScript types (spec §6-§11)."""
from datetime import timezone

from app.db import models


def iso(dt):
    """ISO 문자열 + UTC 표시. 타임스탬프는 UTC로 저장되지만 SQLite를 거치며 tzinfo가
    떨어져 naive가 된다. tz 표시 없이 내보내면 프런트의 new Date()가 로컬로 오해해
    시간이 어긋나므로, naive면 UTC로 간주해 '+00:00'을 붙인다."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


def product_to_dict(p: models.Product) -> dict:
    return {
        "id": p.id,
        "title": p.title,
        "category": p.category,
        "brand": p.brand,
        "price": p.price,
        "listPrice": p.list_price,
        "discountRate": p.discount_rate,
        "deliveryFee": p.delivery_fee,
        "rating": p.rating,
        "reviewCount": p.review_count,
        "longTermReviewRatio": p.long_term_review_ratio,
        "recentSalesCount": p.recent_sales_count,
        "sellerId": p.seller_id,
        "sellerName": p.seller_name,
        "sellerGrade": p.seller_grade,
        "sellerYears": p.seller_years,
        "sellerRegion": p.seller_region,
        "imageUrl": p.image_url,
        "productUrl": p.product_url,
        "attributes": p.attributes or {},
        "description": p.description,
        "cueSummary": p.cue_summary or {},
    }


def session_to_dict(s: models.Session) -> dict:
    return {
        "id": s.id,
        "mode": s.mode,
        "scenarioId": s.scenario_id,
        "userAgentId": s.user_agent_id,
        "participantId": s.participant_id,
        "currentStage": s.current_stage,
        "status": s.status,
        "metadata": s.meta or {},
        "startedAt": iso(s.started_at),
        "endedAt": iso(s.ended_at),
    }


def turn_to_dict(t: models.Turn) -> dict:
    return {
        "id": t.id,
        "sessionId": t.session_id,
        "turnIndex": t.turn_index,
        "role": t.role,
        "content": t.content,
        "dialogueActs": t.dialogue_acts or [],
        "agentAction": t.agent_action,
        "relatedProductIds": t.related_product_ids or [],
        "createdAt": iso(t.created_at),
    }


def impression_to_dict(i: models.ProductImpression, product: models.Product | None = None) -> dict:
    d = {
        "id": i.id,
        "sessionId": i.session_id,
        "turnId": i.turn_id,
        "productId": i.product_id,
        "rank": i.rank,
        "recommendationReason": i.recommendation_reason,
        "matchedIntentions": i.matched_intentions or [],
        "weakIntentions": i.weak_intentions or [],
        "productCuesShown": i.product_cues_shown or {},
        "createdAt": iso(i.created_at),
    }
    if product is not None:
        d["product"] = product_to_dict(product)
    return d


def feedback_to_dict(f: models.FeedbackEvent) -> dict:
    return {
        "id": f.id,
        "sessionId": f.session_id,
        "turnId": f.turn_id,
        "productId": f.product_id,
        "type": f.type,
        "valence": f.valence,
        "reasonCode": f.reason_code,
        "reasonText": f.reason_text,
        "createdAt": iso(f.created_at),
    }


def topic_to_dict(t: models.IntentionTopic, anchors: list[models.AnchorMapping] | None = None,
                  concepts: list[models.Concept] | None = None) -> dict:
    d = {
        "id": t.id,
        "sessionId": t.session_id,
        "label": t.label,
        "description": t.description,
        "source": t.source,
        "status": t.status,
        "priority": t.priority,
        "confidence": t.confidence,
        "explicitness": t.explicitness,
        "evidenceIds": t.evidence_ids or [],
        "relatedProductIds": t.related_product_ids or [],
        "hints": t.hints or {},
        "createdAt": iso(t.created_at),
        "updatedAt": iso(t.updated_at),
    }
    if anchors is not None:
        d["anchorMappings"] = [anchor_mapping_to_dict(a) for a in anchors]
    if concepts is not None:
        d["concepts"] = [concept_to_dict(c) for c in concepts]
    return d


def anchor_mapping_to_dict(a: models.AnchorMapping) -> dict:
    return {
        "id": a.id,
        "topicId": a.topic_id,
        "anchor": a.anchor,
        "score": a.score,
        "confidence": a.confidence,
        "evidenceStrength": a.evidence_strength,
        "decisionImpact": a.decision_impact,
        "temporalStatus": a.temporal_status,
        "rationale": a.rationale,
        "evidenceIds": a.evidence_ids or [],
    }


def concept_to_dict(c: models.Concept, anchors: list["models.ConceptAnchorMapping"] | None = None) -> dict:
    return {
        "id": c.id,
        "label": c.label,
        "normalizedLabel": c.normalized_label,
        "description": c.description,
        "aliases": c.aliases or [],
        "sourceTopicIds": c.source_topic_ids or [],
        "createdBy": c.created_by,
        # 개념 → 이론 canonical 매핑 (ideation 2번)
        "anchorMappings": [
            {"anchor": a.anchor, "score": a.score, "confidence": a.confidence,
             "supportCount": a.support_count}
            for a in sorted(anchors, key=lambda x: -x.score)
        ] if anchors is not None else None,
        "status": c.status,
        "origin": c.origin or [],
        "version": c.version,
        "scenarioScope": c.scenario_scope or [],
        "userVisibleLabel": c.user_visible_label,
        "smeTranslation": c.sme_translation or [],
        "createdAt": iso(c.created_at),
    }


def cluster_to_dict(c: models.FeatureCluster) -> dict:
    return {
        "id": c.id,
        "label": c.label,
        "description": c.description,
        "memberFeatureIds": c.member_feature_ids or [],
        "memberFeatureLabels": c.member_feature_labels or [],
        "scenarioDistribution": c.scenario_distribution or {},
        "createdAt": iso(c.created_at),
    }


def intention_evidence_to_dict(e: models.IntentionEvidence) -> dict:
    return {
        "id": e.id,
        "topicId": e.topic_id,
        "evidenceType": e.evidence_type,
        "evidenceId": e.evidence_id,
        "channel": e.channel,
        "explicitness": e.explicitness,
        "kind": e.kind,
        "createdAt": iso(e.created_at),
    }


def relation_to_dict(r: models.IntentionRelation) -> dict:
    from app.ontology.relation_classifier import effective_nature, relation_nature

    return {
        "id": r.id,
        "sessionId": r.session_id,
        "sourceTopicId": r.source_topic_id,
        "targetTopicId": r.target_topic_id,
        "type": r.type,
        "nature": relation_nature(r.type),  # co_occurrence | temporal | causal (타입 고유값)
        # 검증 반영값: 인과인데 plausibility 미달이면 co_occurrence로 강등 (graph design D4)
        "effectiveNature": effective_nature(r.type, r.verification),
        "verification": r.verification,
        "causalEvidence": r.causal_evidence,  # M1 범주 원본
        "plausibility": r.plausibility,  # 파생 캐시 (levels.py)
        "strength": r.strength,
        "rationale": r.rationale,
        "evidenceIds": r.evidence_ids or [],
        "createdAt": iso(r.created_at),
    }


def snapshot_to_dict(s: models.PreferenceStateSnapshot) -> dict:
    return {
        "id": s.id,
        "sessionId": s.session_id,
        "turnIndex": s.turn_index,
        "stage": s.stage,
        "anchorBreakdown": s.anchor_breakdown or {},
        "motivationScores": s.motivation_scores or {},
        "activeTopicIds": s.active_topic_ids or [],
        "activeConceptIds": s.active_concept_ids or [],
        "anchorScores": s.anchor_scores or {},
        "hardConstraints": s.hard_constraints or [],
        "softPreferences": s.soft_preferences or [],
        "avoidances": s.avoidances or [],
        "priorityOrder": s.priority_order or [],
        "uncertainty": s.uncertainty or {},
        "userVisibleSummary": s.user_visible_summary or {},
        "createdAt": iso(s.created_at),
    }


def conflict_to_dict(c: models.PreferenceConflict) -> dict:
    return {
        "id": c.id,
        "sessionId": c.session_id,
        "severity": c.severity,
        "status": c.status,
        "oldTopicId": c.old_topic_id,
        "newTopicId": c.new_topic_id,
        "oldAssumption": c.old_assumption,
        "newSignal": c.new_signal,
        "conflictType": c.conflict_type,
        "explanationForUser": c.explanation_for_user,
        "explanationForResearcher": c.explanation_for_researcher,
        "suggestedResolutions": c.suggested_resolutions or [],
        "createdAt": iso(c.created_at),
        "resolvedAt": iso(c.resolved_at),
    }


def pair_to_dict(p: models.ChosenRejectedPair) -> dict:
    return {
        "id": p.id,
        "sessionId": p.session_id,
        "promptContext": p.prompt_context,
        "chosenType": p.chosen_type,
        "rejectedType": p.rejected_type,
        "chosenId": p.chosen_id,
        "rejectedId": p.rejected_id,
        "labelSource": p.label_source,
        "userReasonText": p.user_reason_text,
        "productDiff": p.product_diff or {},
        "responseDiff": p.response_diff or {},
        "inferredHiddenReason": p.inferred_hidden_reason,
        "createdAt": iso(p.created_at),
    }


def feature_to_dict(f: models.DiscoveredFeature) -> dict:
    return {
        "id": f.id,
        "label": f.label,
        "description": f.description,
        "sourcePairIds": f.source_pair_ids or [],
        "examplePairs": f.example_pairs or [],
        "candidateAnchorMappings": f.candidate_anchor_mappings or [],
        "noveltyScore": f.novelty_score,
        "coverageScore": f.coverage_score,
        "predictivenessScore": f.predictiveness_score,
        "interpretabilityScore": f.interpretability_score,
        "status": f.status,
        "suggestedConceptLabel": f.suggested_concept_label,
        "suggestedOntologyAction": f.suggested_ontology_action,
        "createdAt": iso(f.created_at),
    }


def correction_to_dict(c: models.CorrectionEvent) -> dict:
    return {
        "id": c.id,
        "sessionId": c.session_id,
        "topicId": c.topic_id,
        "action": c.action,
        "turnIndex": c.turn_index,
        "before": c.before or {},
        "after": c.after or {},
        "manualLabel": c.manual_label,
        "createdAt": iso(c.created_at),
    }


def marker_to_dict(m: models.ObservationMarker) -> dict:
    return {
        "id": m.id,
        "sessionId": m.session_id,
        "turnIndex": m.turn_index,
        "kind": m.kind,
        "tag": m.tag,
        "note": m.note,
        "topicId": m.topic_id,
        "createdAt": iso(m.created_at),
    }


def resolution_to_dict(r: models.ConflictResolutionEvent) -> dict:
    return {
        "id": r.id,
        "conflictId": r.conflict_id,
        "sessionId": r.session_id,
        "selectedOptionId": r.selected_option_id,
        "action": r.action,
        "manualText": r.manual_text,
        "resultingSnapshotId": r.resulting_snapshot_id,
        "createdAt": iso(r.created_at),
    }
