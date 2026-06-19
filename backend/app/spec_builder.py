"""참가자 자연어 명세 파일 (= AI memory / intent specification).

KG의 사람용 렌더링. 참가자의 여러 세션에 누적된 trait(TCV) 가치 + 동기(motivation)
+ 현재 기준/회피 + 사용자 수정 이력을 하나의 마크다운 문서로 합성한다.
매 턴(혹은 세션 종료) 호출되어 점점 보완된다. 수정은 칩에서 하고, 이 파일은
그 결과를 비추는 읽기 전용 거울 (추적성 위해 편집은 구조화된 KG 쪽에서).
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session as DbSession

from app.agents.motivation import MOTIVATION_SPEC
from app.db import models
from app.ontology.anchor_mapper import TRAIT_ANCHORS

ANCHOR_KO = {
    "Functional": "실용·성능", "Social": "사회적 이미지·관계", "Emotional": "정서·안심",
    "Epistemic": "탐색·학습", "Conditional": "상황 적합",
}
MOTIV_KO = {
    "Adventure": "탐험·발견의 재미", "Gratification": "자기보상", "Role": "남을 위한 쇼핑의 즐거움",
    "BargainValue": "득템·가성비의 즐거움", "SocialShopping": "함께 고르기", "Idea": "트렌드 탐색",
    "Utilitarian": "효율·과업 완료",
}


def _participant_sessions(db: DbSession, participant_id: str) -> list[models.Session]:
    return (
        db.query(models.Session)
        .filter(models.Session.participant_id == participant_id)
        .order_by(models.Session.started_at)
        .all()
    )


def _aggregate_traits(db: DbSession, session_ids: list[str]) -> dict[str, float]:
    """참가자의 모든 세션 topic→anchor를 anchor별 평균 (trait는 세션 횡단 누적)."""
    if not session_ids:
        return {}
    topic_ids = [
        t.id for t in db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id.in_(session_ids))
        .filter(models.IntentionTopic.status.notin_(["rejected_by_user", "inactive"]))
        .all()
    ]
    if not topic_ids:
        return {}
    agg: dict[str, list[float]] = {}
    for am in db.query(models.AnchorMapping).filter(models.AnchorMapping.topic_id.in_(topic_ids)).all():
        if am.anchor in TRAIT_ANCHORS:
            agg.setdefault(am.anchor, []).append(am.score)
    return {a: round(sum(v) / len(v), 2) for a, v in agg.items()}


def _latest_motivation(db: DbSession, session_ids: list[str]) -> dict[str, float]:
    """가장 최근 세션의 motivation 점수 (동기는 상황적이라 최신을 대표값으로)."""
    for sid in reversed(session_ids):
        snap = (
            db.query(models.PreferenceStateSnapshot)
            .filter(models.PreferenceStateSnapshot.session_id == sid)
            .order_by(models.PreferenceStateSnapshot.created_at.desc())
            .first()
        )
        if snap and (snap.motivation_scores or {}):
            return snap.motivation_scores
    return {}


def build_participant_spec(db: DbSession, participant_id: str) -> str:
    """참가자 명세 마크다운 합성 (결정적 — LLM 없이 KG에서 직접 렌더)."""
    p = db.get(models.Participant, participant_id)
    sessions = _participant_sessions(db, participant_id)
    sids = [s.id for s in sessions]

    traits = _aggregate_traits(db, sids)
    motivation = _latest_motivation(db, sids)

    # 최신 세션의 현재 기준/회피
    latest_snap = None
    if sids:
        latest_snap = (
            db.query(models.PreferenceStateSnapshot)
            .filter(models.PreferenceStateSnapshot.session_id == sids[-1])
            .order_by(models.PreferenceStateSnapshot.created_at.desc())
            .first()
        )
    hard = latest_snap.hard_constraints if latest_snap else []
    avoid = latest_snap.avoidances if latest_snap else []

    # 사용자가 확인/수정한 기준 (참가자 전체 세션)
    confirmed = (
        db.query(models.IntentionTopic)
        .filter(models.IntentionTopic.session_id.in_(sids or [""]))
        .filter(models.IntentionTopic.status.in_(["confirmed", "corrected_by_user"]))
        .all()
    )

    lines: list[str] = []
    lines.append(f"# 참가자 {participant_id} 쇼핑 프로파일")
    lines.append(f"_세션 {len(sessions)}개 누적 · 자동 합성된 사용자 명세(AI memory)_\n")

    # 안정적 가치 (trait)
    lines.append("## 안정적 가치 (Consumption Values · 비교적 안정적인 특성)")
    if traits:
        for a in sorted(TRAIT_ANCHORS, key=lambda x: -traits.get(x, 0)):
            if traits.get(a, 0) >= 0.15:
                lines.append(f"- **{ANCHOR_KO[a]}** ({a}): {traits[a]:.2f}")
    else:
        lines.append("- _아직 파악된 가치가 없습니다._")

    # 쇼핑 동기 (motivation)
    lines.append("\n## 쇼핑 동기 (Hedonic/Utilitarian · 상황적)")
    strong = [(d, v) for d, v in sorted(motivation.items(), key=lambda x: -x[1]) if v >= 0.4]
    if strong:
        for d, v in strong:
            lines.append(f"- **{MOTIV_KO.get(d, d)}** ({d}): {v:.2f} — {MOTIVATION_SPEC.get(d, {}).get('survey', '')}")
    else:
        lines.append("- _아직 드러난 쇼핑 동기가 없습니다._")

    # 현재 기준 / 회피
    lines.append("\n## 현재 기준 / 회피")
    if hard:
        lines.append(f"- 필수: {', '.join(hard)}")
    if avoid:
        lines.append(f"- 회피: {', '.join(avoid)}")
    if not hard and not avoid:
        lines.append("- _아직 확정된 제약이 없습니다._")

    # 사용자가 직접 확인/수정한 기준
    if confirmed:
        lines.append("\n## 사용자가 확인·수정한 기준")
        for t in confirmed[:8]:
            tag = "수정" if t.status == "corrected_by_user" else "확인"
            lines.append(f"- [{tag}] {t.label}")

    return "\n".join(lines)


def update_participant_spec(db: DbSession, participant_id: str) -> models.Participant | None:
    """명세 재합성 + 버전 증가 (semantic commit). 내용이 바뀌었을 때만 버전 올림."""
    p = db.get(models.Participant, participant_id)
    if p is None:
        return None
    new_md = build_participant_spec(db, participant_id)
    if new_md != (p.spec_markdown or ""):
        p.spec_markdown = new_md
        p.spec_version = (p.spec_version or 0) + 1
        p.updated_at = datetime.now(timezone.utc)
        db.commit()
    return p
