"""③ 추천 에이전트 — recommend(searchText, constraintsNote)의 실행
(설계: docs/plans/2026-07-02-three-agent-crs-redesign.md).

[임베딩 검색: 도구] → LLM rerank(제약·기준 집행) → trade-off 5개 (2026-07-04: 3→5).

evidence-purity 규칙: rerank가 읽는 것은 **stated(명시 발화) + confirmed(사용자
확인 기준)뿐** — 미확인 배후 추론(anchor/motivation 원점수)은 랭킹에 넣지 않는다.
(1) 미확인 추론이 추천에 들어가면 피드백 증거가 오염되고, (2) 칩 수정→confirmed→
다음 추천 반영이라는 ours 조건의 인과 경로가 이 필터로 구조적으로 보장된다.
이론층(가치·동기)이 추천에 닿는 유일한 경로는 플래너의 가설 확인 질문을 거쳐
confirmed가 되는 것(가설 경로).

**baseline2는 이 규칙의 의도된 예외다.** 그 조건에는 확인 UI 자체가 없어서 추론 기준이
confirmed로 갈 길이 없다 — 규칙을 그대로 적용하면 "추론은 하되 추천엔 못 쓰는" 상태가 되어
baseline1과 구분이 사라진다. baseline2의 정의가 "추론한 기준을 사용자 확인 없이 그대로
쓴다"이므로, 그 조건에서만 미확인 추론 토픽도 통과시킨다(`USES_UNCONFIRMED_INFERENCE`).
"""
from sqlalchemy.orm import Session as DbSession

from app.core.conditions import USES_UNCONFIRMED_INFERENCE, normalize_condition
from app.db import models
from app.agents import response_generator as rg
from app.products.search import ScoredProduct, search_products


def _uses_unconfirmed(session: models.Session | None) -> bool:
    """이 세션의 조건이 미확인 추론 기준까지 리랭크에 넣는가 (baseline2만 True)."""
    slug = normalize_condition((session.meta or {}).get("studyCondition")) if session else None
    return USES_UNCONFIRMED_INFERENCE.get(slug, False) if slug else False


def _stated_and_confirmed_criteria(
    db: DbSession, session_id: str, include_unconfirmed: bool = False
) -> list[dict]:
    """추천이 읽어도 되는 기준: 명시 발화에서 온 토픽(explicit) 또는 사용자가 확인한
    토픽(confirmed/corrected_by_user). 거부·비활성은 제외.

    include_unconfirmed=True(baseline2)면 미확인 추론 토픽도 포함한다 — 위 docstring 참조.
    """
    topics = (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id == session_id)
        .filter(models.IntentionTopic.status.notin_(("rejected_by_user", "inactive")))
        .all()
    )
    out = []
    for t in topics:
        if (include_unconfirmed
                or t.explicitness == "explicit"
                or t.status in ("confirmed", "corrected_by_user")):
            out.append({"label": t.label, "description": t.description})
    return out


def select_shown(
    reranked: list[ScoredProduct],
    excluded: dict[str, str],
    top_k: int,
    near_miss_cap: int = 3,
) -> tuple[list[ScoredProduct], dict[str, str]]:
    """노출 셋 확정 (② 부분 정직, 2026-07-07 — 버뮤다 진단 후속).

    rerank의 exclude는 LLM의 판단 **출력 사실**이고, 여기서는 그 사실에만 반응한다:
    준수 후보 [:top_k] — top_k 미만이면 그만큼만(위반품으로 채우는 fill-5 금지).
    준수 후보가 0이면 근접 대안(rerank 순위 상위 = 요청과 가장 가까운 순)
    near_miss_cap개를 이유와 함께 노출한다 — "없다"는 사실을 숨기지도(fill-5),
    빈손으로 끝내지도(완전 공백) 않는 중간 경로. cap=3은 표시 상수: 전부 위반인
    세트를 5칸 가득 보여주면 고지가 있어도 정상 추천처럼 읽히기 때문.
    반환: (노출 셋, {productId: 요청과 다른 점}) — 두 번째가 비어 있지 않으면
    노출 전체가 근접 대안이라는 뜻이다."""
    compliant = [sp for sp in reranked if sp.product.id not in excluded]
    if compliant:
        return compliant[:top_k], {}
    shown = reranked[:near_miss_cap]
    return shown, {sp.product.id: excluded.get(sp.product.id, "") for sp in shown}


def merge_near_miss_into_cards(card_texts: dict[str, dict], near_miss: dict[str, str]) -> None:
    """근접 대안의 '요청과 다른 점'을 해당 카드 weak 맨 앞에 병합 — 고지가 챗 버블만이
    아니라 카드 단위에도 남게 한다(impression으로 영속 → FS1 분석 가능). in-place."""
    for pid, reason in near_miss.items():
        if not reason:
            continue
        card = card_texts.get(pid)
        if card is None:
            continue
        rest = [w for w in card.get("weak") or [] if w != reason]
        card["weak"] = ([reason] + rest)[:3]


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
        "criteria": _stated_and_confirmed_criteria(
            db, session.id, include_unconfirmed=_uses_unconfirmed(session)
        ),
    }


async def run_recommendation(
    db: DbSession,
    provider,
    session: models.Session,
    search_text: str,
    constraints_note: str,
    recent_turns,
    snapshot,
    pool_size: int = 30,   # 15→30 (2026-07-06): 카탈로그 600→10,780 확대에 맞춘 recall 확장
    top_k: int = 5,
) -> tuple[list[ScoredProduct], dict[str, dict], dict]:
    """검색 사양(searchText/constraintsNote)을 실행해 노출 셋을 확정한다.
    반환: (trade-off top_k개, {productId: 카드텍스트}, 진단 dict). 상품 선별은 전부
    여기서 — 플래너에는 상품 ID가 흐르지 않는다. 진단 dict는 llm_calls 기록용:
    검색 풀 전체를 남겨 "정답이 풀에 없었나 vs rerank가 버렸나"를 사후 구분한다."""
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
    reranked, card_texts, excluded = await rg.rerank_by_intent(provider, pool, intent_context)
    # 노출 셋 = 준수 후보 상위 top_k, 전멸 시 근접 대안(② 부분 정직 — select_shown).
    # 셋의 대비(관측 도구 속성 — 강점이 서로 다른 후보들)는 rerank 프롬프트의 구성 원칙으로,
    # mock에서는 결정론 priceCue 스프레드로 처리한다(mock은 exclude를 내지 않으므로
    # 기존 데모 경로 그대로). 옛 버킷 규칙은 아마존 풀에서 88%가 단일 버킷으로 형해화됐고,
    # 희소 버킷을 순위 깊은 곳에서 끌어올려 제약 위반품을 승격시키는 부작용만 남았다.
    scored, near_miss = select_shown(reranked, excluded, top_k)
    merge_near_miss_into_cards(card_texts, near_miss)
    diag = {
        "searchText": search_text,
        "constraintsNote": constraints_note,
        "poolSize": len(pool),
        "pool": [{"id": sp.product.id, "category": sp.product.category,
                  "title": (sp.product.title or "")[:60], "score": round(sp.score, 4)}
                 for sp in pool],
        "rerankContext": intent_context,
        "excludedIds": {pid: reason for pid, reason in excluded.items()},
        "nearMiss": near_miss,
        "shownIds": [sp.product.id for sp in scored],
    }
    return scored, card_texts, diag
