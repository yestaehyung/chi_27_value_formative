"""User-agent simulation runner (spec §5.2, §12, §20.5)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session as DbSession

from app.agents.service_agent import handle_feedback, handle_user_turn
from app.agents.user_agent import UserAgentRunner
from app.core.ids import new_id
from app.db import models, serializers
from app.db.database import get_db
from app.db.schemas import SimulationRequest
from app.evaluation.simulation_eval import evaluate_simulation
from app.ontology.state_builder import build_snapshot
from app.preference_commit.conflict_resolver import resolve_conflict
from app.products.seed_loader import get_persona, get_scenario
from datetime import datetime, timezone

router = APIRouter(prefix="/api/simulations", tags=["simulations"])


@router.post("/run")
async def run_simulation(req: SimulationRequest, db: DbSession = Depends(get_db)):
    scenario = get_scenario(req.scenarioId)
    persona = get_persona(req.userAgentProfileId)
    if scenario is None or persona is None:
        raise HTTPException(404, "unknown scenario or persona")

    session = models.Session(
        id=new_id("sess"),
        mode="simulation",
        scenario_id=req.scenarioId,
        user_agent_id=req.userAgentProfileId,
        current_stage="exploration",
        status="active",
        meta={
            "studyCondition": "correctable",
            "category": scenario.get("targetCategory"),
            "shoppingGoal": scenario.get("title"),
            "assignedPersona": persona["name"],
        },
    )
    db.add(session)
    db.flush()
    build_snapshot(db, session)
    db.commit()

    agent = UserAgentRunner(persona, scenario)
    user_turns = 0
    all_pairs: list[dict] = []

    async def utter(text: str):
        nonlocal user_turns
        user_turns += 1
        result = await handle_user_turn(db, session, text, role="user_agent")
        if req.autoResolveConflicts:
            for conflict in result.conflicts:
                resolve_conflict(db, conflict, agent.conflict_resolution_action(), None)
        return result

    async def react(products: list[models.Product]):
        """Apply feedback triggers; resolve any conflicts the way this persona would."""
        for step in agent.react_to_products(products):
            fb_result = await handle_feedback(
                db, session,
                product_id=step.product_id,
                feedback_type=step.feedback_type,
                reason_code=step.reason_code,
                reason_text=step.reason_text,
            )
            all_pairs.extend(serializers.pair_to_dict(p) for p in fb_result.pairs)
            if req.autoResolveConflicts:
                for conflict in fb_result.new_conflicts:
                    action = agent.conflict_resolution_action()
                    resolve_conflict(db, conflict, action, None)

    # turn 1 — initial need
    result = await utter(agent.initial_utterance())
    await react(result.products)

    # turn 2 — surface (possibly conflicting) price/novelty preference
    while user_turns < req.maxTurns:
        price_utt = agent.price_preference_utterance()
        if price_utt:
            result = await utter(price_utt)
            await react(result.products)
            continue
        inquiry = agent.inquiry_utterance()
        if inquiry:
            result = await utter(inquiry)
            continue
        # final purchase
        shown = (
            db.query(models.ProductImpression)
            .filter(models.ProductImpression.session_id == session.id)
            .all()
        )
        products = list({i.product_id: db.get(models.Product, i.product_id) for i in shown}.values())
        choice = agent.pick_purchase(products)
        if choice is None:
            break
        result = await utter(agent.purchase_utterance(choice))
        fb_result = await handle_feedback(db, session, product_id=choice.id, feedback_type="purchase")
        all_pairs.extend(serializers.pair_to_dict(p) for p in fb_result.pairs)
        break

    session.status = "completed"
    session.ended_at = datetime.now(timezone.utc)
    db.commit()

    turns = (
        db.query(models.Turn).filter(models.Turn.session_id == session.id)
        .order_by(models.Turn.turn_index).all()
    )
    feedback_events = (
        db.query(models.FeedbackEvent).filter(models.FeedbackEvent.session_id == session.id)
        .order_by(models.FeedbackEvent.created_at).all()
    )
    snapshots = (
        db.query(models.PreferenceStateSnapshot)
        .filter(models.PreferenceStateSnapshot.session_id == session.id)
        .order_by(models.PreferenceStateSnapshot.created_at).all()
    )
    evaluation = evaluate_simulation(db, session, scenario)

    return {
        "sessionId": session.id,
        "session": serializers.session_to_dict(session),
        "turns": [serializers.turn_to_dict(t) for t in turns],
        "feedbackEvents": [serializers.feedback_to_dict(f) for f in feedback_events],
        "preferenceSnapshots": [serializers.snapshot_to_dict(s) for s in snapshots],
        "pairs": all_pairs,
        "evaluation": evaluation,
    }
