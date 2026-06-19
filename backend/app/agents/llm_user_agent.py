"""LLM-driven user agent (합성 갈래 — Nemotron persona 역할 연기).

결정론적 `UserAgentRunner`(user_agent.py)는 수작업 trait persona용이고, Nemotron
persona는 서사형이라 LLM이 연기한다. GT(쇼핑 프로필)는 대화 시작 전에 고정되어
user agent 쪽 LLM 호출에만 들어가며 **session.meta에 절대 저장하지 않는다** —
service agent 파이프라인이 meta를 읽으므로 GT가 새면 복원 평가가 오염된다.

모델: 현재 service agent와 같은 provider(deepseek)를 공유한다 — 같은 모델이면
복원이 prior 공유로 부풀 수 있다는 한계를 인지한 채의 비용 절충(추후 분리 예정,
measurement design M7 참조).
"""
import logging

from sqlalchemy.orm import Session as DbSession

from app.agents.service_agent import handle_feedback, handle_user_turn
from app.core.ids import new_id
from app.db import models, serializers
from app.llm.prompts import SYSTEM_BY_TASK, render_user_context
from app.llm.provider import LLMMessage, get_provider
from app.ontology.state_builder import build_snapshot
from app.preference_commit.conflict_resolver import resolve_conflict

logger = logging.getLogger(__name__)

VALID_REACTIONS = ("like", "dislike", "view_detail")


def _persona_context(persona: dict, profile: dict) -> dict:
    # v2 GT는 시나리오 조건부(valueLevels/motivationLevels), v1은 persona 고정
    # (traitLevels/motivationTendencies) — 키 폴백으로 둘 다 받는다.
    return {
        "name": persona.get("name"),
        "personaNarrative": persona.get("personaNarrative"),
        "demographics": persona.get("demographics"),
        "profile": {
            "valueLevels": profile.get("valueLevels") or profile.get("traitLevels"),
            "motivationLevels": profile.get("motivationLevels") or profile.get("motivationTendencies"),
            "hiddenIntentions": profile.get("hiddenIntentions"),
            "speechStyle": profile.get("speechStyle"),
        },
    }


def _product_brief(p: models.Product) -> dict:
    return {"id": p.id, "title": p.title, "price": p.price, "cueSummary": p.cue_summary or {}}


async def _next_utterance(provider, persona, profile, scenario, history, shown) -> dict:
    context = {
        **_persona_context(persona, profile),
        "scenario": {"id": scenario["id"], "title": scenario.get("title"),
                     "initialUserNeed": scenario.get("initialUserNeed")},
        "history": history,
        "shownProducts": shown,
    }
    out = await provider.generate_json(
        [LLMMessage(role="system", content=SYSTEM_BY_TASK["user_agent_utterance"]),
         LLMMessage(role="user", content=render_user_context(context))],
        task="user_agent_utterance", context=context,
    )
    if not isinstance(out, dict) or not (out.get("utterance") or "").strip():
        return {"utterance": None, "action": "stop", "purchaseProductId": None}
    if out.get("action") not in ("continue", "purchase", "stop"):
        out["action"] = "continue"
    return out


async def _react(provider, persona, profile, products: list[models.Product]) -> list[dict]:
    if not products:
        return []
    context = {
        **_persona_context(persona, profile),
        "products": [_product_brief(p) for p in products],
    }
    out = await provider.generate_json(
        [LLMMessage(role="system", content=SYSTEM_BY_TASK["user_agent_reaction"]),
         LLMMessage(role="user", content=render_user_context(context))],
        task="user_agent_reaction", context=context,
    )
    valid_ids = {p.id for p in products}
    reactions = []
    for r in (out.get("reactions") or []) if isinstance(out, dict) else []:
        if isinstance(r, dict) and r.get("productId") in valid_ids and r.get("type") in VALID_REACTIONS:
            reactions.append(r)
    return reactions


