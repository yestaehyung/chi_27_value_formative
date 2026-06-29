"""쇼핑 동기(motivation) 층 — Hedonic 6차원(Arnold & Reynolds 2003) + Utilitarian(Babin).

설문을 직접 묻지 않고, 각 동기 차원의 '잠재 설문 문항'에 해당하는 정보를 대화·피드백에서
수동으로 끌어낸다(detect). 결과는 세션 motivation_scores에 누적된다. 동기는 측정·정렬에만
쓰고 능동 심문은 하지 않는다(recommend-first 피벗) — 능동 probe는 action_decision(LLM)이 결정.
"""

# 각 동기 차원: 설문 문항의 취지 + 발화 신호 키워드
MOTIVATION_SPEC = {
    "Adventure": {
        "survey": "쇼핑하면서 새로운 세계를 탐험하는 기분이 든다",
        "cues": ["새로운", "특이한", "구경", "둘러보", "탐험", "신상", "처음 보는"],
    },
    "Gratification": {
        "survey": "기분 전환이나 나에게 주는 보상으로 쇼핑한다",
        "cues": ["나에게", "나한테", "보상", "기분 전환", "스트레스", "힐링", "위로"],
    },
    "Role": {
        "survey": "다른 사람을 위해 골라주는 데서 즐거움을 느낀다",
        "cues": ["선물", "줄 거", "에게 줄", "친구", "엄마", "아빠", "부모님", "여자친구", "남자친구", "아이"],
    },
    "BargainValue": {
        "survey": "할인·득템에서 즐거움을 느낀다",
        "cues": ["할인", "득템", "싸게", "가성비", "세일", "최저가", "저렴", "쿠폰"],
    },
    "SocialShopping": {
        "survey": "다른 사람과 함께 고르거나 의견을 나누며 쇼핑한다",
        "cues": ["같이", "함께", "친구들이", "다들", "사람들이", "추천받", "물어보"],
    },
    "Idea": {
        "survey": "트렌드나 신제품 정보를 얻으려 쇼핑한다",
        "cues": ["요즘", "유행", "트렌드", "신제품", "최신", "인기", "뭐가 좋아"],
    },
    "Utilitarian": {
        "survey": "필요한 걸 효율적으로 사서 과업을 끝내려 한다",
        "cues": ["필요해", "빨리", "바로", "효율", "끝내", "사야", "급해", "정확히"],
    },
}


def detect_motivation(text: str) -> dict[str, float]:
    """발화에서 동기 신호를 점수화 (cue 매칭 → 0~1, 약한 신호)."""
    scores: dict[str, float] = {}
    for dim, spec in MOTIVATION_SPEC.items():
        hits = sum(1 for c in spec["cues"] if c in text)
        if hits:
            scores[dim] = min(1.0, 0.4 + 0.2 * hits)
    return scores


def merge_motivation(prev: dict, new: dict) -> dict:
    """기존 세션 동기 점수에 새 신호를 noisy-OR로 누적.
    (구 키워드 경로 — LLM motivation_detection 실패 시 폴백 전용, M8)"""
    out = dict(prev or {})
    for dim, s in new.items():
        out[dim] = round(1.0 - (1.0 - out.get(dim, 0.0)) * (1.0 - s), 2)
    return out


def apply_motivation_signals(meta: dict, signals: list[dict]) -> dict:
    """M8 + M4 (llm-measurement-design.md): 설문 rubric LLM이 낸 *발화 단위*
    증거 레벨을 누적하고, 숫자 캐시를 갱신한 meta를 반환한다.

    원본은 meta["motivationEvidence"] = {dim: {best, counts, quotes}} (범주).
    meta["motivationScores"]는 결정 층(probe 선택·snapshot)용 파생 캐시:
      score = LEVEL_VALUE[best]; M4 승격 — suggests 이상 독립 신호 2개면
      asserts 등가(0.8). 폴백(키워드) 턴의 기여는 max로 보존(단조).
    """
    from app.ontology.levels import MOTIVATION_LEVELS, MOTIVATION_LEVEL_VALUE

    rank = {lv: i for i, lv in enumerate(MOTIVATION_LEVELS)}  # asserts=0 (최상위)
    evidence = {k: dict(v) for k, v in (meta.get("motivationEvidence") or {}).items()}
    for s in signals:
        dim, level = s.get("dim"), s.get("level")
        if dim not in MOTIVATION_SPEC or level not in MOTIVATION_LEVEL_VALUE:
            continue
        if not s.get("quote"):
            continue  # 인용 강제 (M1) — 인용 없는 신호는 버린다
        e = evidence.setdefault(dim, {"best": level, "counts": {}, "quotes": []})
        if rank[level] < rank.get(e.get("best", "hints"), 99):
            e["best"] = level
        counts = dict(e.get("counts") or {})
        counts[level] = counts.get(level, 0) + 1
        e["counts"] = counts
        e["quotes"] = (e.get("quotes") or [])[-4:] + [s["quote"]]

    prev_scores = meta.get("motivationScores") or {}
    scores = dict(prev_scores)
    for dim, e in evidence.items():
        val = MOTIVATION_LEVEL_VALUE.get(e.get("best"), 0.0)
        strong = sum(c for lv, c in (e.get("counts") or {}).items()
                     if lv in ("asserts", "suggests"))
        if strong >= 2:  # M4 승격 규칙 (상수 근거: algorithm-audit.md)
            val = max(val, MOTIVATION_LEVEL_VALUE["asserts"])
        scores[dim] = round(max(val, prev_scores.get(dim, 0.0)), 2)

    out = dict(meta)
    out["motivationEvidence"] = evidence
    out["motivationScores"] = scores
    return out


async def fetch_motivation_signals(provider, contents: list[str]) -> list[dict] | None:
    """LLM phase (no DB) — 설문 rubric 기반 동기 신호 감지 (M8).
    발화별로 채점해 신호를 합친다. 전부 실패하면 None (→ 키워드 폴백)."""
    from app.llm.prompts import SYSTEM_BY_TASK, render_user_context
    from app.llm.provider import LLMMessage

    signals: list[dict] = []
    any_ok = False
    for content in contents:
        try:
            out = await provider.generate_json(
                [LLMMessage(role="system", content=SYSTEM_BY_TASK["motivation_detection"]),
                 LLMMessage(role="user", content=render_user_context({"content": content}))],
                task="motivation_detection", context={"content": content},
            )
            signals.extend(s for s in (out.get("signals") or []) if isinstance(s, dict))
            any_ok = True
        except Exception:  # noqa: BLE001
            continue
    return signals if any_ok else None


