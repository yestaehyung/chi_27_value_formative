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

from app.db import models
from app.agents import response_generator as rg
from app.agents.recommendation_policy import (
    RecommendationPolicy,
    build_recommendation_policy,
    uses_unconfirmed,
)
from app.products.search import ScoredProduct, search_products


def _uses_unconfirmed(session: models.Session | None) -> bool:
    """이 세션의 조건이 미확인 추론 기준까지 리랭크에 넣는가 (baseline2만 True)."""
    return uses_unconfirmed(session)


def _stated_and_confirmed_criteria(
    db: DbSession, session_id: str, include_unconfirmed: bool = False
) -> list[dict]:
    """추천이 읽어도 되는 기준: 명시 발화에서 온 토픽(explicit) 또는 사용자가 확인한
    토픽(confirmed/corrected_by_user). 거부·비활성은 제외.

    include_unconfirmed=True(baseline2)면 미확인 추론 토픽도 포함한다 — 위 docstring 참조.

    kind·avoid·mustHave를 함께 넘긴다 (2026-08-14): 추출 설계상 라벨은 극성 없이 '대상'만
    이름 붙이고(예: 회피 기준 "흔한 디자인" — 이중 부정 오문 방지, prompts.py label 작성 규칙)
    극성은 kind가 담는다. label만 넘기면 rerank가 회피 기준을 선호로 뒤집어 읽는다.
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
            hints = t.hints or {}
            crit = {
                "topicId": t.id,
                "label": t.label,
                "description": t.description,
                "kind": hints.get("kind") or "preference",
                "priority": t.priority,
                "status": t.status,
                "explicitness": t.explicitness,
                "source": t.source,
            }
            if hints.get("impliedAvoidance"):
                crit["avoid"] = hints["impliedAvoidance"]
            if hints.get("impliedHardConstraint"):
                crit["mustHave"] = hints["impliedHardConstraint"]
            out.append(crit)
    return out


def select_shown(
    reranked: list[ScoredProduct],
    excluded: dict[str, str],
    top_k: int,
    near_miss_cap: int = 3,
    near_miss_requested: bool = False,
    hard_unk: dict[str, str] | None = None,
) -> tuple[list[ScoredProduct], dict[str, str]]:
    """노출 셋 확정 (2026-08-15 빈손 우선 — ② 부분 정직의 개정).

    rerank 행렬의 위반 판정(excluded)은 LLM의 **출력 사실**이고, 여기서는 그 사실에만
    반응한다: 준수 후보 [:top_k] — top_k 미만이면 그만큼만(위반품으로 채우는 fill-5 금지).
    준수 후보가 0이면 근접 대안 near_miss_cap개를 **기본으로** 사유와 함께 노출한다
    (2026-08-18 파일럿: 빈손 11회 중 사용자가 근접 보기를 요청한 것은 2회 — opt-in은
    막다른 골목이었고, 나머지 9회는 그대로 과제 포기·신뢰 하락으로 이어졌다).
    "다 맞는 상품은 없다"는 부재 고지는 렌더러가 유지한다(near_miss_text).
    cap=3은 표시 상수: 전부 위반인 세트를 5칸 가득 보여주면 고지가 있어도
    정상 추천처럼 읽히기 때문.
    반환: (노출 셋, {productId: 요청과 다른 점}) — 두 번째가 비어 있지 않으면
    노출 전체가 근접 대안이라는 뜻이다."""
    # 준수 = 필수 기준 위반 없음 **그리고** 필수 기준 확인 불가(unk)도 없음 (2026-08-17
    # strict — 확인 불가를 충족으로 간주하지 않는다). vio 사유가 unk 사유보다 우선.
    blocked = {**(hard_unk or {}), **excluded}
    compliant = [sp for sp in reranked if sp.product.id not in blocked]
    if compliant:
        return compliant[:top_k], {}
    if not reranked:
        return [], {}
    shown = reranked[:near_miss_cap]
    return shown, {sp.product.id: blocked.get(sp.product.id, "") for sp in shown}


def unverified_criteria(matrix: dict, shown_ids: list[str]) -> dict[str, int]:
    """노출 셋에서 'unk'(후보 정보로 확인 불가)로 남은 기준별 개수 — 행렬의 사실 집계.

    핵심 기준이 전 후보에서 확인 불가한데 5장을 채워 보여주면(체형 의자 좌판 높이 사례,
    2026-08-15 테스트) 확인된 것처럼 읽힌다. 이 집계를 렌더러에 넘겨 '확인되지 않았다'를
    말하게 한다 — 몇 개부터 언급할지는 렌더러 LLM의 판단."""
    # 셀 의미 계약 (2026-08-23 정합화): FORMAT이 "생략=ok"를 명시하므로 여기서도
    # **명시된 unk만** 센다. 이전 페일세이프(생략=unk 간주, 78a2850)는 이 계약을 몰라
    # 정당한 ok-생략까지 '확인 불가' 고지 대상으로 잡았다 — 진짜 문제(모델이 unk를
    # 생략으로 뭉갬)는 FORMAT의 unk 명시 예시로 잡는다.
    verdicts = matrix.get("verdicts") or {}
    labels = matrix.get("criterionLabels") or {}
    out: dict[str, int] = {}
    for pid in shown_ids:
        for cid, val in (verdicts.get(pid) or {}).items():
            if val == "unk":
                label = labels.get(cid, cid)
                out[label] = out.get(label, 0) + 1
    return out


def _label_words(label: str) -> set[str]:
    """겹침 판정용 내용 단어 (3자 이상, 소문자)."""
    return {w for w in "".join(
        ch if ch.isalnum() else " " for ch in label.lower()).split() if len(w) >= 3}


def merge_near_miss_into_cards(
    card_texts: dict[str, dict],
    near_miss: dict[str, str],
    unk_labels: dict[str, list[str]] | None = None,
) -> None:
    """근접 대안의 '요청과 다른 점'을 해당 카드 weak 맨 앞에 병합 — 고지가 챗 버블만이
    아니라 카드 단위에도 남게 한다(impression으로 영속 → FS1 분석 가능). in-place.

    이중 경고 제거 (2026-08-26 QA): 코드 경고가 이미 명시한 확인 불가 기준을 LLM weak가
    자기 말로 또 쓰면(예: 라벨 'solid wood construction' vs "Material not specified —
    cannot confirm solid wood") 카드마다 같은 말이 2~3줄 반복된다. 코드가 라벨을 아니까
    결정론으로 떨군다 — 라벨 전체 포함 또는 내용 단어 2개 이상 겹침. LLM이 weak를
    아예 빠뜨린 경우엔 코드 경고가 그대로 남아 보증은 유지된다."""
    from app.agents.response_generator import _norm_label

    for pid, reason in near_miss.items():
        if not reason:
            continue
        card = card_texts.get(pid)
        if card is None:
            continue
        labels = (unk_labels or {}).get(pid) or []
        norm_labels = [_norm_label(l) for l in labels]
        word_sets = [_label_words(l) for l in labels]

        def _dupes_code_warning(weak: str) -> bool:
            nw = _norm_label(weak)
            ww = _label_words(weak)
            for nl, ws in zip(norm_labels, word_sets):
                if nl and nl in nw:
                    return True
                if len(ws & ww) >= 2:
                    return True
            return False

        rest = [w for w in card.get("weak") or []
                if w != reason and not _dupes_code_warning(w)]
        card["weak"] = ([reason] + rest)[:3]


def build_rerank_context(
    db: DbSession,
    session: models.Session,
    recent_turns,
    constraints_note: str = "",
    policy: RecommendationPolicy | None = None,
) -> dict:
    """rerank의 Goal. 실행 경로에서는 retrieval과 같은 policy만 읽는다.

    ``constraints_note`` 폴백은 오래된 단위 테스트/직접 호출 호환용이다. 라이브 추천은
    condition-safe ``RecommendationPolicy``를 반드시 전달한다.
    """
    meta = session.meta or {}
    criteria = (
        [dict(c) for c in policy.criteria]
        if policy is not None
        else _stated_and_confirmed_criteria(
            db, session.id, include_unconfirmed=_uses_unconfirmed(session)
        )
    )
    if policy is not None:
        # recommendation_spec이 원문 발화에서 뽑은 명시적 필수조건도 행렬에 독립
        # 기준으로 넣는다. constraintsNote 전체를 hard로 취급하지 않아 일반 선호까지
        # 배제 조건으로 승격되는 것을 막는다.
        #
        # D1 통로 병합 (2026-08-26): 같은 요구가 칩과 스펙 두 통로로 별도 cid를 받아
        # 행렬을 부풀리고 'lightweight, lightweight' 류 중복 표시의 뿌리가 됐다.
        # 정규화 동치 또는 포함 관계(같은 요구의 축약/확장)면 기존 칩 항목에 합치되,
        # 스펙이 필수로 본 요구이므로 집행은 강한 쪽(hard)으로 승격한다.
        # 의미 유사도 매칭은 쓰지 않는다 — 다른 기준을 오병합하면 배제가 실집행이라
        # 위험이 표시 중복보다 크다.
        from app.agents.response_generator import _norm_label

        def _same_requirement(a: str, b: str) -> bool:
            na, nb = _norm_label(a), _norm_label(b)
            if not na or not nb:
                return False
            if na == nb:
                return True
            return len(min(na, nb, key=len)) >= 4 and (na in nb or nb in na)

        for hard in policy.hard_constraints:
            existing = next(
                (c for c in criteria if _same_requirement(c.get("label") or "", hard)), None)
            if existing is not None:
                existing["enforcement"] = "hard"
                continue
            criteria.append({
                "label": hard,
                "kind": "constraint",
                "priority": "must_have",
                "enforcement": "hard",
                "source": "direct_recommendation_spec",
            })
        # 가격도 칩에 구조 필드(priceMin/priceMax)가 이미 있으면 별도 항목을 안 만든다
        has_price_criterion = any(
            c.get("priceMin") is not None or c.get("priceMax") is not None for c in criteria)
        if not has_price_criterion and (policy.price_min is not None or policy.price_max is not None):
            if policy.price_min is not None and policy.price_max is not None:
                price_label = f"price {policy.price_min}–{policy.price_max}"
            elif policy.price_max is not None:
                price_label = f"price at or below {policy.price_max}"
            else:
                price_label = f"price at or above {policy.price_min}"
            criteria.append({
                "label": price_label,
                "kind": "constraint",
                "priority": "must_have",
                "enforcement": "hard",
                "source": "direct_recommendation_spec",
            })
    return {
        "scenario": meta.get("shoppingGoal") or meta.get("category") or "",
        "recentUtterances": [
            t.content for t in recent_turns if t.role in ("user", "user_agent")
        ],
        "statedConstraintsNote": (
            policy.constraints_note if policy is not None else constraints_note or ""
        ),
        "criteria": criteria,
    }


def _previously_shown(db: DbSession, session: models.Session, cap: int = 10) -> list[models.Product]:
    """이번 세션에서 노출된 상품(최신 우선, 중복 제거, 세션 카테고리 한정)."""
    rows = (
        db.query(models.ProductImpression)
        .filter(models.ProductImpression.session_id == session.id)
        .order_by(models.ProductImpression.created_at.desc())
        .all()
    )
    category = (session.meta or {}).get("category")
    out: list[models.Product] = []
    seen: set[str] = set()
    for r in rows:
        if r.product_id in seen:
            continue
        seen.add(r.product_id)
        p = db.get(models.Product, r.product_id)
        if p is None or (category and p.category != category):
            continue
        out.append(p)
        if len(out) >= cap:
            break
    return out


async def run_basic_recommendation(
    db: DbSession,
    provider,
    session: models.Session,
    recent_turns,
    top_k: int = 5,
) -> tuple[list[ScoredProduct], dict[str, dict], dict]:
    """baseline1 전용 (2026-08-21 '완전 basic' 조정): 검색엔진 수준의 추천.

    유지 — 현재 발화의 LLM 검색어 재작성(스펙 컴파일, current-request-only)과
    search_products의 결정론 레이어(가격/카테고리 필터, 뮤텍스 태그) — "무선 달라는데
    유선"류의 티 나는 실패를 막는 바보 방지선.
    제거 — LLM 판정행렬 리랭크(소프트 기준 적합도·보완적 구성·기준별 확인불가 고지·
    후보 영속성): 관련도순 top_k를 그대로 보여준다. 카드 사유 텍스트도 없다.
    반환 형태는 run_recommendation과 동일 (진단 dict에 bucket="basic" 표기)."""
    policy = await build_recommendation_policy(db, provider, session)
    pool = search_products(
        db,
        query=policy.search_text,
        category=(session.meta or {}).get("category"),
        hard_constraints=list(policy.hard_constraints),
        price_min=policy.price_min,
        price_max=policy.price_max,
        return_pool=True,
        pool_size=top_k * 3,
    )
    shown = pool[:top_k]
    # 상품 일반 장단점 (2026-08-26 조작 정의 변경, 사용자 승인): 오프라인 프로필의
    # keyAttributes 2개 + caveats 1개를 결정론 표시한다. 누가 검색해도 같은 상품이면
    # 같은 문구 — "사용자 모델 없음"은 유지하면서, 조건 간 대비를 "설명 유무"가 아니라
    # "일반 정보 vs 내 기준에 비춘 판정"으로 좁힌다. LLM 호출 없음(지연 +0).
    from app.products import profiles

    card_texts: dict[str, dict] = {}
    for sp in shown:
        prof = profiles.get(sp.product.id) or {}
        matched = [str(a) for a in (prof.get("keyAttributes") or [])[:2] if str(a).strip()]
        weak = [str(cv) for cv in (prof.get("caveats") or [])[:1] if str(cv).strip()]
        if matched or weak:
            card_texts[sp.product.id] = {"reason": "", "matched": matched, "weak": weak}
    diag = {
        "bucket": "basic",
        "searchText": policy.search_text,
        "recommendationPolicy": policy.as_dict(),
        "poolSize": len(pool),
        "shownIds": [sp.product.id for sp in shown],
    }
    return shown, card_texts, diag


async def run_recommendation(
    db: DbSession,
    provider,
    session: models.Session,
    recent_turns,
    pool_size: int = 30,   # 15→30 (2026-07-06): 카탈로그 600→10,780 확대에 맞춘 recall 확장
    top_k: int = 5,
) -> tuple[list[ScoredProduct], dict[str, dict], dict]:
    """격리된 evidence policy를 만들어 검색과 rerank에 함께 적용한다.

    planner는 확인 질문을 위해 미확인 가설을 볼 수 있으므로 planner의 searchText,
    constraintsNote, 전체 snapshot은 이 함수가 아예 받지 않는다. raw participant evidence +
    condition-eligible topics만으로 사양을 만든다.

    반환: (trade-off top_k개, {productId: 카드텍스트}, 진단 dict). 상품 선별은 전부
    여기서 — 플래너에는 상품 ID가 흐르지 않는다. 진단 dict는 llm_calls 기록용:
    검색 풀 전체를 남겨 "정답이 풀에 없었나 vs rerank가 버렸나"를 사후 구분한다."""
    policy = await build_recommendation_policy(db, provider, session)
    pool = search_products(
        db,
        query=policy.search_text,
        category=(session.meta or {}).get("category"),
        hard_constraints=list(policy.hard_constraints),
        price_min=policy.price_min,
        price_max=policy.price_max,
        return_pool=True,
        pool_size=pool_size,
    )
    # 후보 영속성 (2026-08-18): 이번 세션에서 이미 보여준 상품은 검색어가 바뀌어도
    # 풀에 남아 매 턴 행렬로 재평가된다 — 새 조건(색상 등)이 추가되면 검색 풀이 갈려
    # "이미 보여준 $19.98 후보"가 사라지고 "조건에 맞는 게 없다"로 이어지던 문제
    # (라이브 실측 2회: 바지·티셔츠). 판정은 여전히 행렬이 한다(부활 보장이 아니라
    # 재평가 보장).
    pool_ids = {sp.product.id for sp in pool}
    for p in _previously_shown(db, session, cap=10):
        if p.id not in pool_ids:
            pool.append(ScoredProduct(product=p, score=0.0, bucket="prev_shown"))
            pool_ids.add(p.id)
    intent_context = build_rerank_context(db, session, recent_turns, policy=policy)
    reranked, card_texts, excluded, matrix = await rg.rerank_by_intent(provider, pool, intent_context)
    # 판정 실패(행렬 부재 — 출력 잘림·형식 붕괴) + 필수 기준 존재 = 무필터 노출 금지.
    # 검증 안 된 상품을 정상 카드처럼 내보내면 "정확히 27인치" 세션에 24인치가 나간다
    # (2026-08-18 라이브 실측). 정직하게 재시도를 청한다 (fail-loud).
    if matrix.get("failed"):
        hard_present = any(
            c.get("enforcement") == "hard"
            for c in (intent_context.get("criteria") or []))
        if hard_present:
            diag = {
                "searchText": policy.search_text,
                "constraintsNote": policy.constraints_note,
                "recommendationPolicy": policy.as_dict(),
                "poolIds": [sp.product.id for sp in pool],
                "rerankFailed": True, "matrix": matrix,
            }
            return [], {}, diag
    # 노출 셋 = 준수 후보 상위 top_k, 전멸 시 근접 대안(② 부분 정직 — select_shown).
    # 셋의 대비(관측 도구 속성 — 강점이 서로 다른 후보들)는 rerank 프롬프트의 구성 원칙으로,
    # mock에서는 결정론 priceCue 스프레드로 처리한다(mock은 exclude를 내지 않으므로
    # 기존 데모 경로 그대로). 옛 버킷 규칙은 아마존 풀에서 88%가 단일 버킷으로 형해화됐고,
    # 희소 버킷을 순위 깊은 곳에서 끌어올려 제약 위반품을 승격시키는 부작용만 남았다.
    scored, near_miss = select_shown(
        reranked, excluded, top_k,
        near_miss_requested=matrix.get("nearMissRequested", False),
        hard_unk=matrix.get("hardUnk"),
    )
    merge_near_miss_into_cards(card_texts, near_miss, matrix.get("hardUnkLabels"))
    # 빈손 = 후보는 있었는데 행렬상 전부 위반/확인불가 & 근접 표시 미요청 (풀이 빈 것과 구분)
    killer = [k for k, _ in sorted(
        (matrix.get("vioCounts") or {}).items(), key=lambda kv: -kv[1])]
    # 위반이 아니라 "전 후보 확인 불가"로 전멸한 필수 기준도 빈손 사유에 올린다
    from app.core.locale import L
    killer += [L(f"{k} (확인 불가)", f"{k} (not confirmed in listings)")
               for k, _ in sorted((matrix.get("hardUnkCounts") or {}).items(), key=lambda kv: -kv[1])
               if k not in (matrix.get("vioCounts") or {})]
    diag = {
        "searchText": policy.search_text,
        "constraintsNote": policy.constraints_note,
        "recommendationPolicy": policy.as_dict(),
        "poolSize": len(pool),
        "pool": [{"id": sp.product.id, "category": sp.product.category,
                  "title": (sp.product.title or "")[:60], "score": round(sp.score, 4)}
                 for sp in pool],
        "rerankContext": intent_context,
        "excludedIds": {pid: reason for pid, reason in excluded.items()},
        "nearMiss": near_miss,
        "shownIds": [sp.product.id for sp in scored],
        "matrix": {"vioCounts": matrix.get("vioCounts") or {},
                   "nearMissRequested": matrix.get("nearMissRequested", False),
                   "verdicts": matrix.get("verdicts") or {}},
        "matrixKiller": killer[:2],
        "emptyHanded": bool(pool) and not scored,
        "unverifiedCriteria": unverified_criteria(
            matrix, [sp.product.id for sp in scored]),
    }
    return scored, card_texts, diag
