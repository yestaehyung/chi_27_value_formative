"""구매 옵션 속성의 unk 배제 면제 (2026-08-18).

의류 사이즈처럼 구매 시 선택하는 옵션은 리스팅에 명시되지 않는 게 정상이다 —
"사이즈 L 필수"가 hard 기준이 되면 전 후보가 '확인 불가'로 몰살당한다
(파일럿 실측: 바지 4턴 연속 빈손, 30개 중 26개가 사이즈 unk로 차단).
purchaseOption=True인 기준의 unk 셀은 배제 사유에서 제외하고,
상품 고유 속성(IP67 등)의 unk는 기존대로 엄격하게 차단한다.
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_opt_"), "t.db"))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

import asyncio

from app.agents import response_generator as rg
from app.agents.recommender import select_shown
from app.db import models
from app.products.search import ScoredProduct


class _StubProvider:
    """rerank 행렬을 고정 반환하는 스텁 — 판정 셀의 구조적 귀결만 검증한다."""

    name = "stub"

    def __init__(self, raw):
        self.raw = raw

    async def generate_json(self, *a, **k):
        return self.raw


def _sp(pid):
    return ScoredProduct(
        product=models.Product(id=pid, title=f"상품 {pid}", category="Pants", price=10000),
        score=1.0, bucket="test",
    )


def _run(raw, criteria):
    scored = [_sp("p0"), _sp("p1")]
    ctx = {"scenario": "", "recentUtterances": [], "statedConstraintsNote": "",
           "criteria": criteria}
    return asyncio.run(rg.rerank_by_intent(_StubProvider(raw), scored, ctx))


def test_option_attribute_unk_is_not_blocking():
    """사이즈(purchaseOption) unk → 차단 없음 / 고유 속성(IP67) unk → 차단."""
    criteria = [
        {"label": "size L", "kind": "constraint", "purchaseOption": True},
        {"label": "IP67 waterproof", "kind": "constraint", "purchaseOption": False},
    ]
    raw = {"verdicts": [
        {"index": 0, "cells": {"c1": "unk"}},          # 사이즈만 확인 불가 → 통과해야 함
        {"index": 1, "cells": {"c2": "unk"}},          # 방수 등급 확인 불가 → 차단돼야 함
    ], "order": [0, 1], "cards": []}
    reranked, _cards, excluded, matrix = _run(raw, criteria)

    assert "p0" not in matrix["hardUnk"], "구매 옵션 unk가 차단 사유가 되면 안 된다"
    assert "p1" in matrix["hardUnk"], "고유 속성 unk는 기존대로 차단된다"

    shown, near_miss = select_shown(reranked, excluded, top_k=5,
                                    hard_unk=matrix["hardUnk"])
    assert [sp.product.id for sp in shown] == ["p0"]
    assert near_miss == {}


def test_option_attribute_vio_still_excludes():
    """옵션 속성이라도 명시적 위반(vio)은 배제된다 — 면제는 unk에만 적용."""
    criteria = [{"label": "size L", "kind": "constraint", "purchaseOption": True}]
    raw = {"verdicts": [
        {"index": 0, "cells": {"c1": "vio"}, "vioNote": "size XL only"},
        {"index": 1, "cells": {}},
    ], "order": [1, 0], "cards": []}
    reranked, _cards, excluded, matrix = _run(raw, criteria)

    assert "p0" in excluded
    shown, near_miss = select_shown(reranked, excluded, top_k=5,
                                    hard_unk=matrix["hardUnk"])
    assert [sp.product.id for sp in shown] == ["p1"]
    assert near_miss == {}
