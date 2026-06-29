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
from app.agents.action_selector import (
    build_action_decision_context,
    fetch_action_decision,
    select_next_action,
)
from app.agents.question_strategy import (
    _last_agent_action,
    build_value_question,
    pick_diagnostic_anchor,
)
from app.agents import response_generator as rg
from app.ontology.state_builder import build_snapshot
from app.preference_commit.commit_engine import run_preference_commit
from app.products.search import ScoredProduct, search_products
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
                # 연구자용: 이 후보가 검증하려는 가설 축 (사용자 UI에는 비노출 — §36)
                **({"probeAnchor": sp.probe_anchor} if sp.probe_anchor else {}),
            },
        )
        db.add(imp)
        impressions.append(imp)
    db.flush()
    return impressions


def _build_intent_context(session: models.Session, snapshot, recent_turns) -> dict:
    """LLM rerank의 'Goal' — 추출된 사용자 의도(시나리오+토픽+가치·동기). 점수→자연어
    하드코딩 변환 없이, 토픽 라벨·설명·사용자 발화 원본을 주고 LLM이 판단하게 한다."""
    meta = session.meta or {}
    return {
        "scenario": meta.get("shoppingGoal") or meta.get("category") or "",
        "recentUtterances": [t.content for t in recent_turns[-4:] if t.role in ("user", "user_agent")],
        "intentTopics": (snapshot.priority_order or []) if snapshot else [],
        "values_TCV5": {k: v for k, v in (snapshot.anchor_scores or {}).items() if v > 0} if snapshot else {},
        "motivations": {k: v for k, v in (snapshot.motivation_scores or {}).items() if v >= 0.4} if snapshot else {},
        "hierarchyNote": "동기가 가치를 조건짓는다 — 이 쇼핑 동기 맥락에서 가치 기준에 맞게 정렬.",
    }


