"""Researcher dashboard API (spec §5.3, §18.7, §20.6)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

from app.db import models, serializers
from app.db.database import get_db
from app.db.schemas import FeatureStatusRequest, PairMiningRequest
from app.llm.provider import get_provider
from app.evaluation.value_profile import build_value_profile
from app.llm.prompts import SYSTEM_BY_TASK  # noqa: F401 (sme_translation task)
from app.products.seed_loader import get_scenario, load_personas, load_scenarios
from app.wimhf.feature_miner import cluster_features, mine_features
from app.wimhf.ontology_expander import approve_feature

router = APIRouter(prefix="/api/research", tags=["research"])


@router.get("/sessions")
def list_sessions(mode: str | None = None, db: DbSession = Depends(get_db)):
    # 모드별 개수 (탭 배지용) — 값싼 그룹 쿼리 한 번
    mode_counts = dict(
        db.query(models.Session.mode, func.count(models.Session.id))
        .group_by(models.Session.mode).all()
    )
    q = db.query(models.Session)
    if mode:
        q = q.filter(models.Session.mode == mode)
    else:
        # 기본 연구 목록: PSCon 배치 분석 세션은 제외 (별도 탭/`/pscon`)
        q = q.filter(models.Session.mode != "pscon")
    q = q.order_by(models.Session.started_at.desc())
    if mode == "pscon":
        q = q.limit(100)  # 648건 전수 N+1 방지 (전체·그래프는 /pscon)
    sessions = q.all()
    out = []
    for s in sessions:
        turn_count = db.query(models.Turn).filter(models.Turn.session_id == s.id).count()
        fb_count = db.query(models.FeedbackEvent).filter(models.FeedbackEvent.session_id == s.id).count()
        pair_count = db.query(models.ChosenRejectedPair).filter(models.ChosenRejectedPair.session_id == s.id).count()
        conflict_count = db.query(models.PreferenceConflict).filter(models.PreferenceConflict.session_id == s.id).count()
        topic_count = db.query(models.IntentionTopic).filter(models.IntentionTopic.session_id == s.id).count()
        d = serializers.session_to_dict(s)
        d.update(turnCount=turn_count, feedbackCount=fb_count, pairCount=pair_count,
                 conflictCount=conflict_count, topicCount=topic_count)
        out.append(d)
    return {"sessions": out, "modeCounts": mode_counts}


@router.get("/sessions/{session_id}/replay")
def session_replay(session_id: str, db: DbSession = Depends(get_db)):
    session = db.get(models.Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")

    topics = db.query(models.IntentionTopic).filter(models.IntentionTopic.session_id == session_id).all()
    topic_payload = []
    for t in topics:
        anchors = db.query(models.AnchorMapping).filter(models.AnchorMapping.topic_id == t.id).all()
        concept_links = db.query(models.TopicConcept).filter(models.TopicConcept.topic_id == t.id).all()
        concepts = [db.get(models.Concept, link.concept_id) for link in concept_links]
        topic_payload.append(serializers.topic_to_dict(t, anchors=anchors, concepts=[c for c in concepts if c]))

    return {
        "session": serializers.session_to_dict(session),
        "scenario": (session.meta or {}).get("customScenario") or get_scenario(session.scenario_id),
        "turns": [serializers.turn_to_dict(t) for t in db.query(models.Turn)
                  .filter(models.Turn.session_id == session_id).order_by(models.Turn.turn_index).all()],
        "impressions": [
            serializers.impression_to_dict(i, db.get(models.Product, i.product_id))
            for i in db.query(models.ProductImpression)
            .filter(models.ProductImpression.session_id == session_id)
            .order_by(models.ProductImpression.created_at, models.ProductImpression.rank).all()
        ],
        "feedback": [serializers.feedback_to_dict(f) for f in db.query(models.FeedbackEvent)
                     .filter(models.FeedbackEvent.session_id == session_id)
                     .order_by(models.FeedbackEvent.created_at).all()],
        "topics": topic_payload,
        "relations": [serializers.relation_to_dict(r) for r in db.query(models.IntentionRelation)
                      .filter(models.IntentionRelation.session_id == session_id).all()],
        "snapshots": [serializers.snapshot_to_dict(s) for s in db.query(models.PreferenceStateSnapshot)
                      .filter(models.PreferenceStateSnapshot.session_id == session_id)
                      .order_by(models.PreferenceStateSnapshot.created_at).all()],
        "conflicts": [serializers.conflict_to_dict(c) for c in db.query(models.PreferenceConflict)
                      .filter(models.PreferenceConflict.session_id == session_id).all()],
        "resolutions": [serializers.resolution_to_dict(r) for r in db.query(models.ConflictResolutionEvent)
                        .filter(models.ConflictResolutionEvent.session_id == session_id).all()],
        "corrections": [serializers.correction_to_dict(c) for c in db.query(models.CorrectionEvent)
                        .filter(models.CorrectionEvent.session_id == session_id)
                        .order_by(models.CorrectionEvent.created_at).all()],
        "markers": [serializers.marker_to_dict(m) for m in db.query(models.ObservationMarker)
                    .filter(models.ObservationMarker.session_id == session_id)
                    .order_by(models.ObservationMarker.created_at).all()],
        "pairs": [serializers.pair_to_dict(p) for p in db.query(models.ChosenRejectedPair)
                  .filter(models.ChosenRejectedPair.session_id == session_id).all()],
    }


@router.get("/pairs")
def list_pairs(sessionId: str | None = None, db: DbSession = Depends(get_db)):
    q = db.query(models.ChosenRejectedPair).order_by(models.ChosenRejectedPair.created_at.desc())
    if sessionId:
        q = q.filter(models.ChosenRejectedPair.session_id == sessionId)
    pairs = q.all()
    out = []
    for p in pairs:
        d = serializers.pair_to_dict(p)
        chosen = db.get(models.Product, p.chosen_id)
        rejected = db.get(models.Product, p.rejected_id)
        d["chosenProduct"] = serializers.product_to_dict(chosen) if chosen else None
        d["rejectedProduct"] = serializers.product_to_dict(rejected) if rejected else None
        out.append(d)
    return {"pairs": out}


@router.post("/pair-mining/run")
async def run_pair_mining(req: PairMiningRequest, db: DbSession = Depends(get_db)):
    provider = get_provider()
    features, pair_count = await mine_features(db, provider, req.sessionIds, req.minPairs)
    clusters = await cluster_features(db, provider, features)
    return {
        "pairCount": pair_count,
        "minPairs": req.minPairs,
        "features": [serializers.feature_to_dict(f) for f in features],
        "clusters": [serializers.cluster_to_dict(c) for c in clusters],
    }


@router.get("/features")
def list_features(db: DbSession = Depends(get_db)):
    features = db.query(models.DiscoveredFeature).order_by(models.DiscoveredFeature.created_at.desc()).all()
    clusters = db.query(models.FeatureCluster).order_by(models.FeatureCluster.created_at.desc()).all()
    return {
        "features": [serializers.feature_to_dict(f) for f in features],
        "clusters": [serializers.cluster_to_dict(c) for c in clusters],
    }


@router.get("/concepts")
def list_concepts(db: DbSession = Depends(get_db)):
    """Hybrid ontology node 목록 (lifecycle/provenance 포함, 이론모듈 §11)."""
    concepts = db.query(models.Concept).order_by(models.Concept.created_at).all()
    out = []
    for c in concepts:
        canon = db.query(models.ConceptAnchorMapping).filter(
            models.ConceptAnchorMapping.concept_id == c.id
        ).all()
        d = serializers.concept_to_dict(c, anchors=canon)
        d["linkedTopicCount"] = (
            db.query(models.TopicConcept).filter(models.TopicConcept.concept_id == c.id).count()
        )
        out.append(d)
    return {"concepts": out}


@router.get("/metrics/latent-yield")
def latent_yield(sessionId: str | None = None, db: DbSession = Depends(get_db)):
    """Hidden intention 산출 지표 — implicit/latent 비율 × 사용자 확인율."""
    from app.evaluation.ontology_eval import compute_latent_yield

    return compute_latent_yield(db, sessionId)


@router.post("/judge/run")
async def run_judge(sessionId: str):
    """수동/시뮬레이션용 judge 트리거 (M5) — 라이브 턴은 BackgroundTasks로 자동 실행되지만,
    시뮬레이션 세션이나 과거 세션은 이 엔드포인트로 평결한다."""
    from app.agents.judge import judge_causal_relations

    return await judge_causal_relations(sessionId)


@router.get("/graph")
def graph(scope: str = "session", id: str | None = None, db: DbSession = Depends(get_db)):
    """Scoped graph materialization (docs/ontology-graph-design.md §5).

    scope=session&id=<sessionId>      — local subgraph
    scope=participant&id=<pid>        — personal global (세션 합집합)
    scope=population                  — 사용자 횡단 (PSCon 배치 제외)
    """
    from app.graph.export import build_graph

    try:
        return build_graph(db, scope, id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/participants")
def list_participants(db: DbSession = Depends(get_db)):
    """기존 참가자 목록 (세션 이어가기용)."""
    parts = db.query(models.Participant).order_by(models.Participant.created_at.desc()).all()
    out = []
    for p in parts:
        sessions = db.query(models.Session).filter(models.Session.participant_id == p.id).all()
        survey = p.survey if isinstance(p.survey, dict) else {}
        answers = survey.get("answers", {}) or {}
        out.append({
            "id": p.id,
            "label": p.label,
            "sessionCount": len(sessions),
            "specVersion": p.spec_version or 0,
            "hasSurvey": bool(answers),
            "surveyCount": len(answers),
            "createdAt": serializers.iso(p.created_at),
        })
    return {"participants": out}


@router.get("/participants/{participant_id}/spec")
def participant_spec(participant_id: str, db: DbSession = Depends(get_db)):
    """참가자 자연어 명세 파일 (AI memory). 최신 상태로 합성해 반환."""
    from app.spec_builder import update_participant_spec

    p = update_participant_spec(db, participant_id)
    if p is None:
        raise HTTPException(404, "participant not found")
    return {
        "participantId": p.id,
        "specMarkdown": p.spec_markdown or "",
        "version": p.spec_version,
        "updatedAt": serializers.iso(p.updated_at),
    }


@router.get("/participants/{participant_id}/survey")
def participant_survey(participant_id: str, db: DbSession = Depends(get_db)):
    """참가자 사전 설문 응답 (연구자 열람용). answers={questionId: value}, profile=파생 점수."""
    p = db.get(models.Participant, participant_id)
    if p is None:
        raise HTTPException(404, "participant not found")
    survey = p.survey if isinstance(p.survey, dict) else {}
    return {
        "participantId": p.id,
        "label": p.label,
        "answers": survey.get("answers", {}) or {},
        "profile": survey.get("profile", {}) or {},
        "createdAt": serializers.iso(p.created_at),
    }


@router.get("/rig/theory-transitions")
def rig_theory_transitions(db: DbSession = Depends(get_db)):
    """RIG-A: 이론 단계 전이 (세션 횡단 dominant anchor 순서 집계)."""
    from app import rig

    return rig.theory_transitions(db)


@router.get("/sessions/{session_id}/meta-path")
def rig_meta_path(session_id: str, db: DbSession = Depends(get_db)):
    """RIG-B: 한 세션의 의도 구체화 경로."""
    from app import rig

    if db.get(models.Session, session_id) is None:
        raise HTTPException(404, "session not found")
    return rig.session_meta_path(db, session_id)


@router.get("/sessions/{session_id}/predict")
def rig_predict(session_id: str, db: DbSession = Depends(get_db)):
    """RIG-C: 경로 기반 다음/최종 의도·상품 예측."""
    from app import rig

    if db.get(models.Session, session_id) is None:
        raise HTTPException(404, "session not found")
    return rig.predict_intentions(db, session_id)


@router.get("/sessions/{session_id}/value-profile")
def session_value_profile(session_id: str, db: DbSession = Depends(get_db)):
    session = db.get(models.Session, session_id)
    if session is None:
        raise HTTPException(404, "session not found")
    return build_value_profile(db, session)


@router.get("/sme-insights")
async def sme_insights(db: DbSession = Depends(get_db)):
    """집계 hidden intention → SME 액션 번역 (이론모듈 Module J §14.3).

    개인 세션이 아니라 confirmed/observed concept의 집계 패턴 수준에서 제안한다.
    """
    provider = get_provider()
    concepts = (
        db.query(models.Concept)
        .filter(models.Concept.status.notin_(["rejected", "deprecated"]))
        .all()
    )
    # 근거가 있는 concept만 (linked topic 또는 seed)
    rows = []
    for c in concepts:
        linked = db.query(models.TopicConcept).filter(models.TopicConcept.concept_id == c.id).count()
        if linked == 0 and c.status == "seed":
            continue  # 아직 한 번도 관찰되지 않은 seed는 제외
        rows.append((c, linked))

    needs_translation = [c for c, _ in rows if not (c.sme_translation or [])]
    if needs_translation:
        out = await provider.generate_json(
            [], task="sme_translation",
            context={"concepts": [{"label": c.label, "description": c.description} for c in needs_translation]},
        )
        by_label = {t.get("conceptLabel"): t for t in out.get("translations") or [] if isinstance(t, dict)}
        for c in needs_translation:
            t = by_label.get(c.label)
            if t:
                c.sme_translation = (t.get("actions") or []) + (
                    [f"포지셔닝: {t['positioning']}"] if t.get("positioning") else []
                )
        db.commit()

    insights = []
    for c, linked in sorted(rows, key=lambda x: -x[1]):
        # 대표 evidence (linked topic의 라벨)
        topic_labels = [
            db.get(models.IntentionTopic, link.topic_id).label
            for link in db.query(models.TopicConcept).filter(models.TopicConcept.concept_id == c.id).limit(3).all()
        ]
        insights.append({
            "concept": serializers.concept_to_dict(c),
            "linkedTopicCount": linked,
            "exampleTopics": topic_labels,
        })
    return {"insights": insights}


@router.post("/features/{feature_id}/status")
def set_feature_status(feature_id: str, req: FeatureStatusRequest, db: DbSession = Depends(get_db)):
    feature = db.get(models.DiscoveredFeature, feature_id)
    if feature is None:
        raise HTTPException(404, "feature not found")
    concept = None
    if req.status in ("researcher_approved", "merged_into_concept"):
        concept = approve_feature(db, feature)
        feature.status = req.status
        db.commit()
    else:
        feature.status = req.status
        db.commit()
    return {
        "feature": serializers.feature_to_dict(feature),
        "concept": serializers.concept_to_dict(concept) if concept else None,
    }


@router.get("/meta")
def research_meta(db: DbSession = Depends(get_db)):
    products = db.query(models.Product).all()
    return {
        "scenarios": load_scenarios(),
        "personas": load_personas(),
        "products": [serializers.product_to_dict(p) for p in products],
    }
