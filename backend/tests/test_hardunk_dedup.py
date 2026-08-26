"""hardUnk 표시 라벨 dedup (2026-08-25 QA — 'lightweight, lightweight').

같은 요구가 칩·스펙 두 통로로 별도 cid를 받아 라벨이 반복되던 결함.
정규화 일치(대소문자·공백·부호 무시)로만 합친다 — 의미 유사도 매칭은 다른
기준을 잘못 합쳐 진짜 미확인 경고를 숨길 수 있어 쓰지 않는다 (tech-debt.md D1).
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_dedup_"), "t.db"))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

import asyncio

from app.agents import response_generator as rg
from app.db import models
from app.products.search import ScoredProduct


class _StubProvider:
    name = "stub"

    def __init__(self, raw):
        self.raw = raw

    async def generate_json(self, *a, **k):
        return self.raw


def _sp(pid):
    return ScoredProduct(
        product=models.Product(id=pid, title=f"상품 {pid}", category="Headphones", price=10000),
        score=1.0, bucket="test",
    )


def _run(raw, criteria):
    ctx = {"scenario": "", "recentUtterances": [], "statedConstraintsNote": "",
           "criteria": criteria}
    return asyncio.run(rg.rerank_by_intent(_StubProvider(raw), [_sp("p0")], ctx))


def test_same_label_two_cids_shown_once():
    """칩 'lightweight' + 스펙 'Lightweight ' — 표기 변형도 한 번만 표시·집계."""
    criteria = [
        {"label": "lightweight", "kind": "constraint", "purchaseOption": False},
        {"label": "Lightweight ", "kind": "constraint", "purchaseOption": False},
    ]
    raw = {"verdicts": [{"index": 0, "cells": {"c1": "unk", "c2": "unk"}}],
           "order": [0], "cards": []}
    _reranked, _cards, _excluded, matrix = _run(raw, criteria)

    note = matrix["hardUnk"]["p0"]
    assert note.count("lightweight") + note.count("Lightweight") == 1, note
    assert sum(1 for k in matrix["hardUnkCounts"]
               if rg._norm_label(k) == "lightweight") == 1
    assert list(matrix["hardUnkCounts"].values()) == [1]


def test_distinct_labels_are_kept_and_capped():
    """다른 기준은 절대 합치지 않는다. 3개 이상이면 2개 + '외 N건'으로 절단."""
    criteria = [
        {"label": "boom microphone", "kind": "constraint", "purchaseOption": False},
        {"label": "aptX codec", "kind": "constraint", "purchaseOption": False},
        {"label": "IP67 waterproof", "kind": "constraint", "purchaseOption": False},
    ]
    raw = {"verdicts": [{"index": 0, "cells": {"c1": "unk", "c2": "unk", "c3": "unk"}}],
           "order": [0], "cards": []}
    _reranked, _cards, _excluded, matrix = _run(raw, criteria)

    note = matrix["hardUnk"]["p0"]
    assert "boom microphone" in note and "aptX codec" in note
    assert "IP67" not in note, "3번째부터는 '외 N건'으로 접힌다"
    assert ("외 1건" in note) or ("and 1 more" in note), note
    # 집계는 절단 없이 전 기준을 센다 (본문 안내·빈손 사유의 재료)
    assert len(matrix["hardUnkCounts"]) == 3


def test_llm_weak_duplicating_code_warning_is_dropped():
    """코드 경고가 명시한 기준을 LLM weak가 자기 말로 반복하면 떨군다 (2026-08-26 QA).
    무관한 caveat(단어 1개 겹침)는 남는다."""
    from app.agents.recommender import merge_near_miss_into_cards

    cards = {"p0": {"reason": "r", "matched": [], "weak": [
        "Material not specified — cannot confirm solid wood",   # 라벨과 단어 2개 겹침 → 드롭
        "Cable management not mentioned — check needed",        # 라벨 포함 → 드롭
        "Wood veneer may scratch easily",                       # 단어 1개(wood)만 → 유지
    ]}}
    near_miss = {"p0": "'solid wood construction, cable management' not confirmed in the listing"}
    unk_labels = {"p0": ["solid wood construction", "cable management"]}
    merge_near_miss_into_cards(cards, near_miss, unk_labels)

    weak = cards["p0"]["weak"]
    assert weak[0].startswith("'solid wood construction")
    assert "Wood veneer may scratch easily" in weak
    assert not any("cannot confirm solid wood" in w for w in weak)
    assert not any("Cable management not mentioned" in w for w in weak)


def test_card_matched_quote_verification():
    """D4 (2026-08-26): matched의 {"text","quote"}는 quote가 후보 원문에 실재해야
    살아남는다 — 지어낸 근거는 드롭, 문자열 항목은 관용 유지(구형·mock)."""
    criteria = [{"label": "white color", "kind": "constraint", "purchaseOption": False}]
    raw = {"verdicts": [{"index": 0, "cells": {}}], "order": [0],
           "cards": [{"index": 0, "reason": "r", "weak": [], "matched": [
               {"text": "27-inch 4K display", "quote": "27-Inch 4K UHD"},     # 원문 존재 → 유지
               {"text": "White color", "quote": "white fabric shade"},        # 원문에 없음 → 드롭
               "legacy string item",                                          # 관용 유지
           ]}]}
    # _run의 상품 제목은 "상품 p0" — 검증 원문에 4K 문구가 있도록 keyAttributes를 주입
    from unittest.mock import patch
    with patch("app.products.profiles.get",
               return_value={"keyAttributes": ["27-Inch 4K UHD IPS panel"], "caveats": []}):
        _reranked, cards, _excluded, _matrix = _run(raw, criteria)
    matched = cards["p0"]["matched"]
    assert "27-inch 4K display" in matched
    assert "legacy string item" in matched
    assert not any("White" in m for m in matched), matched


def test_channel_merge_in_rerank_context():
    """D1 (2026-08-26): 칩과 스펙이 같은 요구를 내면 criteria에 한 항목으로 합쳐지고
    집행은 hard로 승격된다. 다른 요구는 그대로 추가, 가격은 칩에 구조 필드가 있으면 스킵."""
    from types import SimpleNamespace
    from app.agents.recommender import build_rerank_context
    from app.db import models

    policy = SimpleNamespace(
        criteria=[
            {"label": "lightweight over-ear headphones", "kind": "preference",
             "enforcement": "soft"},
            {"label": "budget under $150", "kind": "constraint",
             "enforcement": "hard", "priceMax": 202500},
        ],
        hard_constraints=["lightweight", "IP67 waterproof"],
        price_min=None, price_max=202500,
        constraints_note="",
    )
    session = models.Session(id="s_test", mode="manual", meta={})
    ctx = build_rerank_context(None, session, recent_turns=[], policy=policy)
    labels = [c["label"] for c in ctx["criteria"]]

    assert labels.count("lightweight over-ear headphones") == 1
    assert "lightweight" not in labels, "포함 관계 요구는 칩 항목에 병합돼야 한다"
    merged = next(c for c in ctx["criteria"] if c["label"] == "lightweight over-ear headphones")
    assert merged["enforcement"] == "hard", "스펙이 필수로 본 요구는 hard로 승격"
    assert "IP67 waterproof" in labels, "다른 요구는 그대로 추가"
    assert not any(str(c.get("label", "")).startswith("price ") for c in ctx["criteria"]), \
        "칩에 priceMax가 있으면 스펙 가격 항목을 안 만든다"