async def _classify_dialogue_acts(provider, content: str) -> list[str]:
    """화행(dialogue act) 분류 — 발화로 뭘 하는가(reveal/inquire/accept…). PSCon taxonomy.
    ※ IntentionTopic(가치 의도)과 다름. 실패 시 라벨 없음으로 강등.
    (LLM task/출력 키는 PSCon 원문 'intent' 유지 — 내부 계약.)"""
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

    # 4-6. action selection — 구조 가드는 규칙, "추천 vs 질문(+무엇을 probe)"은 action_decision(LLM).
    # category는 더 이상 행동을 가르지 않지만, 상품 검색·clarify 텍스트에는 여전히 쓰인다.
    category = (session.meta or {}).get("category")
    direct_open = any(c.severity == "direct" for c in commit.new_conflicts)
    has_recommendations = (
        db.query(models.ProductImpression)
        .filter(models.ProductImpression.session_id == session.id)
        .count() > 0
    )
    decision = select_next_action(dialogue_acts, direct_open, has_recommendations)

    # 추천하기에 가치·동기를 충분히 아는가? 부족하면 어떤 축(가치5/동기7)을 떠볼까? —
    # 하드코딩 임계값/키워드 대신 LLM이 대화 맥락으로 판단(설계: docs/plans/2026-06-25-action-decision-design.md).
    # RIG 예측은 선제 질문 소스로 LLM에 전달. 가치·동기는 대등(위계 강제 안 함 — 문헌상 미검증).
    value_question: str | None = None
    question_anchor: str | None = None
    if decision.action == "llm_decide":
        snap = commit.snapshot
        pred = None
        try:
            from app import rig

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
        ad = await fetch_action_decision(provider, build_action_decision_context(
            ad_turns, snap, has_recommendations,
            _last_agent_action(db, session.id), pred,
            (session.meta or {}).get("shoppingGoal") or (session.meta or {}).get("category") or "",
        ))
        decision.action = ad["action"]
        decision.reason = ad["reason"] or decision.reason
        if decision.action == "clarify":
            question_anchor = ad["probeDimension"]
            value_question = ad["probeQuestion"]
            if not value_question:  # 폴백: LLM이 질문을 안 주면 기존 가치질문 도구
                value_question, question_anchor = build_value_question(snap, session)

    impressions: list[models.ProductImpression] = []
    products: list[models.Product] = []
    related_ids: list[str] = []
    conflict_explanation: str | None = None

    if decision.action == "clarify":
        text = value_question or rg.clarify_text(category)
        session.current_stage = "clarification"
    elif decision.action == "show_conflict":
        text = rg.conflict_text(commit.new_conflicts[0])
        conflict_explanation = commit.new_conflicts[0].explanation_for_user
        for c in commit.new_conflicts:
            c.status = "shown_to_user"
    elif decision.action == "explain":
        products = _last_recommended_products(db, session.id)
        text = rg.explain_text(products)
        related_ids = [p.id for p in products]
        session.current_stage = "comparison"
    elif decision.action == "close":
        chosen = _last_recommended_products(db, session.id)
        text = rg.close_text(chosen[0] if chosen else None)
        products = chosen[:1]
        session.current_stage = "decision"
    else:  # recommend
        snapshot = commit.snapshot
        # 진단적 trade-off: 가장 불확실한 가설 축을 검증할 후보를 한 슬롯 포함
        diagnostic = pick_diagnostic_anchor(snapshot, session)
        # 검색 질의 보강: 발화 + 카테고리 + 추출된 가치(토픽).
        # 발화("다시 추천해줘")엔 상품정보가 없어, 그동안 끌어낸 가치(내구성·브랜드 등)를
        # 질의에 넣어야 임베딩이 그 가치 단서를 가진 상품을 찾는다. (상품 description의
        # 객관 단서와 의미 매칭 — generate_product_descriptions가 단서를 서술해 둠.)
        scenario_category = (session.meta or {}).get("category")
        # priority 순 상위 토픽만 (너무 많으면 질의가 희석됨)
        value_terms = " ".join((snapshot.priority_order or [])[:4]) if snapshot else ""
        search_query = " ".join(
            part for part in (content, scenario_category, value_terms) if part
        ).strip()
        # 후보 풀(임베딩+필터, 상위 15)을 받아 → LLM rerank(가치·동기) → 다양성으로 3개.
        pool = search_products(
            db,
            query=search_query,
            category=category,
            hard_constraints=snapshot.hard_constraints if snapshot else [],
            soft_preferences=snapshot.soft_preferences if snapshot else [],
            topic_labels=snapshot.priority_order if snapshot else [],
            avoidances=snapshot.avoidances if snapshot else [],
            price_min=snapshot.price_min if snapshot else None,
            price_max=snapshot.price_max if snapshot else None,
            diagnostic_anchor=diagnostic,
            return_pool=True,
            pool_size=15,
        )
        # 답변 초안·순위는 rerank 후 확정한다(아래 recommend 블록). 여기선 후보 풀만 확보.
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
    # 추천이면: LLM rerank(가치·동기로 후보 재정렬 + 카드텍스트) → 다양성 3개. 챗과 병렬.
    card_texts: dict[str, dict] = {}
    scored: list[ScoredProduct] = []
    if decision.action == "recommend":
        from app.products.search import select_tradeoff_set
        intent_context = _build_intent_context(session, commit.snapshot, recent_turns)
        # 가치·동기로 rerank → 다양성 3개를 먼저 확정한 뒤, 그 "실제 노출 셋"에 근거해 답변을 만든다.
        # (이전엔 reply가 pool[:3], 카드가 reranked에 근거해 서로 다른 셋을 가리켰다 — A 수정.)
        reranked, card_texts = await rg.rerank_by_intent(provider, pool, intent_context)
        scored = select_tradeoff_set(reranked, top_k=3, diagnostic_anchor=diagnostic)
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
