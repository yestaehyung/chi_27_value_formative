"""본실험 between-subjects 조건 배정.

세 조건은 '외재화의 어느 부분이 효과를 내는가'를 분해한다:
  baseline          — 추론한 기준을 보여주지 않음 (일반 쇼핑 챗봇)
  explanation_only  — 기준을 보여주되 수정 불가        ← baseline 대비 차이 = *가시성*의 효과
  correctable       — 기준을 보여주고 수정 가능 (Ours) ← explanation_only 대비 = *수정 가능성*의 효과

**세 조건 모두 백엔드는 동일하게 추론한다.** 안 보여줄 뿐이다. 그래야 추론 품질이
조건과 무관한 상수가 되고, 과제 직후 '기준별 검증' 설문을 세 조건 전부에서 물을 수 있다
(baseline 참가자는 화면에서 본 적 없는 기준을 판정하므로 앵커링 없는 가장 깨끗한 측정이다).
"""
from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

from app.db import models

STUDY_CONDITIONS: tuple[str, ...] = ("baseline", "explanation_only", "correctable")

#: 이 조건에서 추론한 기준을 화면에 보여주는가
SHOWS_CRITERIA = {"baseline": False, "explanation_only": True, "correctable": True}
#: 이 조건에서 기준을 수정·확인할 수 있는가
ALLOWS_CORRECTION = {"baseline": False, "explanation_only": False, "correctable": True}


def assigned_counts(db: DbSession) -> dict[str, int]:
    """조건별 **배정된** 참가자 수 — 배정의 기준.

    한때 '과제를 실제 시작한 참가자'만 셌는데, 그건 틀렸다: 참가자 여럿이 연달아 설문을
    내면(랩 세션·온라인 배치에서 정상 상황) 아무도 아직 세션이 없어 카운트가 전부 0이라
    전원 같은 조건을 받는다. 배정 시점에 슬롯이 점유되는 것으로 봐야 한다.

    이탈자는 그 조건 한 자리를 물고 있게 되지만, 그건 과모집으로 흡수하는 통상적인 문제다
    (`condition_balance` API가 assigned/started 차이를 보여주므로 눈으로 확인 가능).
    """
    rows = (
        db.query(models.Participant.study_condition, func.count(models.Participant.id))
        .filter(models.Participant.study_condition.isnot(None))
        .group_by(models.Participant.study_condition)
        .all()
    )
    counts = {c: 0 for c in STUDY_CONDITIONS}
    for cond, n in rows:
        if cond in counts:
            counts[cond] = n
    return counts


def started_counts(db: DbSession) -> dict[str, int]:
    """조건별 실제로 과제를 시작한 참가자 수 — 모니터링용(배정에는 쓰지 않는다)."""
    rows = (
        db.query(models.Participant.study_condition, func.count(func.distinct(models.Participant.id)))
        .join(models.Session, models.Session.participant_id == models.Participant.id)
        .filter(models.Participant.study_condition.isnot(None))
        .filter(models.Session.mode == "manual")  # 시뮬레이션 세션은 무관
        .group_by(models.Participant.study_condition)
        .all()
    )
    counts = {c: 0 for c in STUDY_CONDITIONS}
    for cond, n in rows:
        if cond in counts:
            counts[cond] = n
    return counts


def assign_condition(db: DbSession) -> str:
    """가장 적게 배정된 조건을 준다 (minimization). 동률이면 STUDY_CONDITIONS 순서."""
    counts = assigned_counts(db)
    return min(STUDY_CONDITIONS, key=lambda c: (counts[c], STUDY_CONDITIONS.index(c)))


def ensure_condition(db: DbSession, participant: models.Participant) -> str:
    """참가자에게 조건이 없으면 지금 배정한다. 이미 있으면 그대로 — **재배정하지 않는다**
    (한 사람의 3개 과제는 반드시 같은 조건이어야 한다)."""
    if participant.study_condition in STUDY_CONDITIONS:
        return participant.study_condition
    participant.study_condition = assign_condition(db)
    return participant.study_condition
