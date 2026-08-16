"""User-visible summary builder (spec §30, §36).

Internal ontology terms (Social, Emotional, confidence…) are translated into
context-limited, correctable phrasing — never definitive statements about the user.
"""
from app.core.locale import L
from app.db import models

CHIP_TYPE_BY_PRIORITY = {"must_have": "must_have", "high": "important", "medium": "nice_to_have", "low": "nice_to_have"}


def topic_to_chip_type(topic: models.IntentionTopic) -> str:
    if topic.status == "candidate":
        return "uncertain"
    if (topic.hints or {}).get("kind") == "avoidance":
        return "avoid"
    return CHIP_TYPE_BY_PRIORITY.get(topic.priority, "nice_to_have")


def short_rationale(topic: models.IntentionTopic) -> str:
    ev = (topic.hints or {}).get("evidence") or []
    if ev:
        return ev[0].get("quoteOrSummary", "")[:80]
    return topic.description or ""


def build_user_visible_summary(
    ordered_topics: list[models.IntentionTopic],
    has_open_conflict: bool,
    max_count: int = 5,
    llm_sentence: str | None = None,
) -> dict:
    top = ordered_topics[:max_count]
    chips = [
        {
            "id": t.id,
            "label": t.label,
            "type": topic_to_chip_type(t),
            "userEditable": True,
            "evidenceCount": len(t.evidence_ids or []),
            "displayRationale": short_rationale(t),
            "status": t.status,
            "priority": t.priority,
            "confidence": round(t.confidence, 2),
        }
        for t in top
    ]

    # 요약은 추론을 *반영*만 한다 — 도메인 가정을 캔 문장으로 *재주장*하지 않는다.
    # (옛 "선물→운동 기능·장기 사용 신뢰" 하드코딩 제거: 스마트워치 가정이라 다른
    #  도메인(이어폰/의류)에 오작동했고, 기준이 바뀌어도 문장이 고정됐다.)
    # 칩 라벨에서 동적으로 합성 — B1(결정론). 추후 LLM trade-off 요약의 폴백/계약이 된다.
    labels = [t.label for t in top]

    # LLM이 칩 사이의 암묵적 trade-off를 합성한 문장(state_summary task)을 우선 사용.
    # 없거나(미생성) 실패 시 → B1(라벨조합) 결정론 폴백. (둘 다 §36 hedged 계약.)
    if llm_sentence and llm_sentence.strip():
        sentence = llm_sentence.strip()
    elif labels:
        head = ", ".join(labels[:3])
        sentence = L(f"지금은 '{head}' 기준을 중요하게 보고 있다고 이해했어요. 맞는지 확인해 주세요.",
                     f"It seems you're currently prioritizing '{head}'. Please confirm whether that's right.")
    else:
        sentence = L("아직 기준을 파악하는 중이에요. 원하시는 조건을 자유롭게 말씀해 주세요.",
                     "I'm still learning your criteria — feel free to tell me what matters to you.")

    needs_confirmation = has_open_conflict or any(t.status in ("candidate", "inferred") for t in top)
    return {"chips": chips, "oneSentenceSummary": sentence, "needsConfirmation": needs_confirmation}


async def fetch_state_summary(
    provider,
    criteria: list[dict],
    scenario: str | None = None,
    recent_utterances: list[str] | None = None,
) -> str | None:
    """LLM phase (no DB) — 기준들을 hedged 한 문장으로 요약. 우선순위/trade-off 비교는
    근거(발화 속 직접 비교, 사용자 확인·수정 상태)가 입력에 있을 때만 쓰도록 프롬프트가
    제한한다 — 라벨만 주면 모든 비교가 날조가 된다(2026-08-16 실측).
    criteria: [{label, priority, status}]. 빈 입력·실패 시 None (→ 폴백)."""
    criteria = [c for c in (criteria or []) if c.get("label")][:5]
    labels = [c["label"] for c in criteria]
    if not labels:
        return None
    from app.llm.prompts import render_user_context, system_for
    from app.llm.provider import LLMMessage

    ctx = {
        "labels": labels,  # mock 핸들러(B1 폴백 형태)가 읽는 키 — 유지
        "criteria": criteria,
        "recentUtterances": [u[:200] for u in (recent_utterances or [])[-3:]],
        "scenario": scenario or "",
    }
    try:
        out = await provider.generate_json(
            [LLMMessage(role="system", content=system_for("state_summary")),
             LLMMessage(role="user", content=render_user_context(ctx))],
            task="state_summary", context=ctx,
        )
        s = (out or {}).get("summary")
        return s.strip() if isinstance(s, str) and s.strip() else None
    except Exception:  # noqa: BLE001
        return None
