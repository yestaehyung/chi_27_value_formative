"""② 플래너 에이전트 — 매개변수화된 액션 결정 (설계: docs/plans/2026-07-02-three-agent-crs-redesign.md).

액션 어휘는 MG-ShopDial(SIGIR'23) 12-intent에서 백엔드 효과 기준으로 도출한 4개
(recommend/clarify/answer/close) + 연구 고유 구조 가드 1개(show_conflict).
recommend는 인자를 갖는다 — searchText(대화 전체를 반영한 독립 검색문, 긍정·주제
신호만)와 constraintsNote(예산·필수·비선호 → rerank가 시맨틱하게 집행). 부정·제약을
임베딩 쿼리에 넣지 않는 분업은 NevIR(EACL'24)의 강제: bi-encoder는 부정을 못 읽는다.

기존 PSCon 화행 가드(accept→close, inquire→explain)는 폐지 — 화행 키워드 멤버십은
혼합 화행에서 오작동(조기 close). close/answer는 문맥 판단이므로 LLM 4-vocab으로.
플래너에 상품 ID는 흐르지 않는다(선별은 recommender 소관).
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session as DbSession

from app.core.conditions import INFERS_INTENTION, normalize_condition
from app.core.locale import product_display_title
from app.db import models

ACTIONS = ("recommend", "clarify", "answer", "close")


@dataclass
class PlannerDecision:
    action: str
    reason: str
    search_text: str | None = None
    constraints_note: str = ""
    probe_dimension: str | None = None
    probe_question: str | None = None
    subtype: str | None = None  # 연구 로그용 MG-ShopDial 입도 (clarify: elicit|repair, answer: factual|justify)
    # 이번에 보여줄 상품 개수 — 대화 맥락에서 LLM이 판단("하나만 골라줘"=1), 코드는
    # 1~5 클램프만. None = 기본 폭(5). 준수 후보가 그보다 적으면 그만큼만 나간다.
    recommend_count: int | None = None


def structural_guard(direct_conflicts_open: bool) -> PlannerDecision | None:
    """유일한 구조 가드 — direct 충돌 객체 존재는 DB 사실이며, 미해소로 두면 그 위의
    추천·피드백 증거가 전부 해석 불능이 되므로 다른 모든 행동에 우선한다."""
    if direct_conflicts_open:
        return PlannerDecision("show_conflict", "open conflict severity is direct")
    return None


def build_planner_context(
    recent_turns,
    snapshot,
    has_recommendations: bool,
    last_agent_action: str | None,
    rag_prediction,
    scenario_goal: str,
    db: DbSession | None = None,
    session: models.Session | None = None,
    window: int = 6,
    last_shown: list | None = None,
) -> dict:
    """플래너에 넘길 컨텍스트 (belt-and-suspenders, 연구 2026-06-25).

    구조화 상태(가치·동기)는 LOSSY — 최근 원문 턴을 *나란히* 둬서 도메인·맥락이 턴을
    넘어 유지되게 한다. searchText 합성을 위해 이 세션의 사용자 발화 전체(userUtterances)와
    피드백 이벤트(feedbackEvents)를 추가로 준다: 스터디 세션은 짧아 전량이 컨텍스트에
    들어가고, 거절·선택은 발화만큼 강한 1급 증거다.

    이론층 가설은 ``hypothesesForClarification`` 아래에만 둔다. planner가 확인 가치가
    있다고 판단하면 clarify 질문의 소재로 쓸 수 있지만, 실제 검색 사양은 이 컨텍스트를
    재사용하지 않고 recommender의 격리된 recommendation policy 단계에서 다시 만든다.
    """
    msgs = [
        {"role": t.role, "content": t.content}
        for t in (recent_turns or [])[-window:]
        if getattr(t, "content", None)
    ]
    if db is not None and session is not None:
        user_utterances = [
            t.content for t in
            db.query(models.Turn)
            .filter(models.Turn.session_id == session.id)
            .filter(models.Turn.role.in_(("user", "user_agent")))
            .order_by(models.Turn.turn_index)
            .all()
            if t.content
        ]
        fb_rows = (
            db.query(models.FeedbackEvent)
            .filter(models.FeedbackEvent.session_id == session.id)
            .order_by(models.FeedbackEvent.created_at.desc())
            .limit(6)
            .all()
        )
        feedback_events = []
        for fb in reversed(fb_rows):
            p = db.get(models.Product, fb.product_id) if fb.product_id else None
            feedback_events.append({
                "type": fb.type,
                "productTitle": product_display_title(p),
                "reasonText": fb.reason_text or fb.reason_code,
            })
    else:  # DB 없이 호출되는 경우(테스트 등) — 최근 턴에서 유도
        user_utterances = [m["content"] for m in msgs if m["role"] in ("user", "user_agent")]
        feedback_events = []
    # 직전 노출 셋 요약 (④′ 2026-07-06) — "더 저렴한 걸로"·"첫 번째 거 비슷한 걸로" 같은
    # 직전-세트 참조 발화의 기준점. 바운딩(제목·가격·카테고리·핵심속성 2)해 컨텍스트 비대 방지.
    # 참조 해소용 읽기 정보일 뿐 — 상품 선별은 여전히 recommender(rerank) 소관.
    from app.products import profiles

    last_shown_summary = []
    for p in last_shown or []:
        prof = profiles.get(p.id) or {}
        last_shown_summary.append({
            "title": p.title, "price": p.price, "category": p.category,
            "keyAttributes": (prof.get("keyAttributes") or [])[:2],
        })
    condition = normalize_condition((session.meta or {}).get("studyCondition")) if session else None
    hypotheses_allowed = (
        INFERS_INTENTION.get(condition, True) if condition is not None else True
    )
    hypothesis_snapshot = snapshot if hypotheses_allowed else None
    return {
        "recentTurns": msgs,
        "userUtterances": user_utterances,
        "feedbackEvents": feedback_events,
        "lastShownProducts": last_shown_summary,
        "recommendationEvidence": {
            "userUtterances": user_utterances,
            "feedbackEvents": feedback_events,
            "lastShownProducts": last_shown_summary,
        },
        "hypothesesForClarification": {
            "values": (
                hypothesis_snapshot.anchor_scores or {}
                if hypothesis_snapshot else {}
            ),
            "motivations": (
                hypothesis_snapshot.motivation_scores or {}
                if hypothesis_snapshot else {}
            ),
            "ragPrediction": rag_prediction if hypotheses_allowed else None,
        },
        "hasRecommendations": has_recommendations,
        "lastAgentAction": last_agent_action,
        "scenarioGoal": scenario_goal,
    }


# 12 vocab (가치5 + 동기7) — probe dimension 검증용 (defense-in-depth)
def _vocab12() -> set[str]:
    from app.ontology.anchor_mapper import MOTIVATION_DIMS, TRAIT_ANCHORS

    return set(TRAIT_ANCHORS) | set(MOTIVATION_DIMS)


async def fetch_plan(provider, context: dict, fallback_search_text: str) -> PlannerDecision:
    """LLM phase (no DB) — 다음 액션과 그 인자를 한 호출로 판단.

    필드별 정규화·폴백(국소 실패 = 국소 강등, `_safe()` 패턴):
    action ∉ 4-vocab → recommend(무한 질문 방지) / searchText 누락 → 현재 발화 /
    dimension ∉ 12-vocab → None. answer·close는 노출 이력이 없으면 성립하지 않으므로
    현실(hasRecommendations)과 대조해 recommend로 강등한다.
    """
    from app.llm.prompts import render_user_context, system_for
    from app.llm.provider import LLMMessage

    try:
        out = await provider.generate_json(
            [LLMMessage(role="system", content=system_for("action_decision")),
             LLMMessage(role="user", content=render_user_context(context))],
            task="action_decision", context=context,
        )
    except Exception:  # noqa: BLE001
        out = {}

    action = out.get("action")
    if action not in ACTIONS:
        action = "recommend"
    if action in ("answer", "close") and not context.get("hasRecommendations"):
        # 노출 이력이 없으면 설명·마무리할 상품이 없다 — 독스트링 계약대로 둘 다 강등
        # (2026-07-06: close만 강등되던 구현 버그 수정 — FS1 실측: 노출 0에서 answer가
        #  통과해 "조금 더 구체적으로…" 빈 응답이 나감).
        action = "recommend"
    if action == "clarify" and context.get("lastAgentAction") == "clarify":
        # 연속 clarify 금지 — mock 계약("직전 clarify→recommend")을 실 경로에 정렬
        # (2026-07-06: flash가 4연속 clarify → 참가자 세션 포기. 프롬프트의 "짧게 한 번"을
        #  작은 모델이 안 지키므로, lastAgentAction이라는 DB 사실로 구조 집행).
        action = "recommend"

    search_text = out.get("searchText")
    if not isinstance(search_text, str) or not search_text.strip():
        # 강등된 recommend는 LLM이 searchText를 안 만든 상태 — 얇은 최신 발화 대신
        # 발화 전량 합성으로 폴백 (mock의 결정론 근사와 동일: 턴1의 도메인이 살아남게).
        utts = [u for u in (context.get("userUtterances") or []) if isinstance(u, str) and u.strip()]
        search_text = " ".join(utts) if utts else fallback_search_text
    constraints_note = out.get("constraintsNote")
    if not isinstance(constraints_note, str):
        constraints_note = ""

    probe = out.get("probe") or {}
    dim = probe.get("dimension")
    if dim not in _vocab12():
        dim = None
    q = probe.get("question")

    subtype = out.get("subtype")
    # 노출 개수 — LLM 판단값을 1~5로 클램프 (어휘 검사만; 판단은 프롬프트).
    try:
        count = int(out.get("recommendCount"))
        count = max(1, min(5, count))
    except (TypeError, ValueError):
        count = None
    return PlannerDecision(
        action=action,
        reason=out.get("reason") or "",
        search_text=search_text.strip(),
        constraints_note=constraints_note.strip(),
        probe_dimension=dim,
        probe_question=q.strip() if isinstance(q, str) and q.strip() else None,
        subtype=subtype if isinstance(subtype, str) else None,
        recommend_count=count,
    )
