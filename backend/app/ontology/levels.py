"""측정 레벨 → 효용 캐시 변환 테이블 (llm-measurement-design.md M1–M3, §7.1).

원칙: LLM은 관찰 기준으로 정의된 범주(level)만 내고, 숫자는 이 모듈의
고정 테이블이 결정론적으로 변환한다. 숫자 컬럼은 결정 층(상품 랭킹·정렬)용
파생 캐시이며, 측정 주장은 서열까지만이다 (algorithm-audit.md 참조 —
절대값이 아니라 순서 관계만 변호 가능).

이 모듈이 변환의 단일 출처다 — 레벨 체계를 바꿀 때 여기만 고친다.
"""

# Topic confidence: 의도 가설 자체의 확신 (P1)
#   directly_stated  — 기준이 사용자 발화에 그대로 등장
#   strong_inference — 인용 스팬에서 맥락상 명확히 추론됨
#   weak_inference   — 약한 힌트뿐
CONFIDENCE_LEVELS = ("directly_stated", "strong_inference", "weak_inference")
CONFIDENCE_LEVEL_VALUE = {
    "directly_stated": 0.85,
    "strong_inference": 0.6,
    "weak_inference": 0.35,
}

# Causal evidence: 인과(MOTIVATES/REFINES) 주장의 증거 수준 (D4 후속, M5)
#   stated_cause     — 사용자가 인과를 직접 언어화 ("선물*이라서* …")
#   strong_inference — 맥락상 강한 추론
#   weak             — 동시출현 이상의 근거 없음
CAUSAL_EVIDENCE_LEVELS = ("stated_cause", "strong_inference", "weak")
CAUSAL_EVIDENCE_VALUE = {
    "stated_cause": 0.95,
    "strong_inference": 0.75,
    "weak": 0.5,
}
# 인과로 인정되는 레벨 (effectiveNature=causal 유지) — "사용자가 말한 인과만 통과"
CAUSAL_ACCEPT_LEVELS = ("stated_cause",)

# Motivation 증거 수준 (M8): 발화 1개가 설문 문항 동의의 증거가 되는 강도.
#   asserts  — 문항 동의를 단정할 발화
#   suggests — 동의를 시사하는 발화
#   hints    — 약한 힌트
MOTIVATION_LEVELS = ("asserts", "suggests", "hints")
MOTIVATION_LEVEL_VALUE = {"asserts": 0.8, "suggests": 0.5, "hints": 0.3}


# Anchor score 파생 (OQ2 결정: derive-from-triple) — LLM이 내는 범주 3종에서
# 결정론적으로 산출. 곱 형태라 세 축 모두에 단조.
_ANCHOR_CONF_W = {"confirmed": 0.95, "inferred": 0.75, "weak": 0.5}
_ANCHOR_STRENGTH_W = {"high": 1.0, "medium": 0.85, "low": 0.65}
_ANCHOR_IMPACT_W = {"high": 1.0, "medium": 0.85, "low": 0.65}


def derive_anchor_score(confidence: str, evidence_strength: str, decision_impact: str) -> float:
    return round(
        _ANCHOR_CONF_W.get(confidence, 0.75)
        * _ANCHOR_STRENGTH_W.get(evidence_strength, 0.85)
        * _ANCHOR_IMPACT_W.get(decision_impact, 0.85),
        2,
    )
