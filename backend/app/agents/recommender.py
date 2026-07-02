"""③ 추천 에이전트 — recommend(searchText, constraintsNote)의 실행
(설계: docs/plans/2026-07-02-three-agent-crs-redesign.md).

[임베딩 검색: 도구] → LLM rerank(제약·기준 집행) → trade-off 3개.

evidence-purity 규칙: rerank가 읽는 것은 **stated(명시 발화) + confirmed(사용자
확인 기준)뿐** — 미확인 배후 추론(anchor/motivation 원점수)은 랭킹에 넣지 않는다.
(1) 미확인 추론이 추천에 들어가면 피드백 증거가 오염되고, (2) 칩 수정→confirmed→
다음 추천 반영이라는 correctable 조건의 인과 경로가 이 필터로 구조적으로 보장된다.
이론층(가치·동기)이 추천에 닿는 유일한 경로는 플래너의 가설 확인 질문을 거쳐
confirmed가 되는 것(가설 경로).
"""
from sqlalchemy.orm import Session as DbSession

from app.db import models
from app.agents import response_generator as rg
from app.products.search import ScoredProduct, search_products


def _stated_and_confirmed_criteria(db: DbSession, session_id: str) -> list[dict]:
    """추천이 읽어도 되는 기준: 명시 발화에서 온 토픽(explicit) 또는 사용자가 확인한
    토픽(confirmed/corrected_by_user). 거부·비활성은 제외."""
    topics = (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id == session_id)
        .filter(models.IntentionTopic.status.notin_(("rejected_by_user", "inactive")))
        .all()
    )
    out = []
    for t in topics:
        if t.explicitness == "explicit" or t.status in ("confirmed", "corrected_by_user"):
            out.append({"label": t.label, "description": t.description})
    return out


def build_rerank_context(
    db: DbSession,
    session: models.Session,
    recent_turns,
    constraints_note: str,
) -> dict:
    """rerank의 'Goal' — 발화 원문 + 명시·확인 기준 + 플래너의 제약 요약.
    점수→자연어 하드코딩 변환 없이 LLM이 판단한다."""
    meta = session.meta or {}
    return {
        "scenario": meta.get("shoppingGoal") or meta.get("category") or "",
        "recentUtterances": [
            t.content for t in recent_turns[-4:] if t.role in ("user", "user_agent")
        ],
        "statedConstraintsNote": constraints_note or "",
        "criteria": _stated_and_confirmed_criteria(db, session.id),
    }


async def run_recommendation(
    db: DbSession,
    provider,
    session: models.Session,
    search_text: str,
    constraints_note: str,
    recent_turns,
    snapshot,
    pool_size: int = 15,
    top_k: int = 3,
) -> tuple[list[ScoredProduct], dict[str, dict]]:
    """검색 사양(searchText/constraintsNote)을 실행해 노출 셋을 확정한다.
    반환: (trade-off 3개, {productId: 카드텍스트}). 상품 선별은 전부 여기서 —
    플래너에는 상품 ID가 흐르지 않는다."""
    pool = search_products(
        db,
        query=search_text,
        category=(session.meta or {}).get("category"),
        hard_constraints=snapshot.hard_constraints if snapshot else [],
        price_min=snapshot.price_min if snapshot else None,
        price_max=snapshot.price_max if snapshot else None,
        return_pool=True,
        pool_size=pool_size,
    )
    intent_context = build_rerank_context(db, session, recent_turns, constraints_note)
    reranked, card_texts = await rg.rerank_by_intent(provider, pool, intent_context)
    # 노출 셋 = rerank 상위 top_k 그대로 (2026-07-02: select_tradeoff_set 제거).
    # 셋의 대비(관측 도구 속성 — 강점이 서로 다른 3개)는 rerank 프롬프트의 구성 원칙으로,
    # mock에서는 결정론 priceCue 스프레드로 처리한다. 옛 버킷 규칙은 아마존 풀에서
    # 88%가 단일 버킷으로 형해화됐고, 희소 버킷을 순위 깊은 곳에서 끌어올려 제약 위반품을
    # 승격시키는 부작용만 남았다(유선 이어폰 누수).
    scored = reranked[:top_k]
    return scored, card_texts
