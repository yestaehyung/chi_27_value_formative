"""Selective value/motivation interpretation for clarification decisions.

This module is deliberately separate from M8 motivation measurement.  Its output is stored only
under ``IntentionTopic.hints.theoryBasis`` and may shape one confirmation question; it never
writes ``session.meta.motivationScores`` and never ranks products directly.
"""
from __future__ import annotations

import logging

from app.db import models
from app.llm.prompts import render_user_context, system_for
from app.llm.provider import LLMMessage, LLMProvider
from app.ontology.merge import _similar

logger = logging.getLogger(__name__)

TCV = {"Functional", "Social", "Emotional", "Epistemic", "Conditional"}
MOTIVATIONS = {
    "Adventure", "Gratification", "Role", "BargainValue",
    "SocialShopping", "Idea", "Utilitarian",
}


def candidate_is_activated(candidate: dict | None, *, has_prior_impression: bool) -> bool:
    """The decision layer starts only after products were shown and evidence is substantive."""
    if not has_prior_impression or not isinstance(candidate, dict):
        return False
    if candidate.get("strength") == "strong" and candidate.get("signalType") in {
        "rationale", "context", "evaluation", "repetition",
    }:
        return True
    evidence_ids = {
        str(eid) for eid in (candidate.get("evidenceIds") or []) if str(eid).strip()
    }
    return len(evidence_ids) >= 2


async def fetch_value_interpretation(
    provider: LLMProvider, candidate: dict,
) -> dict:
    context = {"candidate": candidate}
    out = await provider.generate_json(
        [LLMMessage(role="system", content=system_for("criterion_value_interpretation")),
         LLMMessage(role="user", content=render_user_context(context))],
        task="criterion_value_interpretation",
        context=context,
    )
    if not isinstance(out, dict):
        raise ValueError("criterion_value_interpretation returned a non-object")
    values = []
    for row in out.get("values") or []:
        if not isinstance(row, dict) or row.get("anchor") not in TCV:
            continue
        values.append({
            "anchor": row["anchor"],
            "rationale": str(row.get("rationale") or "").strip(),
        })
    return {
        "criterionLabel": str(out.get("criterionLabel") or candidate.get("criterionLabel") or "").strip(),
        "actionableCriterion": str(out.get("actionableCriterion") or "").strip(),
        "values": values[:2],
        "analysisStatus": out.get("analysisStatus")
        if out.get("analysisStatus") in {"ok", "insufficient_evidence"}
        else "insufficient_evidence",
    }


async def fetch_clarification_motivation(
    provider: LLMProvider, candidate: dict,
) -> dict:
    context = {"candidate": candidate}
    out = await provider.generate_json(
        [LLMMessage(role="system", content=system_for("clarification_motivation")),
         LLMMessage(role="user", content=render_user_context(context))],
        task="clarification_motivation",
        context=context,
    )
    if not isinstance(out, dict):
        raise ValueError("clarification_motivation returned a non-object")
    motivation = out.get("motivation")
    if motivation not in MOTIVATIONS:
        motivation = None
    return {
        "criterionLabel": str(out.get("criterionLabel") or candidate.get("criterionLabel") or "").strip(),
        "motivation": motivation,
        "rationale": str(out.get("rationale") or "").strip() or None,
        "questionHint": str(out.get("questionHint") or "").strip() or None,
        "analysisStatus": out.get("analysisStatus")
        if out.get("analysisStatus") in {"ok", "insufficient_evidence"}
        else "insufficient_evidence",
    }


def apply_theory_basis(
    topics: list[models.IntentionTopic],
    candidate: dict,
    value_result: dict | None,
    motivation_result: dict | None,
) -> models.IntentionTopic | None:
    """Attach one auditable decision-layer hypothesis to the matching criterion topic."""
    label = str(candidate.get("criterionLabel") or "").strip()
    topic = next((t for t in topics if _similar(t.label, label)), None)
    if topic is None:
        return None
    failed = []
    if value_result is None:
        failed.append("criterion_value_interpretation")
    if motivation_result is None:
        failed.append("clarification_motivation")
    usable = any(
        isinstance(result, dict) and result.get("analysisStatus") == "ok"
        for result in (value_result, motivation_result)
    )
    status = (
        "failed" if len(failed) == 2
        else "partial" if failed
        else "ok" if usable
        else "insufficient_evidence"
    )
    askable = (
        topic.explicitness != "explicit"
        and topic.status not in {"confirmed", "corrected_by_user", "rejected_by_user", "inactive"}
        and status in {"ok", "partial"}
    )
    hints = dict(topic.hints or {})
    hints["theoryBasis"] = {
        "criterionLabel": label,
        "evidenceIds": list(dict.fromkeys(candidate.get("evidenceIds") or [])),
        "signalType": candidate.get("signalType"),
        "strength": candidate.get("strength"),
        "valueInterpretation": value_result,
        "clarificationMotivation": motivation_result,
        "analysisStatus": status,
        "fallback": "direct_criteria_only" if failed or not usable else None,
        "failedTasks": failed,
        "askable": askable,
        "askScore": 2 if candidate.get("strength") == "strong" else 1,
    }
    topic.hints = hints
    if failed:
        logger.warning(
            "decision-layer analysis degraded — topic=%s failedTasks=%s",
            topic.id, ",".join(failed),
        )
    return topic
