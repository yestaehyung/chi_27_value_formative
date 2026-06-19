"""Chosen-rejected pair construction (spec §10, §11 Phase A).

Pairs are built inside one recommendation turn:
  like vs dislike / purchase vs ignored / detail_view vs skipped / chosen vs rejected.

Concurrency design: pair candidates are collected from reads, hidden-reason LLM
calls run in parallel with no write locks held, then all rows are written at once.
"""
import asyncio
from dataclasses import dataclass

from sqlalchemy.orm import Session as DbSession

from app.core.ids import new_id
from app.db import models
from app.llm.provider import LLMProvider
from app.wimhf.diff_builder import build_product_diff

POSITIVE = {"like", "purchase", "add_to_cart"}
NEGATIVE = {"dislike", "reject"}


@dataclass
class PairSpec:
    chosen_id: str
    rejected_id: str
    label_source: str
    reason_text: str | None
    diff: dict


def _prompt_context(db: DbSession, session: models.Session) -> str:
    first_user = (
        db.query(models.Turn)
        .filter(models.Turn.session_id == session.id)
        .filter(models.Turn.role.in_(["user", "user_agent"]))
        .order_by(models.Turn.turn_index)
        .first()
    )
    return first_user.content if first_user else (session.meta or {}).get("surfaceIntent", {}).get("explicitQuery", "")


async def build_pairs_for_feedback(
    db: DbSession,
    provider: LLMProvider,
    session: models.Session,
    fb: models.FeedbackEvent,
) -> list[models.ChosenRejectedPair]:
    if fb.turn_id is None:
        return []

    # ── read phase ──────────────────────────────────────────────
    turn_feedback = (
        db.query(models.FeedbackEvent)
        .filter(models.FeedbackEvent.session_id == session.id)
        .filter(models.FeedbackEvent.turn_id == fb.turn_id)
        .all()
    )
    impressions = (
        db.query(models.ProductImpression)
        .filter(models.ProductImpression.turn_id == fb.turn_id)
        .all()
    )
    shown_ids = {i.product_id for i in impressions}
    touched_ids = {f.product_id for f in turn_feedback}
    existing = {
        (p.chosen_id, p.rejected_id, p.label_source)
        for p in db.query(models.ChosenRejectedPair)
        .filter(models.ChosenRejectedPair.session_id == session.id)
        .all()
    }
    products = {p.id: p for p in db.query(models.Product).filter(models.Product.id.in_(shown_ids)).all()}

    candidates: list[tuple[str, str, str, str | None]] = []
    if fb.type in NEGATIVE:
        for other in turn_feedback:
            if other.product_id != fb.product_id and other.type in POSITIVE:
                candidates.append((other.product_id, fb.product_id,
                                   "purchase" if other.type == "purchase" else "like_vs_dislike",
                                   fb.reason_text))
    elif fb.type in POSITIVE:
        for other in turn_feedback:
            if other.product_id != fb.product_id and other.type in NEGATIVE:
                candidates.append((fb.product_id, other.product_id,
                                   "purchase" if fb.type == "purchase" else "like_vs_dislike",
                                   other.reason_text))
        if fb.type == "purchase":
            for pid in shown_ids - touched_ids:  # purchase vs ignored
                candidates.append((fb.product_id, pid, "purchase", None))
    elif fb.type == "view_detail":
        for pid in shown_ids - touched_ids:
            candidates.append((fb.product_id, pid, "detail_view_vs_skip", None))

    specs: list[PairSpec] = []
    for chosen_id, rejected_id, label, reason in candidates:
        if session.mode == "simulation" and label == "click_vs_ignore":
            label = "simulated_user_agent"
        if (chosen_id, rejected_id, label) in existing:
            continue
        chosen, rejected = products.get(chosen_id), products.get(rejected_id)
        if chosen is None or rejected is None:
            continue
        specs.append(PairSpec(chosen_id, rejected_id, label, reason,
                              build_product_diff(chosen, rejected)))

    if not specs:
        return []

    # ── LLM phase (no write locks held) ─────────────────────────
    async def infer_reason(spec: PairSpec) -> str | None:
        try:
            out = await provider.generate_json(
                [], task="pair_hidden_reason",
                context={"diff": spec.diff, "userReasonText": spec.reason_text},
            )
            return out.get("inferredHiddenReason")
        except Exception:  # noqa: BLE001
            return None

    reasons = await asyncio.gather(*(infer_reason(s) for s in specs))

    # ── write phase (one short transaction) ─────────────────────
    prompt_context = _prompt_context(db, session)
    pairs: list[models.ChosenRejectedPair] = []
    for spec, reason in zip(specs, reasons):
        pair = models.ChosenRejectedPair(
            id=new_id("pair"),
            session_id=session.id,
            prompt_context=prompt_context,
            chosen_type="product",
            rejected_type="product",
            chosen_id=spec.chosen_id,
            rejected_id=spec.rejected_id,
            label_source=spec.label_source,
            user_reason_text=spec.reason_text,
            product_diff=spec.diff,
            inferred_hidden_reason=reason,
        )
        db.add(pair)
        pairs.append(pair)
    db.commit()
    return pairs
