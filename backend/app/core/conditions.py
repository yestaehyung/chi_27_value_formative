"""본실험 between-subjects 조건 배정.

세 조건은 '숨은 의도를 다루는 세 단계'를 분해한다:
  baseline1 — 의도 추론 없음. 발화를 그대로 LLM에 넘겨 추천한다 (일반 쇼핑 챗봇).
  baseline2 — 의도를 추론해 추천에 쓴다. 다만 **외재화하지 않는다**   ← b1 대비 = *추론*의 효과
  ours      — 추론 + 외재화 + 사용자 수정 가능                        ← b2 대비 = *외재화*의 효과

세 조건의 차이를 읽는 법:
  baseline1 → baseline2   의도 추론이 추천 품질을 얼마나 올리는가
  baseline2 → ours        추론을 보여주고 고치게 하는 것이 무엇을 더 주는가

**baseline1은 추론 자체를 하지 않는다.** 그래서 과제 직후 '기준별 검증' 설문(⑤)을
baseline1에서는 물을 수 없다 — 검증할 기준이 생성되지 않기 때문이다. b2/ours에서만 측정한다.

**baseline2는 추론한 기준을 사용자 확인 없이 그대로 쓴다.** 이것이 evidence-purity 규칙
(`agents/recommender.py`: 확인된 기준만 리랭크에 투입)의 예외다. 그 규칙은 *확인 경로가 있는*
조건을 전제로 만들어졌는데 baseline2에는 확인 UI가 없으므로, 규칙을 그대로 적용하면 추론이
추천에 영원히 닿지 못해 baseline1과 구분이 사라진다. `USES_UNCONFIRMED_INFERENCE`가 그 분기다.
"""
from sqlalchemy import func
from sqlalchemy.orm import Session as DbSession

from app.db import models

STUDY_CONDITIONS: tuple[str, ...] = ("baseline1", "baseline2", "ours")

#: 이 조건에서 사용자 모델(의도 추론 파이프라인)을 돌리는가.
#: False면 `run_preference_commit`을 건너뛴다 — 의도 토픽/앵커/충돌이 생성되지 않는다.
INFERS_INTENTION = {"baseline1": False, "baseline2": True, "ours": True}
#: 추론한 기준을 화면에 보여주는가 (칩 확인·충돌 발화·앵커바).
SHOWS_CRITERIA = {"baseline1": False, "baseline2": False, "ours": True}
#: 기준을 확인·수정할 수 있는가.
ALLOWS_CORRECTION = {"baseline1": False, "baseline2": False, "ours": True}
#: 사용자 확인을 거치지 않은 추론 기준도 추천 리랭크에 넣는가.
#: baseline2는 확인 UI가 없으므로 넣지 않으면 추론이 추천에 반영될 길이 없다(위 docstring).
USES_UNCONFIRMED_INFERENCE = {"baseline1": False, "baseline2": True, "ours": False}

#: 폐기·개명된 옛 슬러그 → 현재 슬러그. `database.py::_migrate`와 조건 조회가 함께 쓴다.
#: explanation_only(표시하되 수정 불가)는 2026-08-06 설계에서 폐기 — 매핑 없이 재배정된다.
LEGACY_CONDITIONS = {"baseline": "baseline2", "correctable": "ours"}


def normalize_condition(value: str | None) -> str | None:
    """옛 슬러그를 현재 슬러그로 옮긴다. 모르는 값은 None (→ 재배정 대상)."""
    if value in STUDY_CONDITIONS:
        return value
    return LEGACY_CONDITIONS.get(value or "")


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
        slug = normalize_condition(cond)
        if slug in counts:
            counts[slug] += n
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
        slug = normalize_condition(cond)
        if slug in counts:
            counts[slug] += n
    return counts


FORCED_CONDITION_KEY = "forced_condition"


def get_forced_condition(db: DbSession) -> str | None:
    """관리자가 고정한 배정 조건 (없으면 None = 자동 균형).
    조건별 순차 모집용 — 관리자 페이지(/admin)에서 설정하며 재배포가 필요 없다."""
    row = db.get(models.StudySetting, FORCED_CONDITION_KEY)
    slug = normalize_condition(row.value) if row and row.value else None
    return slug if slug in STUDY_CONDITIONS else None


def set_forced_condition(db: DbSession, condition: str | None) -> str | None:
    row = db.get(models.StudySetting, FORCED_CONDITION_KEY)
    if row is None:
        row = models.StudySetting(key=FORCED_CONDITION_KEY)
        db.add(row)
    row.value = condition
    return condition


def balance_pool() -> tuple[str, ...]:
    """자동 균형 배정에 참여하는 조건들. `VC_BALANCE_CONDITIONS`로 물결별 제한 —
    수집이 끝난 조건이 카운트 최소가 되는 순간 다시 배정되는 누수를 막는다."""
    from app.core.config import settings

    pool = tuple(c for c in settings.balance_conditions if c in STUDY_CONDITIONS)
    return pool or STUDY_CONDITIONS


def assign_condition(db: DbSession) -> str:
    """관리자 고정 조건이 있으면 그 조건, 없으면 배정 풀에서 가장 적게 배정된
    조건(minimization). 동률이면 STUDY_CONDITIONS 순서."""
    forced = get_forced_condition(db)
    if forced is not None:
        return forced
    counts = assigned_counts(db)
    pool = balance_pool()
    return min(pool, key=lambda c: (counts[c], STUDY_CONDITIONS.index(c)))


def ensure_condition(db: DbSession, participant: models.Participant) -> str:
    """참가자에게 조건이 없으면 지금 배정한다. 이미 있으면 그대로 — **재배정하지 않는다**
    (한 사람의 여러 과제는 반드시 같은 조건이어야 한다). 옛 슬러그는 현재 슬러그로 옮긴다."""
    slug = normalize_condition(participant.study_condition)
    if slug is not None:
        participant.study_condition = slug
        return slug
    participant.study_condition = assign_condition(db)
    return participant.study_condition
