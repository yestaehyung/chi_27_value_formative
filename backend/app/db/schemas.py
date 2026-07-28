"""Pydantic request schemas (API inputs)."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    # demo = 상품 풀·추천 품질을 눈으로 확인하는 용도. manual이 아니므로 조건 배정을 받지 않고
    # (sessions.py) 조건 균형 집계에도 안 잡힌다 (conditions.started_counts) — 데모가 실험
    # 데이터에 섞이는 경로를 구조적으로 없앤다.
    mode: Literal["manual", "simulation", "demo"] = "manual"
    scenarioId: str = "gift_for_other"  # "custom" = 회상 인터뷰 기반 자유 시나리오 (FS1)
    studyCondition: Literal["baseline", "explanation_only", "correctable"] = "correctable"
    participantId: Optional[str] = None
    userAgentId: Optional[str] = None
    customTitle: Optional[str] = None
    customContext: Optional[str] = None  # 회상 인터뷰에서 추출한 초기 쇼핑 맥락


class TurnRequest(BaseModel):
    role: Literal["user", "user_agent"] = "user"
    content: str = Field(min_length=1)


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
