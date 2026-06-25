"""예산을 '범위'로 처리한다 (상·하한 둘 다). 버그: '10만원에서 20만원'이
'예산 10만원 이하'로 뭉개져 → 상한 10만으로 역전 → 10-20만 상품이 다 걸러짐.

설계: 언어 이해(범위→숫자)는 LLM(real)/결정론 파서(mock·폴백)가, 적용은 산수만.
가격 제약은 canonical '가격 {min}~{max}원' 형태로 impliedHardConstraint 채널을 탄다.
"""
import pytest

from app.db import models
from app.products.scoring import hard_constraint_match, parse_price_range


def _prod(price):
    return models.Product(id="x", title="t", price=price)


# --- 파서: 언어/canonical → (min, max) ---
def test_parse_range_natural_language():
    assert parse_price_range("10만원에서 20만원 사이") == (100000, 200000)


def test_parse_upper_only():
    assert parse_price_range("20만원 이하") == (None, 200000)


def test_parse_lower_only():
    assert parse_price_range("10만원 이상") == (100000, None)


def test_parse_canonical_form():
    # LLM이 내보낼 정규형
    assert parse_price_range("가격 100000~200000원") == (100000, 200000)
    assert parse_price_range("가격 ~200000원") == (None, 200000)


# --- 적용: 상·하한 둘 다 ---
def test_hard_constraint_enforces_both_bounds():
    c = ["가격 100000~200000원"]
    assert hard_constraint_match(_prod(150000), c) == 1.0   # 범위 안 → 통과
    assert hard_constraint_match(_prod(50000), c) == 0.0    # 하한 미만 → 거부 (버그였던 부분)
    assert hard_constraint_match(_prod(250000), c) == 0.0   # 상한 초과 → 거부


def test_legacy_upper_bound_still_works():
    # 기존 '예산 N만원 이하' 형태는 그대로 상한으로 동작 (하위호환)
    c = ["예산 20만원 이하"]
    assert hard_constraint_match(_prod(150000), c) == 1.0
    assert hard_constraint_match(_prod(250000), c) == 0.0


def test_price_in_range_structured():
    """구조화 예산 필터 — 산수만(문자열 없음)."""
    from app.products.scoring import price_in_range

    assert price_in_range(_prod(150000), 100000, 200000) is True   # 범위 안
    assert price_in_range(_prod(50000), 100000, 200000) is False   # 하한 미만 (버그였던 부분)
    assert price_in_range(_prod(250000), 100000, 200000) is False  # 상한 초과
    assert price_in_range(_prod(None), 100000, 200000) is True     # 가격 미상 → 통과


def test_mock_emits_structured_price_range_end_to_end():
    """코트 버그 재현: '10만원에서 20만원' 발화 → mock이 priceMin/priceMax 숫자로 방출
    (문자열 canonical 아님). 버그 시절엔 '예산 10만원 이하'로 뭉개져 10-20만이 다 걸러졌음."""
    from app.llm import mock_rules

    ctx = {
        "turns": [{"id": "t1", "role": "user", "content": "10만원에서 20만원 사이 코트 추천해줘"}],
        "feedback": [],
        "state": {"activeTopicLabels": []},
    }
    out = mock_rules.TASK_HANDLERS["topic_extraction"](ctx)
    price_topics = [
        t for t in out.get("topics", [])
        if t.get("priceMin") is not None or t.get("priceMax") is not None
    ]
    assert price_topics, f"가격 토픽이 추출되지 않음. topics={out.get('topics')}"
    t = price_topics[0]
    assert t["priceMin"] == 100000 and t["priceMax"] == 200000, f"범위 손실: {t}"
