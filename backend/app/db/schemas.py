"""Pydantic request schemas (API inputs)."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    # demo = 상품 풀·추천 품질을 눈으로 확인하는 용도. manual이 아니므로 조건 배정을 받지 않고
    # (sessions.py) 조건 균형 집계에도 안 잡힌다 (conditions.started_counts) — 데모가 실험
    # 데이터에 섞이는 경로를 구조적으로 없앤다.
    mode: Literal["manual", "simulation", "demo"] = "manual"
    scenarioId: str = "gift_for_other"  # "custom" = 회상 인터뷰 기반 자유 시나리오 (FS1)
    #: None이면 서버가 균형 배정한다(본실험 참가자의 정상 경로). 값을 주면 **신규 참가자에
    #: 한해** 그대로 쓴다 — 테스트·데모가 특정 조건을 고정하기 위한 통로다. 기존 참가자는
    #: 언제나 자기에게 붙은 조건이 이긴다(한 사람의 여러 과제는 같은 조건이어야 하므로).
    studyCondition: Literal["baseline1", "baseline2", "ours"] | None = None
    participantId: Optional[str] = None
    userAgentId: Optional[str] = None
    customTitle: Optional[str] = None
    customContext: Optional[str] = None  # 회상 인터뷰에서 추출한 초기 쇼핑 맥락
    #: 본실험(2026-08-06~) 경로 — 시나리오 대신 **카테고리**로 과제를 연다. 값이 있으면
    #: scenarioId를 보지 않는다. 시나리오는 시뮬레이션·합성에서 계속 쓰이므로 남겨둔다.
    category: Optional[str] = None
    #: 참가자가 스스로 매긴 그 카테고리에 대한 친숙도. 본실험의 within-subjects 요인이다
    #: (친근 2 + 비친근 2). 시나리오에 고정할 수 없는, 참가자가 선택 시점에 주는 값이다.
    familiarity: Optional[Literal["familiar", "unfamiliar"]] = None


class TurnRequest(BaseModel):
    role: Literal["user", "user_agent"] = "user"
    content: str = Field(min_length=1)
    # 전송 멱등 키 (2026-08-18) — 같은 키의 턴이 이미 있으면 서버는 새 턴을 만들지 않는다
    clientRequestId: str | None = None
    # 입력 경로 (2026-08-19) — 답변 칩 클릭(suggestion) vs 직접 타이핑(typed) 구분
    inputSource: Literal["suggestion", "typed"] | None = None


class FeedbackRequest(BaseModel):
    productId: str
    type: Literal[
        "click", "view_detail", "like", "dislike", "compare",
        "add_to_cart", "purchase", "reject", "quick_reason", "manual_correction",
    ]
    turnId: Optional[str] = None
    reasonCode: Optional[
        Literal[
            "too_cheap_looking", "too_expensive", "not_trustworthy",
            "low_long_term_reviews", "too_common", "not_functional_enough",
            "bad_design", "wrong_context", "wrong_recipient", "other",
        ]
    ] = None
    reasonText: Optional[str] = None


class ConflictResolveRequest(BaseModel):
    optionId: str
    manualText: Optional[str] = None


class ChipActionRequest(BaseModel):
    action: Literal[
        "confirm", "reject", "increase_priority", "decrease_priority",
        "edit_label", "show_evidence",
    ]
    manualLabel: Optional[str] = None
    # true면 수정만 저장하고 재추천은 건너뛴다 — 프론트가 연속 수정을 디바운스해
    # refresh-recommendation 1회로 모아 보낸다 (2026-08-19 v4: 11/23 세션에서
    # 수정 연타가 에이전트 메시지 3~5연발을 만들던 문제).
    deferRecommend: bool = False


class RefreshRecommendationRequest(BaseModel):
    # 마지막 재추천 이후 누적된 수정 내역(표시용) — 상태 진실은 DB가 이미 갖고 있고,
    # 이 목록은 렌더러가 "무엇이 반영됐는지"를 서두에 언급하는 데만 쓴다.
    corrections: list[dict] = []


class SimulationRequest(BaseModel):
    scenarioId: str = "gift_for_other"
    userAgentProfileId: str = "ua_gift_smartwatch_social_risk_averse"
    maxTurns: int = 8
    autoResolveConflicts: bool = True


class PairMiningRequest(BaseModel):
    sessionIds: Optional[list[str]] = None
    minPairs: int = 5
    groupBy: Optional[list[str]] = None


class FeatureStatusRequest(BaseModel):
    status: Literal["candidate", "researcher_approved", "merged_into_concept", "rejected"]
