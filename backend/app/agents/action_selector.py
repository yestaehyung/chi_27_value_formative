"""Next action selection rules (spec §13.3)."""
from dataclasses import dataclass

from app.db import models


@dataclass
class NextAgentActionDecision:
    action: str
    reason: str


def select_next_action(
    session: models.Session,
    dialogue_acts: list[str],
    direct_conflicts_open: bool,
    category: str | None,
    has_recommendations: bool = False,
) -> NextAgentActionDecision:
    """다음 행동 결정 — 사용자 발화의 화행(dialogue_acts: reveal/inquire/accept/reject/revise…)과
    상태를 보고 정한다. ※ dialogue_acts는 화행(말로 뭘 하나)이지 가치(IntentionTopic)가 아니다."""
    if category is None:
        return NextAgentActionDecision("clarify", "product category unknown")
    if direct_conflicts_open:
        return NextAgentActionDecision("show_conflict", "open conflict severity is direct")
    if "accept" in dialogue_acts and has_recommendations:
        return NextAgentActionDecision("close", "user accepted a recommendation")
    # 거절: 추천을 봤는데 거절했고 새 요구(reveal)는 없음 → 같은 걸 또 주지 말고
    # 기준을 다시 끌어낸다(clarify). reveal이 같이 있으면 새 기준이 있으니 recommend로.
    if "reject" in dialogue_acts and has_recommendations and "reveal" not in dialogue_acts:
        return NextAgentActionDecision("clarify", "user rejected recommendations without new criteria — re-elicit")
    if "inquire" in dialogue_acts and has_recommendations and "reveal" not in dialogue_acts:
        return NextAgentActionDecision("explain", "user asked for information about shown products")
    # 수정(revise): 새 기준으로 다시 추천 (recommend). reveal과 같은 경로지만 의미 기록용으로 분리.
    if "revise" in dialogue_acts:
        return NextAgentActionDecision("recommend", "user revised criteria — re-recommend with updated state")
    return NextAgentActionDecision("recommend", "enough constraints exist to recommend")
