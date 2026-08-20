"""Stage 1 — Intention Topic Extraction (spec §15.1).

The legacy ``extract_topics`` list contract remains public.  The commit engine uses the
extended update contract so question signals and one interpretation candidate can travel beside
the established topic schema without replacing it.
"""
from sqlalchemy.orm import Session as DbSession

from app.core.locale import product_display_title
from app.db import models
from app.llm.prompts import render_user_context, system_for
from app.llm.provider import LLMMessage, LLMProvider


def _feedback_context(db: DbSession, fb: models.FeedbackEvent) -> dict:
    product = db.get(models.Product, fb.product_id)
    return {
        "id": fb.id,
        "type": fb.type,
        "valence": fb.valence,
        "reasonCode": fb.reason_code,
        "reasonText": fb.reason_text,
        "productId": fb.product_id,
        "productTitle": product_display_title(product),
        "productCues": (product.cue_summary or {}) if product else {},
        "price": product.price if product else None,
        "longTermReviewRatio": product.long_term_review_ratio if product else None,
    }


async def extract_topics(
    db: DbSession,
    provider: LLMProvider,
    session: models.Session,
    turn_ids: list[str],
    feedback_ids: list[str],
    current_state: dict | None,
) -> list[dict]:
    update = await extract_topic_update(
        db, provider, session, turn_ids, feedback_ids, current_state,
    )
    return update["topics"]


def _valid_question_signals(value, valid_ids: set[str]) -> list[dict]:
    out: list[dict] = []
    for row in value if isinstance(value, list) else []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("candidateLabel") or "").strip()
        evidence_id = str(row.get("evidenceId") or "").strip()
        quote = str(row.get("quote") or "").strip()
        if label and evidence_id in valid_ids and quote:
            out.append({
                "candidateLabel": label,
                "evidenceId": evidence_id,
                "quote": quote,
            })
    return out[:4]


def _attach_prior_question_evidence(topics: list[dict], candidates: list[dict]) -> None:
    """Promote a prior question only when a later extracted criterion reuses its label.

    The question edge stays implicit; the later declarative evidence determines whether the topic
    itself becomes explicit.  A question by itself never becomes a recommendation criterion.
    """
    by_label: dict[str, list[dict]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict) or not candidate.get("candidateLabel"):
            continue
        key = str(candidate["candidateLabel"]).strip().casefold()
        by_label.setdefault(key, []).append(candidate)
    for topic in topics:
        if not isinstance(topic, dict):
            continue
        matched = by_label.get(str(topic.get("label") or "").strip().casefold()) or []
        if not matched:
            continue
        source = topic.setdefault("sourceEvidence", [])
        for candidate in matched:
            evidence_id = candidate.get("evidenceId")
            if not evidence_id:
                continue
            if any(e.get("id") == evidence_id for e in source if isinstance(e, dict)):
                continue
            source.append({
                "type": "turn",
                "id": evidence_id,
                "quoteOrSummary": candidate.get("quote") or candidate.get("candidateLabel"),
                "explicitness": "implicit",
                "channel": "question_signal",
            })


async def extract_topic_update(
    db: DbSession,
    provider: LLMProvider,
    session: models.Session,
    turn_ids: list[str],
    feedback_ids: list[str],
    current_state: dict | None,
) -> dict:
    turns = [db.get(models.Turn, tid) for tid in turn_ids]
    feedback = [db.get(models.FeedbackEvent, fid) for fid in feedback_ids]
    context = {
        "turns": [
            {"id": t.id, "role": t.role, "content": t.content}
            for t in turns if t is not None
        ],
        "feedback": [_feedback_context(db, f) for f in feedback if f is not None],
        "state": {
            "activeTopicLabels": (current_state or {}).get("activeTopicLabels", []),
            "userAuthoredLabels": (current_state or {}).get("userAuthoredLabels", []),
            "candidateLabels": [
                c.get("candidateLabel")
                for c in (current_state or {}).get("criterionQuestionCandidates", [])
                if isinstance(c, dict) and c.get("candidateLabel")
            ],
        },
    }
    messages = [
        LLMMessage(role="system", content=system_for("topic_extraction")),
        LLMMessage(role="user", content=render_user_context(context)),
    ]
    # 추출은 집행층과 같은 최대 결정론(temp 0.0) — qwen3.8에서 temp 0.1 샘플링이
    # 같은 발화에 대해 간헐적으로 빈 topics를 내는 것을 실측 (2026-08-20, 3회 중 1회).
    # 빈 추출은 침묵 강등처럼 사용자 모델에 구멍을 내므로 그리디로 고정한다.
    out = await provider.generate_json(messages, task="topic_extraction", context=context,
                                       temperature=0.0)
    topics = [t for t in (out.get("topics") or []) if isinstance(t, dict)]
    prior_candidates = [
        c for c in (current_state or {}).get("criterionQuestionCandidates", [])
        if isinstance(c, dict)
    ]
    _attach_prior_question_evidence(topics, prior_candidates)
    valid_ids = {
        *(t.id for t in turns if t is not None),
        *(f.id for f in feedback if f is not None),
    }
    question_signals = _valid_question_signals(out.get("questionSignals"), valid_ids)
    interpretation = out.get("interpretationCandidate")
    if not isinstance(interpretation, dict):
        interpretation = None
    elif not str(interpretation.get("criterionLabel") or "").strip():
        interpretation = None
    else:
        evidence_ids = [
            str(eid) for eid in (interpretation.get("evidenceIds") or [])
            if str(eid) in valid_ids
        ]
        signal_type = interpretation.get("signalType")
        strength = interpretation.get("strength")
        if not evidence_ids or signal_type not in {
            "rationale", "context", "evaluation", "repetition",
        } or strength not in {"strong", "weak"}:
            interpretation = None
        else:
            interpretation = {
                "criterionLabel": str(interpretation["criterionLabel"]).strip(),
                "evidenceIds": list(dict.fromkeys(evidence_ids)),
                "quotes": [
                    str(q).strip() for q in (interpretation.get("quotes") or [])
                    if str(q).strip()
                ][:4],
                "signalType": signal_type,
                "strength": strength,
            }
            for prior in prior_candidates:
                if str(prior.get("candidateLabel") or "").strip().casefold() != (
                    interpretation["criterionLabel"].casefold()
                ):
                    continue
                prior_id = str(prior.get("evidenceId") or "").strip()
                if prior_id and prior_id not in interpretation["evidenceIds"]:
                    interpretation["evidenceIds"].append(prior_id)
                prior_quote = str(prior.get("quote") or "").strip()
                if prior_quote and prior_quote not in interpretation["quotes"]:
                    interpretation["quotes"].append(prior_quote)
            interpretation["quotes"] = interpretation["quotes"][:4]

    # 예산/가격 제약도 LLM(topic_extraction)이 kind=constraint로 추출한다 — 키워드 가드 없음.
    # (실제 경로 하드코딩 제거, 2026-06-24. 프롬프트가 canonical "가격 {min}~{max}원"을 지시;
    #  mock은 LLM이 없으므로 mock_rules가 자체 결정론 규칙으로 동등 출력을 만든다.)
    return {
        "topics": topics,
        "questionSignals": question_signals,
        "interpretationCandidate": interpretation,
    }
