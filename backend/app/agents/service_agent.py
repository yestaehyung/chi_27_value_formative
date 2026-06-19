"""Service agent orchestration (spec §13, §28.1, §28.2)."""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session as DbSession

from app.core.ids import new_id
from app.db import models
from app.llm.provider import LLMMessage, get_provider
from app.agents.action_selector import select_next_action
from app.agents.question_strategy import (
    build_value_question,
    pick_diagnostic_anchor,
    should_value_clarify,
)
from app.agents import response_generator as rg
from app.ontology.state_builder import build_snapshot
from app.preference_commit.commit_engine import run_preference_commit
from app.products.search import ScoredProduct, detect_category, search_products
from app.wimhf.pair_builder import build_pairs_for_feedback


@dataclass
class AgentTurnResult:
    user_turn: models.Turn
    agent_turn: models.Turn
    impressions: list[models.ProductImpression] = field(default_factory=list)
    products: list[models.Product] = field(default_factory=list)
    snapshot: models.PreferenceStateSnapshot | None = None
    conflicts: list[models.PreferenceConflict] = field(default_factory=list)


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
    meta = dict(session.meta or {})
    surface = dict(meta.get("surfaceIntent", {}))
    category = detect_category(content)
    if category:
        surface["productCategory"] = category
    surface["explicitQuery"] = content
    meta["surfaceIntent"] = surface
    session.meta = meta


def _create_impressions(
    db: DbSession, session: models.Session, agent_turn: models.Turn, scored: list[ScoredProduct]
) -> list[models.ProductImpression]:
    impressions = []
    for rank, sp in enumerate(scored, start=1):
        imp = models.ProductImpression(
            id=new_id("imp"),
            session_id=session.id,
            turn_id=agent_turn.id,
            product_id=sp.product.id,
            rank=rank,
            recommendation_reason=rg.BUCKET_PHRASE.get(sp.bucket, ""),
            matched_intentions=sp.matched,
            weak_intentions=sp.weak,
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


async def _classify_intents(provider, content: str) -> list[str]:
    """Intent 분류 (실패 시 라벨 없음으로 강등)."""
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

    # 1-2. save user turn + intent classification.
    # 동기 층(M8) 감지는 commit engine으로 이동 — 라이브·시뮬·PSCon이 같은 경로로 12축.
    intents = await _classify_intents(provider, content)
    user_turn = models.Turn(
        id=new_id("turn"),
        session_id=session.id,
        turn_index=_next_turn_index(db, session.id),
        role=role,
        content=content,
        intent_labels=intents,
    )
    db.add(user_turn)
    _update_surface_intent(session, content)
    # commit immediately so the write lock is NOT held during the LLM pipeline
    db.commit()

    # 3. preference commit on the new utterance
    commit = await run_preference_commit(
        db, provider, session, turn_ids=[user_turn.id], feedback_ids=[], source="user_utterance",
    )

    # 4-6. action selection
    # detect_category가 모르는 카테고리(니트·원피스 등)는 시나리오 targetCategory로 폴백한다.
    # 폴백이 없으면 category=None → select_next_action이 영영 clarify에 갇혀 추천을 못 한다.
    surface = (session.meta or {}).get("surfaceIntent", {})
    category = surface.get("productCategory") or (session.meta or {}).get("category")
    direct_open = any(c.severity == "direct" for c in commit.new_conflicts)
    has_recommendations = (
        db.query(models.ProductImpression)
        .filter(models.ProductImpression.session_id == session.id)
        .count() > 0
    )
    decision = select_next_action(session, intents, direct_open, category, has_recommendations)

    # 가치 수준 적응형 질문 (S3 정보격차 판단): 추천하기에 기준이 부족하면
    # 속성 질문 대신 가치 질문으로 implicit intention을 끌어낸다
    value_question: str | None = None
    question_anchor: str | None = None
    if decision.action == "recommend" and should_value_clarify(
        db, session, commit.snapshot, has_recommendations
    ):
        decision.action = "clarify"
        # 질문 우선순위:
        #  (1) 아직 안 드러난 쇼핑 동기 프로브 (설문 동등 정보를 대화로 수집)
        #  (2) RIG 경로 예측 기반 선제 질문
        #  (3) 가치(trait) 수준 적응형 질문
        from app.agents.motivation import next_probe

        probe = next_probe((session.meta or {}).get("motivationScores", {}), session.meta or {})
        pred = None
        if not probe:
            try:
                from app import rig

                pred = rig.top_predicted_concept(db, session.id)
            except Exception:  # noqa: BLE001
                pred = None
        if probe:
            decision.reason = f"motivation probe (dim={probe[1]})"
            value_question = probe[0]
        elif pred:
            decision.reason = f"anticipatory question from RIG path (concept={pred['normalizedLabel']})"
            value_question = (
                f"비슷한 분들은 '{pred['exampleIntention']}'도 중요하게 보시던데, "
                f"이 부분도 신경 쓰이세요?"
            )
            question_anchor = pred.get("topAnchor")
        else:
            decision.reason = "information gap — value-level question first"
            value_question, question_anchor = build_value_question(commit.snapshot, session)

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
        # 검색 질의 앵커: 해명성 답변("혼자 고르고 싶어요")엔 상품어가 없어 적합도가 무너진다.
        # 통제 시나리오의 targetCategory(session.meta["category"])를 질의에 붙여 매 턴 상품
        # 도메인을 고정한다. custom 시나리오는 category가 없으니 발화만 사용 (자유 탐색).
        scenario_category = (session.meta or {}).get("category")
        search_query = f"{content} {scenario_category}".strip() if scenario_category else content
        scored = search_products(
            db,
            query=search_query,
            category=category,
            hard_constraints=snapshot.hard_constraints if snapshot else [],
            soft_preferences=snapshot.soft_preferences if snapshot else [],
            topic_labels=snapshot.priority_order if snapshot else [],
            avoidances=snapshot.avoidances if snapshot else [],
            top_k=3,
            diversify_by_tradeoff=True,
            diagnostic_anchor=diagnostic,
        )
        text = rg.recommend_text(scored)
        session.current_stage = "recommendation"
        products = [sp.product for sp in scored]
        related_ids = [p.id for p in products]

    # real LLM providers rewrite the template grounded on context (mock returns it as-is)
    recent_turns = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session.id)
        .order_by(models.Turn.turn_index)
        .all()
    )
    text = await rg.generate_reply(
        provider,
        action=decision.action,
        template_text=text,
        recent_turns=recent_turns,
        products=products,
        state_summary=(commit.snapshot.user_visible_summary if commit.snapshot else None),
        conflict_explanation=conflict_explanation,
        must_ask_question=value_question,
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
            db, session, agent_turn, [scored_by_id[p.id] for p in products]
        )

    db.commit()

    # 참가자 자연어 명세(AI memory) 보완 — 이번 턴의 KG 변화를 반영 (semantic commit)
    if session.participant_id:
        try:
            from app.spec_builder import update_participant_spec

            update_participant_spec(db, session.participant_id)
        except Exception:  # noqa: BLE001
            pass

    return AgentTurnResult(
        user_turn=user_turn,
        agent_turn=agent_turn,
        impressions=impressions,
        products=products,
        snapshot=commit.snapshot,
        conflicts=commit.new_conflicts,
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
