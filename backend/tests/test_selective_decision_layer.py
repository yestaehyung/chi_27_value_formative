"""Question promotion and selective value/motivation decision-layer contracts."""
import asyncio
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_decision_"), "test.db"))
os.environ.setdefault("VC_EXPORT_DIR", tempfile.mkdtemp(prefix="vc_decision_exp_"))
os.environ["VC_LLM_PROVIDER"] = "mock"

import pytest

from app.core.ids import new_id
from app.db import models
from app.db.database import Base, SessionLocal, engine
from app.llm.mock_rules import TASK_HANDLERS
from app.llm.prompts import EN_DIRECTIVES, FORMAT_BY_TASK, SYSTEM_BY_TASK
from app.llm.provider import get_provider
from app.agents.planner import build_planner_context, fetch_plan
from app.preference_commit.commit_engine import run_preference_commit
from app.preference_commit.summary_builder import build_user_visible_summary


@pytest.fixture(scope="module", autouse=True)
def schema():
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _session(db):
    row = models.Session(
        id=new_id("sess"), mode="manual", scenario_id="custom",
        meta={"studyCondition": "ours", "category": "Keyboards"},
    )
    db.add(row)
    db.commit()
    return row


def _user_turn(db, session, index: int, content: str):
    row = models.Turn(
        id=new_id("turn"), session_id=session.id, turn_index=index,
        role="user", content=content,
    )
    db.add(row)
    db.commit()
    return row


def _mark_product_shown(db, session, index: int = 1):
    product = models.Product(
        id=new_id("prod"), title="Standard keyboard", category="Keyboards", price=70_000,
    )
    turn = models.Turn(
        id=new_id("turn"), session_id=session.id, turn_index=index,
        role="service_agent", content="Here are some keyboards.", agent_action="recommend",
    )
    db.add_all([product, turn])
    db.flush()
    db.add(models.ProductImpression(
        id=new_id("imp"), session_id=session.id, turn_id=turn.id,
        product_id=product.id, rank=1,
    ))
    db.commit()


def test_new_llm_tasks_have_all_three_registry_contracts():
    # clarification_motivation은 2026-08-26 D5로 삭제 — 남은 결정층 태스크만 검사
    for task in ("criterion_value_interpretation",):
        assert task in TASK_HANDLERS
        assert task in SYSTEM_BY_TASK
        assert task in FORMAT_BY_TASK
        assert task in EN_DIRECTIVES


def test_question_is_not_a_topic_then_promotes_with_both_evidence_edges(db):
    session = _session(db)
    question = _user_turn(db, session, 0, "Are the keys quiet?")
    first = asyncio.run(run_preference_commit(
        db, get_provider(), session, [question.id], [], "user_utterance",
    ))

    assert first.touched_topics == []
    assert (session.meta or {})["criterionQuestionCandidates"][0]["candidateLabel"] == "quiet keys"

    _mark_product_shown(db, session)
    statement = _user_turn(db, session, 2, "Quiet keys matter to me.")
    second = asyncio.run(run_preference_commit(
        db, get_provider(), session, [statement.id], [], "user_utterance",
    ))

    assert len(second.touched_topics) == 1
    topic = second.touched_topics[0]
    assert topic.label == "quiet keys"
    assert set(topic.evidence_ids) == {question.id, statement.id}
    edges = (
        db.query(models.IntentionEvidence)
        .filter(models.IntentionEvidence.topic_id == topic.id)
        .all()
    )
    assert {e.channel for e in edges} == {"question_signal", "user_utterance"}
    assert topic.explicitness == "explicit"
    theory = (topic.hints or {}).get("theoryBasis") or {}
    assert theory["analysisStatus"] == "ok"
    # Directly declared criteria are acknowledged, not re-confirmed in the Ours widget.
    assert theory["askable"] is False
    assert (session.meta or {})["criterionQuestionCandidates"] == []


def test_question_only_never_activates_value_or_motivation_analysis(db):
    session = _session(db)
    _mark_product_shown(db, session, index=0)
    question = _user_turn(db, session, 1, "Is the battery long-lasting?")
    asyncio.run(run_preference_commit(
        db, get_provider(), session, [question.id], [], "user_utterance",
    ))
    assert (session.meta or {}).get("decisionAnalysis") is None
    assert db.query(models.IntentionTopic).filter_by(session_id=session.id).count() == 0


def test_reputable_brand_becomes_one_natural_value_grounded_question(db):
    session = _session(db)
    _mark_product_shown(db, session, index=0)
    statement = _user_turn(
        db, session, 1,
        "I want a reputable brand, such as Samsung, Sony, or LG.",
    )
    result = asyncio.run(run_preference_commit(
        db, get_provider(), session, [statement.id], [], "user_utterance",
    ))
    chip = result.snapshot.user_visible_summary["chips"][0]
    assert chip["askable"] is True
    assert chip["theoryBasis"]["valueInterpretation"]["values"][0]["anchor"] == "Emotional"

    turns = db.query(models.Turn).filter_by(session_id=session.id).order_by(models.Turn.turn_index).all()
    ctx = build_planner_context(
        turns, result.snapshot, True, "recommend", None, "Choose a keyboard",
        db=db, session=session,
    )
    decision = asyncio.run(fetch_plan(get_provider(), ctx, fallback_search_text=statement.content))
    assert decision.action == "clarify"
    assert decision.probe_question == (
        "Are you asking for a well-known brand mainly because reliability matters to you?"
    )
    topic = result.touched_topics[0]
    topic.status = "confirmed"
    assert build_user_visible_summary([topic], False)["chips"][0]["askable"] is False


def test_decision_analysis_failure_is_visible_and_falls_back_to_direct_criteria(db):
    class FailingDecisionProvider:
        name = "stub"

        async def generate_json(self, _messages, task=None, context=None, **_kwargs):
            if task in {"criterion_value_interpretation"}:
                raise RuntimeError("intentional decision-layer failure")
            return TASK_HANDLERS[task](context or {})

    session = _session(db)
    _mark_product_shown(db, session, index=0)
    statement = _user_turn(db, session, 1, "I want a reputable brand.")
    result = asyncio.run(run_preference_commit(
        db, FailingDecisionProvider(), session, [statement.id], [], "user_utterance",
    ))
    diag = (session.meta or {})["decisionAnalysis"]
    assert diag["analysisStatus"] == "failed"
    assert diag["fallback"] == "direct_criteria_only"
    assert diag["failedTasks"] == ["criterion_value_interpretation"]
    theory = (result.touched_topics[0].hints or {})["theoryBasis"]
    assert theory["analysisStatus"] == "failed"
    assert theory["askable"] is False


def test_topic_extraction_failure_is_marked_in_session_metadata(db):
    class FailingExtractionProvider:
        name = "stub"

        async def generate_json(self, _messages, task=None, context=None, **_kwargs):
            if task == "topic_extraction":
                raise RuntimeError("intentional extraction failure")
            return TASK_HANDLERS[task](context or {})

    session = _session(db)
    statement = _user_turn(db, session, 0, "I need a quiet keyboard under $100.")
    result = asyncio.run(run_preference_commit(
        db, FailingExtractionProvider(), session, [statement.id], [], "user_utterance",
    ))
    assert result.touched_topics == []
    diag = (session.meta or {})["preferenceAnalysis"]
    assert diag["analysisStatus"] == "degraded"
    assert diag["fallback"] == "direct_criteria_only"
    assert diag["failedTasks"] == ["topic_extraction"]
