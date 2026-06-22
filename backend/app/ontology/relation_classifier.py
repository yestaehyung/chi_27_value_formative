"""Stage 4 — Relation Classification (spec §15.4). LLM fetch / DB apply split."""
from sqlalchemy.orm import Session as DbSession

from app.core.ids import new_id
from app.db import models
from app.llm.prompts import SYSTEM_BY_TASK, render_user_context
from app.llm.provider import LLMMessage, LLMProvider

# 의도 간 관계의 성질별 메타 분류 (RIG ideation 1) — 정의는 schema.py 단일 출처.
#   co_occurrence(동시적) / temporal(비동시적) / causal(인과)
from app.ontology.schema import RELATION_TYPE_TO_NATURE as RELATION_NATURE  # noqa: E402


# graph design D4 + 측정 설계 M1: 인과 엣지의 증거 수준은 범주(causalEvidence)로
# 받고, plausibility 숫자는 levels.py 테이블의 파생 캐시다. 인과 인정은
# CAUSAL_ACCEPT_LEVELS("사용자가 직접 말한 인과만 통과") 멤버십으로 결정된다.
# 구(舊) 숫자 경로 하위호환용 임계값 — 레벨이 없고 숫자만 온 경우에만 사용.
CAUSAL_PLAUSIBILITY_THRESHOLD = 0.9


def relation_nature(rtype: str) -> str:
    return RELATION_NATURE.get(rtype, "co_occurrence")


def effective_nature(rtype: str, verification: str | None = None) -> str:
    """검증을 반영한 성질: 인과인데 증거 수준 미달/judge·사람 기각이면 co_occurrence로
    강등해 보고한다 (관계 행 자체는 보존 — 동시출현 사실은 여전히 참이므로)."""
    nature = relation_nature(rtype)
    if nature == "causal" and verification in (
        "llm_downgraded", "judge_downgraded", "judge_rejected", "human_rejected",
    ):
        return "co_occurrence"
    return nature


async def fetch_relations(provider: LLMProvider, topic_labels: list[str]) -> list[dict]:
    """LLM phase — returns raw relation dicts."""
    if len(topic_labels) < 2:
        return []
    context = {"topicLabels": topic_labels}
    messages = [
        LLMMessage(role="system", content=SYSTEM_BY_TASK["relation_classification"]),
        LLMMessage(role="user", content=render_user_context(context)),
    ]
    out = await provider.generate_json(messages, task="relation_classification", context=context)
    return [r for r in (out.get("relations") or []) if isinstance(r, dict)]


def apply_relations(
    db: DbSession,
    session: models.Session,
    relations: list[dict],
) -> list[models.IntentionRelation]:
    """Write phase — resolves labels to topic rows, dedupes, writes."""
    topics = (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id == session.id)
        .filter(models.IntentionTopic.status.notin_(["rejected_by_user", "inactive"]))
        .all()
    )
    by_label = {t.label: t for t in topics}
    existing_keys = {
        (r.source_topic_id, r.target_topic_id, r.type)
        for r in db.query(models.IntentionRelation)
        .filter(models.IntentionRelation.session_id == session.id)
        .all()
    }

    created: list[models.IntentionRelation] = []
    for rel in relations:
        src = by_label.get(rel.get("sourceTopicLabel") or "")
        tgt = by_label.get(rel.get("targetTopicLabel") or "")
        rtype = rel.get("type")
        if src is None or tgt is None or not rtype or src.id == tgt.id:
            continue
        key = (src.id, tgt.id, rtype)
        if key in existing_keys:
            continue
        try:
            strength = max(0.0, min(1.0, float(rel.get("strength", 0.5))))
        except (TypeError, ValueError):
            strength = 0.5
        # D4 + M1: 인과 타입은 증거 수준(causalEvidence 범주)으로 판정한다.
        # plausibility 숫자는 레벨에서 산출되는 파생 캐시 (levels.py).
        from app.ontology.levels import (
            CAUSAL_ACCEPT_LEVELS, CAUSAL_EVIDENCE_LEVELS, CAUSAL_EVIDENCE_VALUE,
        )

        causal_evidence: str | None = None
        plausibility: float | None = None
        verification = "unverified"
        if relation_nature(rtype) == "causal":
            level = rel.get("causalEvidence")
            if level in CAUSAL_EVIDENCE_LEVELS:
                causal_evidence = level
                plausibility = CAUSAL_EVIDENCE_VALUE[level]
                verification = (
                    "llm_thresholded" if level in CAUSAL_ACCEPT_LEVELS else "llm_downgraded"
                )
            else:  # 구(舊) 숫자 경로 하위호환
                try:
                    plausibility = max(0.0, min(1.0, float(rel["plausibility"])))
                except (KeyError, TypeError, ValueError):
                    plausibility = None
                if plausibility is not None:
                    verification = (
                        "llm_thresholded"
                        if plausibility >= CAUSAL_PLAUSIBILITY_THRESHOLD
                        else "llm_downgraded"
                    )
        row = models.IntentionRelation(
            id=new_id("rel"),
            session_id=session.id,
            source_topic_id=src.id,
            target_topic_id=tgt.id,
            type=rtype,
            strength=strength,
            rationale=rel.get("rationale"),
            evidence_ids=[],
            verification=verification,
            plausibility=plausibility,
            causal_evidence=causal_evidence,
        )
        db.add(row)
        existing_keys.add(key)
        created.append(row)
    db.flush()
    return created
