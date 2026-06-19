"""Judge layer (llm-measurement-design.md M5/M6) — 인과 엣지 검증.

builder(service agent 파이프라인)가 만든 인과 주장(MOTIVATES/REFINES)을
독립 LLM이 인용 근거와 대조해 평결한다. Judge는:
  - 내용을 절대 쓰지 않는다 — verification 필드(평결)만 갱신 (M6 쓰기 권한 분할)
  - 범주로만 말한다 — 스칼라 없음 (M1)
  - 턴을 막지 않는다 — FastAPI BackgroundTasks로 응답 후 실행 (M5)
  - 권위 서열을 지킨다 — human_* 평결은 건드리지 않는다 (사용자 > judge > builder)
"""
import logging

from app.db import models
from app.db.database import SessionLocal
from app.llm.prompts import SYSTEM_BY_TASK, render_user_context
from app.llm.provider import LLMMessage, get_judge_provider
from app.ontology.levels import CAUSAL_ACCEPT_LEVELS, CAUSAL_EVIDENCE_LEVELS, CAUSAL_EVIDENCE_VALUE
from app.ontology.relation_classifier import relation_nature

logger = logging.getLogger(__name__)

# judge가 재검토하는 상태 — judge_*(이미 평결)와 human_*(상위 권위)는 제외
_JUDGEABLE = ("unverified", "llm_thresholded", "llm_downgraded")


def _topic_quotes(topic: models.IntentionTopic | None) -> list[str]:
    if topic is None:
        return []
    quotes = [e.get("quoteOrSummary") for e in (topic.hints or {}).get("evidence", [])
              if isinstance(e, dict) and e.get("quoteOrSummary")]
    return quotes[:4]


async def judge_causal_relations(session_id: str) -> dict:
    """세션의 인과 관계를 평결한다. 자체 DB 세션 사용 (background-task 안전)."""
    db = SessionLocal()
    judged = skipped = failed = 0
    try:
        provider = get_judge_provider()
        relations = (
            db.query(models.IntentionRelation)
            .filter(models.IntentionRelation.session_id == session_id)
            .all()
        )
        for rel in relations:
            if relation_nature(rel.type) != "causal" or rel.verification not in _JUDGEABLE:
                skipped += 1
                continue
            src = db.get(models.IntentionTopic, rel.source_topic_id)
            tgt = db.get(models.IntentionTopic, rel.target_topic_id)
            context = {
                "sourceTopicLabel": src.label if src else rel.source_topic_id,
                "targetTopicLabel": tgt.label if tgt else rel.target_topic_id,
                "type": rel.type,
                "rationale": rel.rationale,
                "causalEvidence": rel.causal_evidence,
                "sourceQuotes": _topic_quotes(src),
                "targetQuotes": _topic_quotes(tgt),
            }
            try:
                out = await provider.generate_json(
                    [LLMMessage(role="system", content=SYSTEM_BY_TASK["judge_causal_relation"]),
                     LLMMessage(role="user", content=render_user_context(context))],
                    task="judge_causal_relation", context=context,
                )
            except Exception:  # noqa: BLE001
                logger.exception("judge call failed for relation %s — left as-is", rel.id)
                failed += 1
                continue
            verdict = out.get("verdict")
            level = out.get("supportedLevel")
            if verdict == "supported" and level in CAUSAL_EVIDENCE_LEVELS:
                rel.verification = (
                    "judge_supported" if level in CAUSAL_ACCEPT_LEVELS else "judge_downgraded"
                )
                rel.causal_evidence = level
                rel.plausibility = CAUSAL_EVIDENCE_VALUE[level]
            elif verdict == "downgrade" and level in CAUSAL_EVIDENCE_LEVELS:
                rel.verification = "judge_downgraded"
                rel.causal_evidence = level
                rel.plausibility = CAUSAL_EVIDENCE_VALUE[level]
            elif verdict == "rejected":
                rel.verification = "judge_rejected"
            else:
                failed += 1  # malformed verdict — 평결 보류
                continue
            judged += 1
        db.commit()
        return {"sessionId": session_id, "judged": judged, "skipped": skipped, "failed": failed}
    finally:
        db.close()
