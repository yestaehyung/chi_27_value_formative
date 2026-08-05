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
from app.core.conditions import INFERS_INTENTION, normalize_condition
from app.ontology.state_builder import build_snapshot
from app.preference_commit.commit_engine import PreferenceCommitResult, run_preference_commit
from app.products.search import ScoredProduct
from app.wimhf.pair_builder import build_pairs_for_feedback


def infers_intention(session: models.Session) -> bool:
    """이 세션의 조건이 사용자 모델(의도 추론)을 돌리는가.

    조건이 없는 세션(데모·시뮬레이션·로컬 개발)은 **추론한다**로 본다 — 조건 설계는 본실험
    참가자에게만 적용되고, 나머지는 종래대로 전체 파이프라인이 돌아야 한다.
    """
    slug = normalize_condition((session.meta or {}).get("studyCondition"))
    return INFERS_INTENTION.get(slug, True) if slug else True


async def _no_commit() -> PreferenceCommitResult:
    """baseline1용 빈 커밋 결과. asyncio.gather에 넣기 위해 코루틴이어야 한다."""
    return PreferenceCommitResult()


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
    # 탐색 클릭(자세히)의 상호작용 응답 — 상품 설명 + 궁금점 질문 턴 (2026-07-03)
    agent_turn: models.Turn | None = None
    reply_suggestions: list[str] = field(default_factory=list)


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
        # 카드 설명은 rerank가 순위와 함께 생성(rerank_by_intent의 card_texts) — 사용자 가치에 연결(B1).
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


