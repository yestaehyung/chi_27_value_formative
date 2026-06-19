"""LLM-simulated study participant (spec §12).

The user agent holds ground-truth hidden intentions (never revealed to the
service agent) and reacts to product cues via deterministic trigger rules,
producing utterances, feedback events, and conflict resolutions.
The plan is persona-conditioned so persona × scenario combinations differ.
"""
from dataclasses import dataclass

from app.db import models

LEVEL = {"low": 0, "medium": 1, "high": 2}


@dataclass
class UserAgentStep:
    kind: str  # "utter" | "feedback" | "resolve_conflict" | "stop"
    content: str | None = None
    product_id: str | None = None
    feedback_type: str | None = None
    reason_code: str | None = None
    reason_text: str | None = None
    resolution_action: str | None = None


class UserAgentRunner:
    def __init__(self, profile: dict, scenario: dict):
        self.profile = profile
        self.scenario = scenario
        self.traits = profile.get("traits", {})
        self.script = profile.get("script", {})  # 특이형 persona 오버라이드 (이론모듈 §15.3)
        self.said_price_pref = False
        self.asked_long_term = False
        self.purchased = False

    # ------------------------------------------------------------------
    def initial_utterance(self) -> str:
        return self.script.get("firstUtterance") or self.scenario["initialUserNeed"]

    def price_preference_utterance(self) -> str | None:
        """Second-turn utterance revealing a (possibly conflicting) surface preference."""
        if self.said_price_pref:
            return None
        self.said_price_pref = True
        if self.script.get("secondUtterance"):
            return self.script["secondUtterance"]
        sensitivity = LEVEL.get(self.traits.get("priceSensitivity", "medium"), 1)
        novelty = LEVEL.get(self.traits.get("noveltySeeking", "medium"), 1)
        if novelty >= 2:
            return "흔하지 않고 특별해 보이는 게 좋아요. 예산은 크게 상관없어요."
        if sensitivity >= 1:
            return "예산은 20만원 이하면 좋겠고, 가능하면 저렴한 게 좋아요."
        return "예산은 크게 상관없는데 믿을 수 있는 제품이면 좋겠어요."

    def inquiry_utterance(self) -> str | None:
        if self.asked_long_term:
            return None
        self.asked_long_term = True
        return self.script.get("inquiry") or "추천해주신 것 중에 오래 써도 괜찮을 만한 건 어느 쪽일까요? 한달 사용 리뷰가 궁금해요."

    def _maybe_omit_reason(self, reason_text: str | None) -> str | None:
        """Avoidant persona는 이유를 말하지 않는다 — 행동 신호만 남긴다."""
        if self.profile.get("communicationStyle", {}).get("givesReasons") == "rarely":
            return None
        return reason_text

    # ------------------------------------------------------------------
    def react_to_products(self, products: list[models.Product]) -> list[UserAgentStep]:
        """Apply ground-truth productCueTriggers + persona traits to shown products."""
        steps: list[UserAgentStep] = []
        risk = LEVEL.get(self.traits.get("riskAversion", "medium"), 1)
        sensitivity = LEVEL.get(self.traits.get("priceSensitivity", "medium"), 1)
        novelty = LEVEL.get(self.traits.get("noveltySeeking", "medium"), 1)
        social = self.profile.get("valueOrientation", {}).get("social", 0.5)

        for p in products:
            cue = p.cue_summary or {}
            if cue.get("popularityCue") == "very_popular" and novelty >= 2:
                steps.append(UserAgentStep(
                    kind="feedback", product_id=p.id, feedback_type="dislike",
                    reason_code="too_common",
                    reason_text=self._maybe_omit_reason("너무 흔한 모델이라 선물로는 특별하지 않은 것 같아요."),
                ))
                continue
            if cue.get("priceCue") == "very_low":
                if social >= 0.7:
                    steps.append(UserAgentStep(
                        kind="feedback", product_id=p.id, feedback_type="dislike",
                        reason_code="too_cheap_looking",
                        reason_text=self._maybe_omit_reason("선물인데 너무 저렴해 보이면 좀 그래요."),
                    ))
                    continue
                if sensitivity >= 2:
                    steps.append(UserAgentStep(kind="feedback", product_id=p.id, feedback_type="like"))
                    continue
            if (p.price or 0) > 200000 and sensitivity >= 1:
                steps.append(UserAgentStep(
                    kind="feedback", product_id=p.id, feedback_type="dislike",
                    reason_code="too_expensive",
                    reason_text=self._maybe_omit_reason("선물이지만 20만원이 넘으면 좀 부담돼요."),
                ))
                continue
            if (p.long_term_review_ratio or 0) >= 0.3:
                if risk >= 1:
                    steps.append(UserAgentStep(kind="feedback", product_id=p.id, feedback_type="like",
                                               reason_text=self._maybe_omit_reason("한달 사용 리뷰 비율이 높은 게 마음에 들어요.")))
                else:
                    steps.append(UserAgentStep(kind="feedback", product_id=p.id, feedback_type="view_detail"))
        return steps

    def conflict_resolution_action(self) -> str:
        sensitivity = LEVEL.get(self.traits.get("priceSensitivity", "medium"), 1)
        changes_mind = self.profile.get("communicationStyle", {}).get("changesMind", True)
        if not changes_mind and sensitivity >= 2:
            return "keep_old"
        if sensitivity >= 1:
            return "merge"
        return "accept_new"

    # ------------------------------------------------------------------
    def pick_purchase(self, products: list[models.Product]) -> models.Product | None:
        """Choose the product that best satisfies ground-truth hidden intentions."""
        if not products:
            return None
        sensitivity = LEVEL.get(self.traits.get("priceSensitivity", "medium"), 1)
        novelty = LEVEL.get(self.traits.get("noveltySeeking", "medium"), 1)
        social = self.profile.get("valueOrientation", {}).get("social", 0.5)

        def score(p: models.Product) -> float:
            cue = p.cue_summary or {}
            s = 0.0
            s += (p.long_term_review_ratio or 0) * 2
            if cue.get("sellerCue") == "trusted":
                s += 0.5
            if social >= 0.7 and cue.get("priceCue") == "very_low":
                s -= 2.0
            if sensitivity >= 1 and (p.price or 0) > 200000:
                s -= 1.5
            if sensitivity >= 2:
                s += max(0.0, 1.0 - (p.price or 0) / 200000)
            if novelty >= 2 and cue.get("noveltyCue") == "distinctive":
                s += 0.8
            if novelty >= 2 and cue.get("popularityCue") == "very_popular":
                s -= 1.0
            return s

        return max(products, key=score)

    def purchase_utterance(self, product: models.Product) -> str:
        self.purchased = True
        return f"{product.title}(으)로 할게요."
