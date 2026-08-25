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
