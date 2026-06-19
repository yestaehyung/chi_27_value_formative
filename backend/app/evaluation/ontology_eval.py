"""Ontology 품질 지표 (spec §22.1 + Latent Yield).

Latent Yield — "시스템이 사용자가 말하지 않은 기준을 얼마나 만들어내고,
그게 맞다고 확인받는가":
    latentYield = implicitLatentRatio × latentConfirmRate
베이스라인: PSCon 원대화 0% → 발화 추출 ~4% → 피드백 추출 ~21% (2026-06-05 측정).

v2 (graph design D1, 2026-06-11): hidden을 노드 라벨이 아니라 증거 엣지로 정의 —
hidden(t) := t에 explicit 채널 증거 엣지가 하나도 없음. v1·v2를 나란히 보고한다
(전환기 비교용). 증거 엣지가 전혀 없는 구(舊) topic은 노드 라벨로 폴백.
"""
from sqlalchemy.orm import Session as DbSession

from app.db import models

CONFIRMED_STATUSES = ("confirmed", "corrected_by_user")


def _hidden_by_edges(db: DbSession, topics: list[models.IntentionTopic]) -> dict[str, bool]:
    """topic_id → hidden 여부 (explicit 엣지 부재). 엣지 없는 topic은 노드 라벨 폴백."""
    if not topics:
        return {}
    rows = (
        db.query(models.IntentionEvidence.topic_id, models.IntentionEvidence.explicitness)
        .filter(models.IntentionEvidence.topic_id.in_([t.id for t in topics]))
        .all()
    )
    has_edges: set[str] = set()
    has_explicit: set[str] = set()
    for topic_id, explicitness in rows:
        has_edges.add(topic_id)
        if explicitness == "explicit":
            has_explicit.add(topic_id)
    return {
        t.id: (t.id not in has_explicit) if t.id in has_edges
        else t.explicitness in ("implicit", "latent")  # legacy fallback
        for t in topics
    }


def compute_latent_yield(db: DbSession, session_id: str | None = None) -> dict:
    q = db.query(models.IntentionTopic)
    if session_id:
        q = q.filter(models.IntentionTopic.session_id == session_id)
    else:
        # 전역 지표: PSCon 배치 분석 세션의 토픽은 제외 (참가자/시뮬 연구 데이터만)
        q = q.join(
            models.Session, models.IntentionTopic.session_id == models.Session.id
        ).filter(models.Session.mode != "pscon")
    topics = q.all()
    total = len(topics)
    if total == 0:
        return {"totalTopics": 0, "implicitLatentRatio": None,
                "latentConfirmRate": None, "latentYield": None}

    latent = [t for t in topics if t.explicitness in ("implicit", "latent")]
    confirmed_latent = [t for t in latent if t.status in CONFIRMED_STATUSES]
    ratio = len(latent) / total
    confirm_rate = (len(confirmed_latent) / len(latent)) if latent else 0.0
    by_source: dict[str, dict] = {}
    for t in topics:
        s = by_source.setdefault(t.source, {"total": 0, "implicitLatent": 0})
        s["total"] += 1
        if t.explicitness in ("implicit", "latent"):
            s["implicitLatent"] += 1

    # v2 — 엣지 기반 hidden 정의 (explicit 증거 엣지 부재)
    hidden_map = _hidden_by_edges(db, topics)
    hidden = [t for t in topics if hidden_map.get(t.id)]
    confirmed_hidden = [t for t in hidden if t.status in CONFIRMED_STATUSES]
    hidden_ratio = len(hidden) / total
    hidden_confirm = (len(confirmed_hidden) / len(hidden)) if hidden else 0.0

    return {
        "totalTopics": total,
        "implicitLatentCount": len(latent),
        "implicitLatentRatio": round(ratio, 3),
        "latentConfirmRate": round(confirm_rate, 3),
        "latentYield": round(ratio * confirm_rate, 3),
        "bySource": {
            k: {**v, "ratio": round(v["implicitLatent"] / v["total"], 2)}
            for k, v in by_source.items()
        },
        "v2": {
            "hiddenCount": len(hidden),
            "hiddenRatio": round(hidden_ratio, 3),
            "hiddenConfirmRate": round(hidden_confirm, 3),
            "latentYield": round(hidden_ratio * hidden_confirm, 3),
        },
    }
