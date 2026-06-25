"""Preference Commit Engine (spec §16, §28.3).

New evidence (turns / feedback) is treated as a commit against the current
preference state: extract topics → merge → anchors → concepts → relations →
conflicts → snapshot.

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
from app.ontology.anchor_mapper import apply_anchor_mappings, fetch_anchor_mappings
from app.ontology.conceptualizer import apply_concepts, fetch_concepts, recompute_concept_anchors
from app.ontology.merge import merge_topics, plan_new_topics
from app.ontology.relation_classifier import apply_relations, fetch_relations
from app.ontology.state_builder import build_snapshot, get_active_topics
from app.ontology.topic_extractor import extract_topics
from app.preference_commit.conflict_detector import apply_conflicts, fetch_conflicts

logger = logging.getLogger(__name__)


@dataclass
class PreferenceCommitResult:
    touched_topics: list[models.IntentionTopic] = field(default_factory=list)
    new_topics: list[models.IntentionTopic] = field(default_factory=list)
    new_conflicts: list[models.PreferenceConflict] = field(default_factory=list)
    snapshot: models.PreferenceStateSnapshot | None = None


async def _safe(coro, default, stage: str):
    """Degrade gracefully: a single failing pipeline stage (malformed LLM output,
    API error after retries) must not 500 the whole turn."""
    try:
        return await coro
    except Exception:  # noqa: BLE001
        logger.exception("preference commit stage '%s' failed — skipping", stage)
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
    current_state = {"activeTopicLabels": [t.label for t in pre_existing]}

    # 동기 층(M8) 입력 — 새 user 발화가 있는 commit에서만 감지한다.
    # 여기(공통 파이프라인)에 두어 라이브·시뮬레이션·PSCon 배치가 모두 12축을 얻는다.
    user_contents: list[str] = []
    if turn_ids:
        rows = db.query(models.Turn).filter(models.Turn.id.in_(turn_ids)).all()
        user_contents = [t.content for t in rows if t.role in ("user", "user_agent") and t.content]

    # ────────────────── LLM phase (reads only) ──────────────────
    # Stage 1 — topic extraction (+ motivation 감지를 같은 왕복에 병렬로)
    from app.agents.motivation import fetch_motivation_signals

    t1 = time.perf_counter()
    motivation_signals: list[dict] | None = None
    if user_contents:
        extracted, motivation_signals = await asyncio.gather(
            _safe(extract_topics(db, provider, session, turn_ids, feedback_ids, current_state),
                  [], "topic_extraction"),
            _safe(fetch_motivation_signals(provider, user_contents), None, "motivation_detection"),
        )
    else:
        extracted = await _safe(
            extract_topics(db, provider, session, turn_ids, feedback_ids, current_state),
            [], "topic_extraction",
        )
    t2 = time.perf_counter()
    logger.info("commit_engine.stage1_latency_sec=%.3f (topic_extraction+motivation)", t2 - t1)

    pending_new = plan_new_topics(pre_existing, extracted)

    anchors_by_label: dict = {}
    concepts_by_label: dict = {}
    raw_relations: list = []
    raw_conflicts: list = []
    # 한 줄 요약은 칩이 바뀐 commit(pending_new 있음)에서만 새로 생성한다. 안 바뀌면
    # None → build_snapshot이 직전 문장을 이어받는다(깜빡임 방지).
    state_summary_text: str | None = None
    if pending_new:
        from app.preference_commit.summary_builder import fetch_state_summary

        all_labels = [t.label for t in pre_existing] + [p["label"] for p in pending_new]
        existing_ctx = [
            {"id": t.id, "label": t.label, "priority": t.priority, "status": t.status}
            for t in pre_existing
        ]
        # 요약용 provisional 칩 라벨 (context 토픽 제외). 병합 전이라 라벨은 최종과 동일.
        prov_labels = (
            [t.label for t in pre_existing if (t.hints or {}).get("kind") != "context"]
            + [p["label"] for p in pending_new if p.get("kind") != "context"]
        )[:6]
        scenario = (session.meta or {}).get("shoppingGoal") or (session.meta or {}).get("category") or ""
        # Stages 2-4 + 6 + 요약 fetched concurrently — one network round-trip
        t3 = time.perf_counter()
        (anchors_by_label, concepts_by_label, raw_relations, raw_conflicts,
         state_summary_text) = await asyncio.gather(
            _safe(fetch_anchor_mappings(provider, pending_new), {}, "anchor_mapping"),
            _safe(fetch_concepts(provider, pending_new), {}, "conceptualization"),
            _safe(fetch_relations(provider, all_labels), [], "relation_classification"),
            _safe(fetch_conflicts(provider, existing_ctx, [p["label"] for p in pending_new]),
                  [], "conflict_detection"),
            _safe(fetch_state_summary(provider, prov_labels, scenario), None, "state_summary"),
        )
        t4 = time.perf_counter()
        logger.info("commit_engine.stage2_4_6_latency_sec=%.3f (anchors+concepts+relations+conflicts+summary)", t4 - t3)
    else:
        logger.info("commit_engine.stage2_4_6_skipped=no_pending_new")

    # ────────────────── Write phase (one short transaction) ──────────────────
    t_write = time.perf_counter()
    # 동기 층 누적 (M8/M4) — snapshot이 meta를 읽으므로 build_snapshot 전에 갱신
    if user_contents:
        from app.agents.motivation import apply_motivation_signals, detect_motivation, merge_motivation

        meta = dict(session.meta or {})
        if motivation_signals is not None:
            meta = apply_motivation_signals(meta, motivation_signals)
        else:  # LLM 실패 — 구 키워드 경로 폴백
            for content in user_contents:
                meta["motivationScores"] = merge_motivation(
                    meta.get("motivationScores", {}), detect_motivation(content))
        session.meta = meta

    touched, created = merge_topics(db, session, extracted, source=source)  # Stage 5
    apply_anchor_mappings(db, created, anchors_by_label)                    # Stage 2 (의도→이론, 강도)
    concept_links = apply_concepts(db, created, concepts_by_label)          # Stage 3 (의도→개념)
    recompute_concept_anchors(db, concept_links)                           # 개념→이론 canonical (ideation 2)
    apply_relations(db, session, raw_relations)                             # Stage 4
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
