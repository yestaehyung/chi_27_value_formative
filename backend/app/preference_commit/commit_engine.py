"""Preference Commit Engine (spec §16, §28.3).

New evidence (turns / feedback) is treated as a commit against the current
preference state: extract topics → merge → anchors → conflicts → snapshot.

Concurrency design: all LLM calls run first against read-only context
(SQLite write locks are NOT held while waiting on the network), then every
DB mutation happens in one short write transaction at the end. This lets a
browser session interact in real time while simulations run on the same DB.

Performance: each stage is timed; logs show "commit_engine.stage_latency_sec"
to diagnose LLM latency bottlenecks.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session as DbSession

from app.db import models
from app.llm.provider import LLMProvider
from app.ontology.merge import merge_topics, plan_new_topics
from app.ontology.state_builder import build_snapshot, get_active_topics
from app.ontology.topic_extractor import extract_topic_update
from app.preference_commit.conflict_detector import apply_conflicts, fetch_conflicts

logger = logging.getLogger(__name__)


@dataclass
class PreferenceCommitResult:
    touched_topics: list[models.IntentionTopic] = field(default_factory=list)
    new_topics: list[models.IntentionTopic] = field(default_factory=list)
    new_conflicts: list[models.PreferenceConflict] = field(default_factory=list)
    snapshot: models.PreferenceStateSnapshot | None = None


async def _safe(coro, default, stage: str, failures: list[str] | None = None):
    """Degrade gracefully: a single failing pipeline stage (malformed LLM output,
    API error after retries) must not 500 the whole turn."""
    try:
        return await coro
    except Exception:  # noqa: BLE001
        logger.exception("preference commit stage '%s' failed — skipping", stage)
        if failures is not None and stage not in failures:
            failures.append(stage)
        return default


async def run_preference_commit(
    db: DbSession,
    provider: LLMProvider,
    session: models.Session,
    turn_ids: list[str],
    feedback_ids: list[str],
    source: str,
) -> PreferenceCommitResult:
    t0 = time.perf_counter()
    pre_existing = get_active_topics(db, session.id)
    current_state = {
        "activeTopicLabels": [t.label for t in pre_existing],
        # 사용자가 직접 쓴 문구는 재추출 시 표현이 달라도 그대로 재사용해야 한다
        # (수정된 라벨은 대화의 자연스러운 표현과 멀어져 중복 칩이 생기기 쉬움)
        "userAuthoredLabels": [t.label for t in pre_existing if t.status == "corrected_by_user"],
        "criterionQuestionCandidates": list(
            (session.meta or {}).get("criterionQuestionCandidates") or []
        ),
    }
    has_prior_impression = (
        db.query(models.ProductImpression)
        .filter(models.ProductImpression.session_id == session.id)
        .first()
        is not None
    )

    # 동기 층(M8) 입력 — 새 user 발화가 있는 commit에서만 감지한다.
    # 여기(공통 파이프라인)에 두어 라이브·시뮬레이션·PSCon 배치가 모두 12축을 얻는다.
    user_contents: list[str] = []
    if turn_ids:
        rows = db.query(models.Turn).filter(models.Turn.id.in_(turn_ids)).all()
        user_contents = [t.content for t in rows if t.role in ("user", "user_agent") and t.content]

    # ────────────────── LLM phase (reads only) ──────────────────
    # Stage 1 — topic extraction.
    # (motivation 감지는 2026-08-25 제거 — 이론 프레이밍을 TCV 단일 축으로 좁히면서
    #  detect-only 축이던 쇼핑 동기 호출을 뺐다. 모듈·mock 핸들러·과거 데이터의
    #  meta.motivationScores는 그대로 두고 새로 감지하지 않는다.)
    t1 = time.perf_counter()
    analysis_failures: list[str] = []
    extraction_update = await _safe(
        extract_topic_update(db, provider, session, turn_ids, feedback_ids, current_state),
        {"topics": [], "questionSignals": [], "interpretationCandidate": None},
        "topic_extraction", analysis_failures,
    )
    extracted = extraction_update.get("topics") or []
    question_signals = extraction_update.get("questionSignals") or []
    interpretation_candidate = extraction_update.get("interpretationCandidate")
    t2 = time.perf_counter()
    logger.info("commit_engine.stage1_latency_sec=%.3f (topic_extraction)", t2 - t1)

    pending_new = plan_new_topics(pre_existing, extracted)

    from app.agents.decision_interpreter import candidate_is_activated

    decision_candidate_active = candidate_is_activated(
        interpretation_candidate,
        has_prior_impression=has_prior_impression,
    )

    raw_conflicts: list = []
    value_interpretation: dict | None = None
    # 한 줄 요약은 칩이 바뀐 commit(pending_new 있음)에서만 새로 생성한다. 안 바뀌면
    # None → build_snapshot이 직전 문장을 이어받는다(깜빡임 방지).
    state_summary_text: str | None = None
    if pending_new:
        from app.agents.decision_interpreter import fetch_value_interpretation
        from app.preference_commit.summary_builder import fetch_state_summary

        existing_ctx = [
            {"id": t.id, "label": t.label, "priority": t.priority, "status": t.status}
            for t in pre_existing
        ]
        # 요약용 provisional 칩 라벨 (context 토픽 제외). 병합 전이라 라벨은 최종과 동일.
        # 요약 근거: 라벨 + 사용자 우선순위/확인 상태 — 비교("A보다 B")는 이 근거가
        # 있을 때만 쓰도록 프롬프트가 제한한다 (라벨만 주면 비교가 전부 날조).
        prov_criteria = (
            [{"label": t.label, "priority": t.priority, "status": t.status}
             for t in pre_existing if (t.hints or {}).get("kind") != "context"]
            + [{"label": p["label"], "priority": p.get("priority"), "status": "new"}
               for p in pending_new if p.get("kind") != "context"]
        )[:8]
        scenario = (session.meta or {}).get("shoppingGoal") or (session.meta or {}).get("category") or ""
        # 충돌 + 요약(+ 해석 후보 시 가치 해석)을 한 왕복에 병렬 실행한다.
        # (clarification_motivation은 2026-08-25 제거 — TCV 단일 축; 저장만 되고
        #  런타임에서 읽는 곳이 없었다. theoryBasis는 가치 해석만 싣는다.)
        # Concept/Relation 그래프와 AnchorMapping(TCV 매핑)은 참가자 턴에서 만들지
        # 않는다 — 추천·발화에 쓰이지 않는 측정층이라, 분석 시점에 저장된 원자료
        # (토픽·근거·theoryBasis)로 오프라인 일괄 계산한다 (2026-08-19 결정,
        # scripts/backfill_offline_ontology.py). 기존 테이블/API는 호환용 유지.
        t3 = time.perf_counter()
        value_coro = (
            _safe(fetch_value_interpretation(provider, interpretation_candidate), None,
                  "criterion_value_interpretation", analysis_failures)
            if decision_candidate_active else asyncio.sleep(0, result=None)
        )
        (raw_conflicts, state_summary_text,
         value_interpretation) = await asyncio.gather(
            _safe(fetch_conflicts(provider, existing_ctx, [p["label"] for p in pending_new]),
                  [], "conflict_detection", analysis_failures),
            _safe(fetch_state_summary(provider, prov_criteria, scenario, user_contents),
                  None, "state_summary", analysis_failures),
            value_coro,
        )
        t4 = time.perf_counter()
        logger.info("commit_engine.stage2_6_latency_sec=%.3f (conflicts+summary)", t4 - t3)
    elif decision_candidate_active:
        from app.agents.decision_interpreter import fetch_value_interpretation

        value_interpretation = await _safe(
            fetch_value_interpretation(provider, interpretation_candidate), None,
            "criterion_value_interpretation", analysis_failures,
        )
        logger.info("commit_engine.stage2_decision_only=completed")
    else:
        logger.info("commit_engine.stage2_6_skipped=no_pending_new")

    # ────────────────── Write phase (one short transaction) ──────────────────
    t_write = time.perf_counter()
    # 질문은 기준이 아니다. 다음 발화의 동일 라벨 승격을 위해 세션 메타에만 짧게 보관한다.
    meta = dict(session.meta or {})
    meta["preferenceAnalysis"] = {
        "analysisStatus": "degraded" if analysis_failures else "ok",
        "failedTasks": list(analysis_failures),
        "fallback": (
            "direct_criteria_only" if "topic_extraction" in analysis_failures
            else ("stage_specific_safe_fallback" if analysis_failures else None)
        ),
    }
    candidates = [
        c for c in (meta.get("criterionQuestionCandidates") or []) if isinstance(c, dict)
    ]
    candidates.extend(question_signals)
    promoted = {
        str(t.get("label") or "").strip().casefold()
        for t in extracted if isinstance(t, dict)
    }
    candidates = [
        c for c in candidates
        if str(c.get("candidateLabel") or "").strip().casefold() not in promoted
    ][-8:]
    meta["criterionQuestionCandidates"] = candidates
    if decision_candidate_active:
        failed = [] if value_interpretation is not None else ["criterion_value_interpretation"]
        usable = (
            isinstance(value_interpretation, dict)
            and value_interpretation.get("analysisStatus") == "ok"
        )
        meta["decisionAnalysis"] = {
            "analysisStatus": (
                "failed" if failed
                else "ok" if usable
                else "insufficient_evidence"
            ),
            "fallback": "direct_criteria_only" if failed or not usable else None,
            "failedTasks": failed,
            "criterionLabel": (interpretation_candidate or {}).get("criterionLabel"),
        }
    session.meta = meta

    touched, created = merge_topics(db, session, extracted, source=source)  # Stage 5
    if decision_candidate_active:
        from app.agents.decision_interpreter import apply_theory_basis

        applied = apply_theory_basis(
            touched, interpretation_candidate, value_interpretation,
        )
        if applied is None:
            # 해석 후보는 본질적으로 **새로운 숨은 기준**이라 기존 토픽과 라벨이 안 겹치는
            # 게 정상이다 (E2E 실측: "well-known brand" 토픽 옆의 "avoiding purchase
            # regret" 후보가 매번 미스). 매칭 실패 = 새 추론 토픽으로 생성해 theoryBasis를
            # 싣는다 — agent_inference 출처라 구조적으로 latent, 미확인이므로 ours에선
            # 확인 전 추천 미반영·askable 질문 대상이 된다.
            candidate_ext = {
                "label": (interpretation_candidate or {}).get("criterionLabel") or "",
                "description": (value_interpretation or {}).get("actionableCriterion"),
                "kind": "preference",
                "priority": "medium",
                "confidenceLevel": "strong_inference"
                if (interpretation_candidate or {}).get("strength") == "strong"
                else "weak_inference",
                "sourceEvidence": [
                    {"type": "turn", "id": ev, "quoteOrSummary": q}
                    for ev, q in zip(
                        (interpretation_candidate or {}).get("evidenceIds") or [],
                        ((interpretation_candidate or {}).get("quotes") or []) + [""] * 8,
                    )
                ],
            }
            if candidate_ext["label"]:
                _, cand_created = merge_topics(
                    db, session, [candidate_ext], source="agent_inference")
                applied = apply_theory_basis(
                    cand_created or touched, interpretation_candidate,
                    value_interpretation,
                )
                created.extend(cand_created)
                touched.extend(cand_created)
        if applied is None:
            meta = dict(session.meta or {})
            diag = dict(meta.get("decisionAnalysis") or {})
            diag.update({
                "analysisStatus": "failed",
                "fallback": "direct_criteria_only",
                "failedTasks": list(dict.fromkeys([
                    *(diag.get("failedTasks") or []), "topic_match",
                ])),
            })
            meta["decisionAnalysis"] = diag
            session.meta = meta
            logger.warning(
                "decision-layer candidate did not match a topic — label=%s",
                (interpretation_candidate or {}).get("criterionLabel"),
            )
    created_ids = {t.id for t in created}
    conflicts = apply_conflicts(                                            # Stage 6
        db, session, raw_conflicts,
        existing_topics=[t for t in pre_existing if t.id not in created_ids],
        new_topics=created,
    )
    snapshot = build_snapshot(db, session, llm_summary=state_summary_text)  # Stage 7-8
    db.commit()
    t_write_end = time.perf_counter()
    logger.info("commit_engine.write_latency_sec=%.4f", t_write_end - t_write)

    t_total = time.perf_counter()
    logger.info("commit_engine.total_latency_sec=%.3f", t_total - t0)

    return PreferenceCommitResult(
        touched_topics=touched,
        new_topics=created,
        new_conflicts=conflicts,
        snapshot=snapshot,
    )
