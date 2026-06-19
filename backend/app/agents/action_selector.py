"""Next action selection rules (spec §13.3)."""
from dataclasses import dataclass

from app.db import models


@dataclass
class NextAgentActionDecision:
    action: str
    reason: str


def select_next_action(
    session: models.Session,
    user_intents: list[str],
    direct_conflicts_open: bool,
    category: str | None,
    has_recommendations: bool = False,
) -> NextAgentActionDecision:
    if category is None:
        return NextAgentActionDecision("clarify", "product category unknown")
    if direct_conflicts_open:
        return NextAgentActionDecision("show_conflict", "open conflict severity is direct")
    if "accept" in user_intents and has_recommendations:
        return NextAgentActionDecision("close", "user accepted a recommendation")
    if "inquire" in user_intents and has_recommendations and "reveal" not in user_intents:
        return NextAgentActionDecision("explain", "user asked for information about shown products")
    return NextAgentActionDecision("recommend", "enough constraints exist to recommend")