async def run_llm_simulation(
    db: DbSession,
    persona: dict,
    profile: dict,
    scenario: dict,
    max_user_turns: int = 8,
    participant_id: str | None = None,
    gt_version: str | None = None,
) -> dict:
    """한 persona × scenario 합성 대화를 실행하고 검수용 결과를 반환한다.

    participant_id를 주면 세션이 그 Participant에 연결된다 — 가치 누적·spec 문서·
    RIG가 participant 단위로 동작하므로, 멀티 세션 합성은 이 연결이 핵심이다.
    gt_version은 meta에 스탬프만 남긴다(GT 내용은 은닉 원칙상 meta 금지) —
    나중 평가 때 이 세션을 어떤 GT 파일과 대조해야 하는지의 연결고리다.
    """
    provider = get_provider()
    session = models.Session(
        id=new_id("sess"),
        mode="simulation",
        scenario_id=scenario["id"],
        user_agent_id=persona["id"],
        participant_id=participant_id,
        current_stage="exploration",
        status="active",
        meta={
            # GT 프로필은 여기 넣지 않는다 — service agent가 meta를 읽는다 (은닉 원칙)
            "studyCondition": "correctable",
            "category": scenario.get("targetCategory"),
            "shoppingGoal": scenario.get("title"),
            "assignedPersona": persona.get("name"),
            "personaId": persona["id"],
            "llmUserAgent": True,
            "multiSession": participant_id is not None,
            **({"gtVersion": gt_version} if gt_version else {}),
        },
    )
    db.add(session)
    db.flush()
    build_snapshot(db, session)
    db.commit()

    history: list[dict] = []
    shown_products: dict[str, models.Product] = {}
    transcript: list[dict] = []
    purchased: str | None = None
    ended = "max_turns"

    for _ in range(max_user_turns):
        step = await _next_utterance(
            provider, persona, profile, scenario, history,
            [_product_brief(p) for p in shown_products.values()],
        )
        if step["action"] == "stop" or not step.get("utterance"):
            ended = "stop"
            break

        if step["action"] == "purchase" and step.get("purchaseProductId") in shown_products:
            purchased = step["purchaseProductId"]

        result = await handle_user_turn(db, session, step["utterance"], role="user_agent")
        history.append({"role": "user", "content": step["utterance"]})
        history.append({"role": "agent", "content": result.agent_turn.content})
        transcript.append({"role": "user", "content": step["utterance"]})
        transcript.append({"role": "agent", "content": result.agent_turn.content})
        for c in result.conflicts:
            resolve_conflict(db, c, "merge", None)

        if purchased:
            await handle_feedback(db, session, product_id=purchased, feedback_type="purchase")
            transcript.append({"role": "event", "content": f"구매: {shown_products[purchased].title}"})
            ended = "purchase"
            break

        new_products = [p for p in result.products if p.id not in shown_products]
        for p in result.products:
            shown_products[p.id] = p
        if new_products:
            for r in await _react(provider, persona, profile, new_products):
                fb = await handle_feedback(
                    db, session,
                    product_id=r["productId"],
                    feedback_type=r["type"],
                    reason_text=r.get("reasonText"),
                )
                title = shown_products[r["productId"]].title
                transcript.append({
                    "role": "event",
                    "content": f"{r['type']}: {title}" + (f" — \"{r['reasonText']}\"" if r.get("reasonText") else ""),
                })
                for c in fb.new_conflicts:
                    resolve_conflict(db, c, "merge", None)

    session.status = "completed"
    db.commit()

    # 검수용 산출 — 최종 12축 + 추출 의도
    snap = (
        db.query(models.PreferenceStateSnapshot)
        .filter(models.PreferenceStateSnapshot.session_id == session.id)
        .order_by(models.PreferenceStateSnapshot.created_at.desc())
        .first()
    )
    topics = (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id == session.id)
        .filter(models.IntentionTopic.status.notin_(["rejected_by_user", "inactive"]))
        .all()
    )
    return {
        "sessionId": session.id,
        "personaId": persona["id"],
        "personaName": persona.get("name"),
        "scenarioId": scenario["id"],
        "ended": ended,
        "purchasedProductId": purchased,
        "transcript": transcript,
        "anchorScores": (snap.anchor_scores if snap else {}),
        "motivationScores": (snap.motivation_scores if snap else {}),
        "topics": [serializers.topic_to_dict(t) for t in topics],
    }