async def recommend_after_resolution(
    db: DbSession, session: models.Session, snapshot: models.PreferenceStateSnapshot,
) -> tuple[models.Turn, list[models.ProductImpression], list[models.Product]]:
    """충돌 해소로 기준이 바뀐 직후 갱신된 기준으로 바로 재추천한다(해소가 dead-end가
    되지 않게). resolve_conflict가 이미 commit한 뒤(락 해제) 호출되므로 LLM-first-write-last
    유지 — LLM(추천·렌더)을 먼저 돌리고 마지막에 짧은 트랜잭션으로 turn·impression을 쓴다."""
    provider = get_provider()
    category = (session.meta or {}).get("category")
    prev_shown = _last_recommended_products(db, session.id)
    recent_turns = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session.id)
        .order_by(models.Turn.turn_index)
        .all()
    )
    has_recommendations = (
        db.query(models.ProductImpression)
        .filter(models.ProductImpression.session_id == session.id)
        .count() > 0
    )
    pred = None
    try:
        from app import rig
        pred = rig.top_predicted_concept(db, session.id)
    except Exception:  # noqa: BLE001
        pred = None
    planner_context = planner.build_planner_context(
        recent_turns[-6:], snapshot, has_recommendations,
        _last_agent_action(db, session.id), pred,
        (session.meta or {}).get("shoppingGoal") or category or "",
        db=db, session=session, last_shown=prev_shown,
    )
    # 해소 직후엔 재추천이 목적 — 플래너 searchText를 쓰되 없으면 최근 사용자 발화로 폴백,
    # 액션과 무관하게 recommend를 실행한다(갱신된 기준으로 상품을 바로 보여주는 게 목적).
    last_user = next((t.content for t in reversed(recent_turns) if t.role == "user"), "")
    decision = await planner.fetch_plan(provider, planner_context, fallback_search_text=last_user)
    search_text = decision.search_text or last_user or ((session.meta or {}).get("shoppingGoal") or "")
    scored, card_texts, rec_diag = await recommender.run_recommendation(
        db, provider, session, search_text=search_text,
        constraints_note=decision.constraints_note, recent_turns=recent_turns, snapshot=snapshot,
    )
    products = [sp.product for sp in scored]
    state_for_llm = snapshot.user_visible_summary if snapshot else None
    near_miss = (rec_diag or {}).get("nearMiss") or {}
    rec_note = None
    if near_miss or not scored:
        rec_note = {
            "noExactMatch": True,
            "nearestAlternatives": [
                {"title": p.title, "differsHow": near_miss.get(p.id, "")} for p in products
            ],
        }
        template = rg.near_miss_text(scored)
    else:
        template = rg.recommend_text(scored)
    text = await rg.generate_reply(
        provider, action="recommend", template_text=template, recent_turns=recent_turns,
        products=products, state_summary=state_for_llm, conflict_explanation=None,
        must_ask_question=None, previously_shown=prev_shown, recommendation_note=rec_note,
    )
    agent_turn = models.Turn(
        id=new_id("turn"), session_id=session.id,
        turn_index=_next_turn_index(db, session.id), role="service_agent",
        content=text, agent_action="recommend",
        related_product_ids=[p.id for p in products],
    )
    db.add(agent_turn)
    db.flush()
    scored_by_id = {sp.product.id: sp for sp in scored}
    impressions = _create_impressions(
        db, session, agent_turn, [scored_by_id[p.id] for p in products], card_texts
    )
    db.commit()
    return agent_turn, impressions, products


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
    #      baseline1은 의도 추론 자체가 없는 조건이므로 commit을 건너뛴다 — 빈 결과(토픽·충돌
    #      없음, snapshot None)로 이후 단계가 그대로 흐른다(§조건 설계: core/conditions.py).
    t_pipe = time.perf_counter()
    dialogue_acts, commit = await asyncio.gather(
        _classify_dialogue_acts(provider, content),
        run_preference_commit(
            db, provider, session, turn_ids=[user_turn.id], feedback_ids=[], source="user_utterance",
        ) if infers_intention(session) else _no_commit(),
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
    # 직전 노출 셋 — 새 impression 저장 전인 이 시점에 잡아야 "직전"이다. 두 소비처:
    # ① planner 컨텍스트(④′ — "더 저렴한 걸로" 같은 직전-세트 참조의 기준점),
    # ② renderer(previouslyShownProducts — 과거 노출 언급의 근거, 2026-07-03).
    prev_shown = _last_recommended_products(db, session.id)
    recent_turns = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session.id)
        .order_by(models.Turn.turn_index)
        .all()
    )
    decision = planner.structural_guard(direct_open)
    # 플래너 컨텍스트 — 최근 대화 윈도우(원문) + 구조화 상태를 함께 넘겨 도메인·맥락이
    # 턴을 넘어 유지되게 한다.
    planner_context = None
    if decision is None:
        pred = None
        try:
            from app import rig

            # 이론층의 cross-session 가설 — 별도 tier가 아니라 플래너 컨텍스트 필드.
            pred = rig.top_predicted_concept(db, session.id)
        except Exception:  # noqa: BLE001
            pred = None
        planner_context = planner.build_planner_context(
            recent_turns[-6:], commit.snapshot, has_recommendations,
            _last_agent_action(db, session.id), pred,
            (session.meta or {}).get("shoppingGoal") or category or "",
            db=db, session=session, last_shown=prev_shown,
        )
    if decision is None:
        decision = await planner.fetch_plan(
            provider, planner_context, fallback_search_text=content.strip(),
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
        products = prev_shown
        text = rg.explain_text(products)
        related_ids = [p.id for p in products]
        session.current_stage = "comparison"
    elif decision.action == "close":
        text = rg.close_text(prev_shown[0] if prev_shown else None)
        products = prev_shown[:1]
        session.current_stage = "decision"
    else:  # recommend — 실행(검색→rerank→3개)은 추천 에이전트(③)가 아래에서 수행.
        session.current_stage = "recommendation"

    # real LLM providers rewrite the template grounded on context (mock returns it as-is)
    t_reply = time.perf_counter()
    state_for_llm = commit.snapshot.user_visible_summary if commit.snapshot else None
    # 추천이면: 추천 에이전트(③)가 검색 사양을 실행 — 임베딩 검색 → rerank(제약·기준 집행,
    # stated+confirmed만 읽음) → trade-off 3개를 먼저 확정한 뒤, 그 "실제 노출 셋"에 근거해
    # 답변을 만든다.
    card_texts: dict[str, dict] = {}
    scored: list[ScoredProduct] = []
    rec_diag: dict | None = None
    if decision.action == "recommend":
        scored, card_texts, rec_diag = await recommender.run_recommendation(
            db, provider, session,
            search_text=decision.search_text or content.strip(),
            constraints_note=decision.constraints_note,
            recent_turns=recent_turns,
            snapshot=commit.snapshot,
        )
        products = [sp.product for sp in scored]
        related_ids = [p.id for p in products]
        # ② 부분 정직 (2026-07-07): 노출 전체가 근접 대안이면(준수 후보 0 = rerank의
        # 출력 사실) 정직 초안 + recommendationNote로 렌더러가 부재를 먼저 고지하게 한다.
        near_miss = rec_diag.get("nearMiss") or {}
        rec_note = None
        if near_miss or not scored:
            rec_note = {
                "noExactMatch": True,
                "nearestAlternatives": [
                    {"title": p.title, "differsHow": near_miss.get(p.id, "")}
                    for p in products
                ],
            }
            template = rg.near_miss_text(scored)
        else:
            template = rg.recommend_text(scored)
        text = await rg.generate_reply(
            provider, action=decision.action, template_text=template,
            recent_turns=recent_turns, products=products, state_summary=state_for_llm,
            conflict_explanation=conflict_explanation, must_ask_question=value_question,
            previously_shown=prev_shown, recommendation_note=rec_note,
        )
    else:
        text = await rg.generate_reply(
            provider, action=decision.action, template_text=text, recent_turns=recent_turns,
            products=products, state_summary=state_for_llm,
            conflict_explanation=conflict_explanation, must_ask_question=value_question,
            previously_shown=prev_shown,
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

    # 플래너·rerank 의사결정 기록 (llm_calls) — 사후 디버깅/검색품질 분석용 (2026-07-06).
    # '사수 선물' 사례에서 로그 부재로 searchText·풀을 재구성해야 했던 공백을 메운다.
    # 로깅 실패가 턴을 깨면 안 되므로 통째로 _safe 성격의 try로 감싼다.
    try:
        from app.core.config import settings as _settings

        if decision.action != "show_conflict":  # 구조 가드 턴은 LLM 판단이 없음
            db.add(models.LLMCall(
                id=new_id("llm"), session_id=session.id, task="action_decision",
                provider=_settings.llm_provider,
                request={"turnId": agent_turn.id, "utterance": content[:500]},
                response={"action": decision.action, "reason": decision.reason,
                          "searchText": decision.search_text,
                          "constraintsNote": decision.constraints_note,
                          "probeDimension": decision.probe_dimension,
                          "subtype": decision.subtype},
            ))
        if rec_diag is not None:
            db.add(models.LLMCall(
                id=new_id("llm"), session_id=session.id, task="rerank",
                provider=_settings.llm_provider,
                request={"turnId": agent_turn.id, **{k: rec_diag[k] for k in
                         ("searchText", "constraintsNote", "poolSize", "pool", "rerankContext")}},
                response={"shownIds": rec_diag["shownIds"]},
            ))
    except Exception:  # noqa: BLE001
        logging.warning("llm_calls logging failed", exc_info=True)

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

    # 탐색 클릭(자세히 등)은 선호 표명이 아니라 호기심일 수 있다 — 커밋 엔진(토픽 생성)을
    # 태우지 않고, 상품을 설명하며 무엇이 궁금한지 되묻는 상호작용으로 전환한다 (2026-07-03).
    # 실사례: 최고가 상품 자세히 클릭 1건 → '가격 부담' 토픽 날조(conf 0.9) → 유령 충돌 카드.
    # 사용자의 답변이 일반 턴 파이프라인을 타고 진짜 명시 증거가 된다. FeedbackEvent 로그는 유지.
    if feedback_type in ("view_detail", "click"):
        return await _handle_detail_view(db, provider, session, product_id, fb)

    # chosen-rejected pairs within the same recommendation turn (spec §10, §11 Phase A)
    pairs = await build_pairs_for_feedback(db, provider, session, fb)

    # preference commit on the feedback evidence (baseline1은 추론 없음 — 위와 동일)
    commit = await (
        run_preference_commit(db, provider, session, turn_ids=[], feedback_ids=[fb.id], source="feedback")
        if infers_intention(session) else _no_commit()
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


async def _handle_detail_view(
    db: DbSession,
    provider,
    session: models.Session,
    product_id: str,
    fb: models.FeedbackEvent,
) -> FeedbackResult:
    """자세히 클릭 → 해당 상품 설명 + "어떤 점이 궁금하세요?" 턴 (2026-07-03).

    conflict_resolver의 해소-턴 영속화 패턴 재사용 — 새로고침·연구 replay에 남는다.
    LLM-first-write-last: 렌더링(LLM)은 락 없이, Turn 기록은 짧은 트랜잭션으로."""
    from app.products import profiles

    product = db.get(models.Product, product_id)
    if product is None:  # 방어 — API 레이어에서 이미 404 처리됨
        return FeedbackResult(feedback_event=fb)

    recent_turns = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session.id)
        .order_by(models.Turn.turn_index)
        .all()
    )
    snapshot = (
        db.query(models.PreferenceStateSnapshot)
        .filter(models.PreferenceStateSnapshot.session_id == session.id)
        .order_by(models.PreferenceStateSnapshot.created_at.desc())
        .first()
    )
    template = rg.detail_text(product, profiles.get(product.id))
    text = await rg.generate_reply(
        provider, action="answer", template_text=template,
        recent_turns=recent_turns, products=[product],
        state_summary=snapshot.user_visible_summary if snapshot else None,
        must_ask_question="이 상품에서 어떤 점이 궁금하신가요?",
        previously_shown=_last_recommended_products(db, session.id),
    )

    turn = models.Turn(
        id=new_id("turn"),
        session_id=session.id,
        turn_index=_next_turn_index(db, session.id),
        role="service_agent",
        content=text,
        agent_action="detail",  # 연구 로그용 — planner 4-vocab 아님(UI 트리거)
        related_product_ids=[product.id],
    )
    db.add(turn)
    db.commit()

    suggestions = await rg.generate_reply_suggestions(
        provider, "detail", text, snapshot.user_visible_summary if snapshot else None,
    )
    return FeedbackResult(feedback_event=fb, agent_turn=turn, reply_suggestions=suggestions)
