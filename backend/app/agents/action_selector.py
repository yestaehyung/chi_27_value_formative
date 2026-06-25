"""Next action selection (spec §13.3).

구조적으로 확실한 행동(실제 객체·사건 기반)은 규칙 가드로 정하고,
"추천할까 / 무엇을 더 물을까"라는 퍼지 판단은 action_decision(LLM)에 위임한다.
설계: docs/plans/2026-06-25-action-decision-design.md
"""
from dataclasses import dataclass

from app.db import models


@dataclass
class NextAgentActionDecision:
    action: str
    reason: str


def select_next_action(
    dialogue_acts: list[str],
    direct_conflicts_open: bool,
    has_recommendations: bool = False,
) -> NextAgentActionDecision:
    """구조 가드만 결정한다. 그 외(recommend vs clarify)는 'llm_decide' →
    호출부가 action_decision(LLM)으로 판단한다.

    ※ dialogue_acts는 화행(reveal/inquire/accept/reject/revise)이지 가치가 아니다.
    category(무엇을 사려는지)는 더 이상 행동을 가르지 않는다 — LLM이 대화로 판단."""
    if direct_conflicts_open:
        return NextAgentActionDecision("show_conflict", "open conflict severity is direct")
    if "accept" in dialogue_acts and has_recommendations:
        return NextAgentActionDecision("close", "user accepted a recommendation")
    if "inquire" in dialogue_acts and has_recommendations and "reveal" not in dialogue_acts:
        return NextAgentActionDecision("explain", "user asked for information about shown products")
    return NextAgentActionDecision("llm_decide", "recommend-vs-clarify delegated to action_decision")


# 12 vocab (가치5 + 동기7) — probe dimension 검증용 (defense-in-depth)
def _vocab12() -> set[str]:
    from app.ontology.anchor_mapper import MOTIVATION_DIMS, TRAIT_ANCHORS

    return set(TRAIT_ANCHORS) | set(MOTIVATION_DIMS)


async def fetch_action_decision(provider, context: dict) -> dict:
    """LLM phase (no DB) — '추천 vs 질문(+어느 축 probe)'을 판단.
    출력은 현실과 대조해 정규화: action은 recommend/clarify로, dimension은 12 vocab으로."""
    from app.llm.prompts import SYSTEM_BY_TASK, render_user_context
    from app.llm.provider import LLMMessage

    try:
        out = await provider.generate_json(
            [LLMMessage(role="system", content=SYSTEM_BY_TASK["action_decision"]),
             LLMMessage(role="user", content=render_user_context(context))],
            task="action_decision", context=context,
        )
    except Exception:  # noqa: BLE001
        out = {}
    action = out.get("action")
    if action not in ("recommend", "clarify"):
        action = "recommend"  # 폴백: 애매하면 추천(무한 질문 방지)
    probe = out.get("probe") or {}
    dim = probe.get("dimension")
    if dim not in _vocab12():
        dim = None
    q = probe.get("question")
    return {
        "action": action,
        "reason": out.get("reason") or "",
        "probeDimension": dim,
        "probeQuestion": q.strip() if isinstance(q, str) and q.strip() else None,
    }
