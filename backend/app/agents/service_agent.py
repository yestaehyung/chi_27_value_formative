"""Service agent orchestration (spec §13, §28.1, §28.2).

Performance: each LLM-bound stage is timed; logs show "service_agent.stage_latency_sec"
to diagnose turn-level latency bottlenecks.
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session as DbSession

from app.core.ids import new_id
from app.db import models
from app.llm.provider import LLMMessage, get_provider
from app.agents import planner, recommender
from app.agents.question_strategy import (
    _last_agent_action,
    build_value_question,
)
from app.agents import response_generator as rg
from app.ontology.state_builder import build_snapshot
from app.preference_commit.commit_engine import run_preference_commit
from app.products.search import ScoredProduct
from app.wimhf.pair_builder import build_pairs_for_feedback


@dataclass
class AgentTurnResult:
    user_turn: models.Turn
    agent_turn: models.Turn
    impressions: list[models.ProductImpression] = field(default_factory=list)
    products: list[models.Product] = field(default_factory=list)
    snapshot: models.PreferenceStateSnapshot | None = None
    conflicts: list[models.PreferenceConflict] = field(default_factory=list)
    reply_suggestions: list[str] = field(default_factory=list)


@dataclass
class FeedbackResult:
    feedback_event: models.FeedbackEvent
    snapshot: models.PreferenceStateSnapshot | None = None
    new_conflicts: list[models.PreferenceConflict] = field(default_factory=list)
    pairs: list[models.ChosenRejectedPair] = field(default_factory=list)


def _next_turn_index(db: DbSession, session_id: str) -> int:
    last = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session_id)
        .order_by(models.Turn.turn_index.desc())
        .first()
    )
    return (last.turn_index + 1) if last else 0


def _last_recommended_products(db: DbSession, session_id: str) -> list[models.Product]:
    imp_turn = (
        db.query(models.ProductImpression)
        .filter(models.ProductImpression.session_id == session_id)
        .order_by(models.ProductImpression.created_at.desc())
        .first()
    )
    if imp_turn is None:
        return []
    imps = (
        db.query(models.ProductImpression)
        .filter(models.ProductImpression.turn_id == imp_turn.turn_id)
        .order_by(models.ProductImpression.rank)
        .all()
    )
    return [db.get(models.Product, i.product_id) for i in imps]


def _update_surface_intent(session: models.Session, content: str) -> None:
    # 카테고리는 더 이상 키워드로 감지하지 않는다(하드코딩 제거, 2026-06-23).
    # 발화 원문만 보관 — 상품 카테고리는 임베딩/BM25 의미검색이 처리한다.
    meta = dict(session.meta or {})
    surface = dict(meta.get("surfaceIntent", {}))
    surface["explicitQuery"] = content
    meta["surfaceIntent"] = surface
    session.meta = meta


def _create_impressions(
    db: DbSession, session: models.Session, agent_turn: models.Turn,
    scored: list[ScoredProduct], card_texts: dict[str, dict] | None = None,
) -> list[models.ProductImpression]:
    impressions = []
    card_texts = card_texts or {}
    for rank, sp in enumerate(scored, start=1):
        # 카드 설명은 LLM 생성(generate_card_rationales) — 사용자 가치에 연결(B1).
        # 누락 시 폴백(빈 reason 방지). BUCKET_PHRASE/규칙 matched·weak는 더 이상 안 씀.
        card = card_texts.get(sp.product.id) or {}
        imp = models.ProductImpression(
            id=new_id("imp"),
            session_id=session.id,
            turn_id=agent_turn.id,
            product_id=sp.product.id,
            rank=rank,
            recommendation_reason=card.get("reason", ""),
            matched_intentions=card.get("matched", []),
            weak_intentions=card.get("weak", []),
            product_cues_shown={
                "price": True, "rating": True, "reviewCount": True,
                "longTermReviewRatio": True, "recentSalesCount": True,
                "sellerGrade": True, "deliveryFee": True,
            },
        )
        db.add(imp)
        impressions.append(imp)
    db.flush()
    return impressions


async def _classify_dialogue_acts(provider, content: str) -> list[str]:
    """화행(dialogue act) 분류 — annotation 전용 (연구 로그). 2026-07-02부터 행동 결정에
    쓰지 않는다: 화행 키워드 가드(accept→close 등)는 혼합 화행에서 오작동해 폐지, 판단은
    플래너 LLM으로 이동 (docs/plans/2026-07-02-three-agent-crs-redesign.md).
    실패 시 라벨 없음으로 강등. (LLM task/출력 키는 PSCon 원문 'intent' 유지 — 내부 계약.)"""
    try:
        out = await provider.generate_json(
            [LLMMessage(role="user", content=content)],
            task="intent_classification", context={"content": content},
        )
        return [i for i in (out.get("intents") or []) if isinstance(i, str)]
    except Exception:  # noqa: BLE001
        return []


async def handle_user_turn(db: DbSession, session: models.Session, content: str,
                           role: str = "user") -> AgentTurnResult:
    provider = get_provider()
    t0 = time.perf_counter()

    # 1-2. save user turn + dialogue-act classification.
    # 동기 층(M8) 감지는 commit engine으로 이동 — 라이브·시뮬·PSCon이 같은 경로로 12축.
    user_turn = models.Turn(
        id=new_id("turn"),
        session_id=session.id,
        turn_index=_next_turn_index(db, session.id),
        role=role,
        content=content,
        dialogue_acts=[],  # 화행은 아래 병렬 분류 후 채운다
    )
    db.add(user_turn)
    _update_surface_intent(session, content)
    # commit immediately so the write lock is NOT held during the LLM pipeline
    db.commit()

    # 2-3. 화행 분류와 preference commit는 서로 의존이 없다(둘 다 발화만 읽음) → 병렬로 1 RT 절약.
    #      _classify_dialogue_acts는 DB를 만지지 않으므로 commit과 같은 session을 동시 사용해도 안전.
    t_pipe = time.perf_counter()
    dialogue_acts, commit = await asyncio.gather(
        _classify_dialogue_acts(provider, content),
        run_preference_commit(
            db, provider, session, turn_ids=[user_turn.id], feedback_ids=[], source="user_utterance",
        ),
    )
    user_turn.dialogue_acts = dialogue_acts
    db.commit()
    logging.info("service_agent.turn_pipeline_latency_sec=%.3f", time.perf_counter() - t_pipe)

    # 4-6. 플래닝(②) — 구조 가드는 show_conflict 하나(DB 사실). 나머지는 플래너 LLM이
    # 매개변수화된 액션을 결정: recommend(searchText, constraintsNote) / clarify(dimension,
    # question) / answer / close (설계: docs/plans/2026-07-02-three-agent-crs-redesign.md).
    category = (session.meta or {}).get("category")
    direct_open = any(c.severity == "direct" for c in commit.new_conflicts)
    has_recommendations = (
        db.query(models.ProductImpression)
        .filter(models.ProductImpression.session_id == session.id)
        .count() > 0
    )
    decision = planner.structural_guard(direct_open)
    if decision is None:
        pred = None
        try:
            from app import rig

            # 이론층의 cross-session 가설 — 별도 tier가 아니라 플래너 컨텍스트 필드.
            pred = rig.top_predicted_concept(db, session.id)
        except Exception:  # noqa: BLE001
            pred = None
        # 최근 대화 윈도우(원문) + 구조화 상태를 함께 — 도메인·맥락이 턴을 넘어 유지되게.
        ad_turns = list(reversed(
            db.query(models.Turn)
            .filter(models.Turn.session_id == session.id)
            .order_by(models.Turn.turn_index.desc())
            .limit(6).all()
        ))
        decision = await planner.fetch_plan(
            provider,
            planner.build_planner_context(
                ad_turns, commit.snapshot, has_recommendations,
                _last_agent_action(db, session.id), pred,
                (session.meta or {}).get("shoppingGoal") or category or "",
                db=db, session=session,
            ),
            fallback_search_text=content.strip(),
        )
        if decision.action == "clarify" and not decision.probe_question:
            # 폴백: LLM이 질문을 안 주면 기존 가치질문 도구
            decision.probe_question, decision.probe_dimension = build_value_question(
                commit.snapshot, session,
            )

    impressions: list[models.ProductImpression] = []
    products: list[models.Product] = []
    related_ids: list[str] = []
    conflict_explanation: str | None = None
    value_question: str | None = None

    if decision.action == "clarify":
        value_question = decision.probe_question
        text = value_question or rg.clarify_text(category)
        session.current_stage = "clarification"
    elif decision.action == "show_conflict":
        text = rg.conflict_text(commit.new_conflicts[0])
        conflict_explanation = commit.new_conflicts[0].explanation_for_user
        for c in commit.new_conflicts:
            c.status = "shown_to_user"
    elif decision.action == "answer":
        # 노출된 상품·상품 지식에 대한 질문에 답한다 (MG-ShopDial Answer+Explain 병합) —
        # 새 검색 없이 마지막 노출 셋 + 대화를 근거로. 렌더러(generate_reply)가 최종 저작.
        products = _last_recommended_products(db, session.id)
        text = rg.explain_text(products)
        related_ids = [p.id for p in products]
        session.current_stage = "comparison"
    elif decision.action == "close":
        chosen = _last_recommended_products(db, session.id)
        text = rg.close_text(chosen[0] if chosen else None)
        products = chosen[:1]
        session.current_stage = "decision"
    else:  # recommend — 실행(검색→rerank→3개)은 추천 에이전트(③)가 아래에서 수행.
        session.current_stage = "recommendation"

    # real LLM providers rewrite the template grounded on context (mock returns it as-is)
    recent_turns = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session.id)
        .order_by(models.Turn.turn_index)
        .all()
    )
    t_reply = time.perf_counter()
    state_for_llm = commit.snapshot.user_visible_summary if commit.snapshot else None
    # 추천이면: 추천 에이전트(③)가 검색 사양을 실행 — 임베딩 검색 → rerank(제약·기준 집행,
    # stated+confirmed만 읽음) → trade-off 3개를 먼저 확정한 뒤, 그 "실제 노출 셋"에 근거해
    # 답변을 만든다.
    card_texts: dict[str, dict] = {}
    scored: list[ScoredProduct] = []
    if decision.action == "recommend":
        scored, card_texts = await recommender.run_recommendation(
            db, provider, session,
            search_text=decision.search_text or content.strip(),
            constraints_note=decision.constraints_note,
            recent_turns=recent_turns,
            snapshot=commit.snapshot,
        )
        products = [sp.product for sp in scored]
        related_ids = [p.id for p in products]
        text = await rg.generate_reply(
            provider, action=decision.action, template_text=rg.recommend_text(products),
            recent_turns=recent_turns, products=products, state_summary=state_for_llm,
            conflict_explanation=conflict_explanation, must_ask_question=value_question,
        )
    else:
        text = await rg.generate_reply(
            provider, action=decision.action, template_text=text, recent_turns=recent_turns,
            products=products, state_summary=state_for_llm,
            conflict_explanation=conflict_explanation, must_ask_question=value_question,
        )
    logging.info("service_agent.generate_reply_latency_sec=%.3f", time.perf_counter() - t_reply)

    # 입력창 위 답변 칩 — 방금 에이전트 말(text)에 이어지는 사용자 후보 (맥락 의존 → reply 후 생성)
    reply_suggestions = await rg.generate_reply_suggestions(
        provider, decision.action, text, state_for_llm,
    )

    agent_turn = models.Turn(
        id=new_id("turn"),
        session_id=session.id,
        turn_index=_next_turn_index(db, session.id),
        role="service_agent",
        content=text,
        agent_action=decision.action,
        related_product_ids=related_ids,
    )
    db.add(agent_turn)
    db.flush()

    if decision.action == "recommend":
        scored_by_id = {sp.product.id: sp for sp in scored}
        impressions = _create_impressions(
            db, session, agent_turn, [scored_by_id[p.id] for p in products], card_texts
        )

    db.commit()

    # 참가자 자연어 명세(AI memory) 보완 — 이번 턴의 KG 변화를 반영 (semantic commit)
    if session.participant_id:
        try:
            from app.spec_builder import update_participant_spec

            t_spec = time.perf_counter()
            update_participant_spec(db, session.participant_id)
            logging.info("service_agent.update_participant_spec_latency_sec=%.3f", time.perf_counter() - t_spec)
        except Exception:  # noqa: BLE001
            pass

    logging.info("service_agent.total_turn_latency_sec=%.3f", time.perf_counter() - t0)
    return AgentTurnResult(
        user_turn=user_turn,
        agent_turn=agent_turn,
        impressions=impressions,
        products=products,
        snapshot=commit.snapshot,
        conflicts=commit.new_conflicts,
        reply_suggestions=reply_suggestions,
    )


VALENCE_BY_TYPE = {
    "like": "positive", "purchase": "positive", "add_to_cart": "positive",
    "view_detail": "positive", "click": "positive", "compare": "neutral",
    "dislike": "negative", "reject": "negative",
    "quick_reason": "neutral", "manual_correction": "neutral",
}


async def handle_feedback(
    db: DbSession,
    session: models.Session,
    product_id: str,
    feedback_type: str,
    reason_code: str | None = None,
    reason_text: str | None = None,
    turn_id: str | None = None,
) -> FeedbackResult:
    provider = get_provider()

    if turn_id is None:
        last_imp = (
            db.query(models.ProductImpression)
            .filter(models.ProductImpression.session_id == session.id)
            .filter(models.ProductImpression.product_id == product_id)
            .order_by(models.ProductImpression.created_at.desc())
            .first()
        )
        turn_id = last_imp.turn_id if last_imp else None

    fb = models.FeedbackEvent(
        id=new_id("fb"),
        session_id=session.id,
        turn_id=turn_id,
        product_id=product_id,
        type=feedback_type,
        valence=VALENCE_BY_TYPE.get(feedback_type, "neutral"),
        reason_code=reason_code,
        reason_text=reason_text,
    )
    db.add(fb)
    # commit immediately so the write lock is NOT held during the LLM pipeline
    db.commit()

    # chosen-rejected pairs within the same recommendation turn (spec §10, §11 Phase A)
    pairs = await build_pairs_for_feedback(db, provider, session, fb)

    # preference commit on the feedback evidence
    commit = await run_preference_commit(
        db, provider, session, turn_ids=[], feedback_ids=[fb.id], source="feedback",
    )

    if feedback_type == "purchase":
        session.current_stage = "post_decision"
        db.commit()

    return FeedbackResult(
        feedback_event=fb,
        snapshot=commit.snapshot,
        new_conflicts=commit.new_conflicts,
        pairs=pairs,
    )
