"""rerank 판정 행렬 + 빈손 우선 노출 (2026-08-15 — categorical-over-scalar를 rerank에 적용).

계약:
- rerank LLM은 후보×기준 판정 행렬(verdicts)을 먼저 내고, 순위(order)·카드(cards)는
  행렬에서 유도한다. 코드는 기준 내용을 모른다 — 행렬의 구조적 귀결만 집행한다:
  hard 기준(constraint·avoidance·"note")의 "vio" 셀 → 노출 배제.
  preference·context의 "vio"와 "unk"는 배제가 아니다.
- 노출: 준수 후보 [:top_k], 미만이면 그만큼만. 준수 0이면 **기본은 빈손**(카드 없음 +
  렌더러가 걸린 기준 설명). 근접 대안 3개는 사용자가 요청했을 때만(nearMissRequested).
- 구 스키마("ranking" + 명시 exclude)는 폴백으로 계속 파싱한다.
- mock rerank는 위반을 내지 않음 → 기존 데모/테스트 경로 무영향.
"""
import asyncio

from app.agents import response_generator as rg
from app.agents.recommender import merge_near_miss_into_cards, select_shown
from app.products.search import ScoredProduct


class _P:
    def __init__(self, pid, title=None):
        self.id = pid
        self.title = title or pid
        self.category = "반바지"
        self.price = 10000
        self.rating = 4.0
        self.review_count = 10
        self.long_term_review_ratio = 0.1
        self.cue_summary = {}
        self.description = ""


def _sp(pid):
    return ScoredProduct(product=_P(pid), score=1.0)


CRITERIA = [
    {"label": "최소 16GB 램", "kind": "constraint", "mustHave": "최소 16GB 램"},   # → c1 (hard)
    {"label": "화려한 디자인 피하기", "kind": "avoidance"},                        # → c2 (hard)
    {"label": "부드러운 촉감", "kind": "preference"},                              # → c3 (soft)
]


class _MatrixStub:
    """행렬 스키마 출력 스텁 — p0: hard 위반, p1: soft만 위반, p2: unk만."""
    name = "stub"

    async def generate_json(self, messages, task, context=None, **kwargs):
        return {
            "verdicts": [
                {"index": 0, "cells": {"c1": "vio", "c2": "ok", "c3": "ok"},
                 "vioNote": "8GB 램 — 16GB 미만"},
                {"index": 1, "cells": {"c1": "ok", "c2": "ok", "c3": "vio"}},
                {"index": 2, "cells": {"c1": "unk", "c2": "ok", "c3": "ok"}},
            ],
            # LLM이 위반 후보(p0)를 1위로 놓아도 노출은 구조 가드가 거른다
            "order": [0, 1, 2],
            "cards": [{"index": 0, "reason": "가장 가까운 대안", "matched": [], "weak": []},
                      {"index": 1, "reason": "조건 부합", "matched": ["16GB 램"], "weak": []}],
            "nearMissRequested": False,
        }


def _run_matrix_stub():
    scored = [_sp("p0"), _sp("p1"), _sp("p2")]
    return asyncio.run(rg.rerank_by_intent(
        _MatrixStub(), scored,
        {"recentUtterances": [], "criteria": CRITERIA, "statedConstraintsNote": ""},
    ))


def test_matrix_hard_vio_excludes_soft_and_unk_do_not():
    reranked, cards, excluded, matrix = _run_matrix_stub()
    assert excluded == {"p0": "8GB 램 — 16GB 미만"}      # hard vio만 배제
    assert "p1" not in excluded                          # preference vio → 배제 아님
    assert "p2" not in excluded                          # unk → 배제 아님
    assert matrix["vioCounts"] == {"최소 16GB 램": 1}


def test_matrix_violator_never_shown_even_if_llm_ranks_it_first():
    """LLM이 자기 행렬과 모순되게 위반 후보를 1위로 놓아도 노출에서 걸러진다."""
    reranked, cards, excluded, matrix = _run_matrix_stub()
    assert [sp.product.id for sp in reranked] == ["p0", "p1", "p2"]  # 순위 자체는 LLM 것
    shown, near_miss = select_shown(reranked, excluded, top_k=5)
    assert [sp.product.id for sp in shown] == ["p1", "p2"]           # p0은 구조적으로 배제
    assert near_miss == {}


def test_matrix_missing_card_gets_fallback():
    _, cards, _, _ = _run_matrix_stub()
    assert cards["p2"]["reason"]  # cards에 없던 후보도 폴백 카드가 채워진다


def test_unverified_criteria_aggregates_unk_over_shown():
    """노출 셋에서 unk로 남은 기준이 라벨 기준으로 집계된다 (확인 불가 고지의 재료)."""
    from app.agents.recommender import unverified_criteria

    reranked, cards, excluded, matrix = _run_matrix_stub()
    assert matrix["criterionLabels"]["c1"] == "최소 16GB 램"
    shown, _ = select_shown(reranked, excluded, top_k=5)
    unv = unverified_criteria(matrix, [sp.product.id for sp in shown])
    # p2만 c1이 unk — 노출 2개(p1, p2) 중 1개에서 '최소 16GB 램' 확인 불가
    assert unv == {"최소 16GB 램": 1}
    # 배제된 후보(p0)의 셀은 집계에 들어가지 않는다
    unv_all_excluded = unverified_criteria(matrix, [])
    assert unv_all_excluded == {}


def test_legacy_ranking_schema_still_parses():
    """구 스키마 폴백 — 명시 exclude:true만 제외, 누락은 append-back (제외 아님)."""
    class _Legacy:
        name = "stub"

        async def generate_json(self, messages, task, context=None, **kwargs):
            return {"ranking": [
                {"index": 1, "reason": "조건 부합", "matched": [], "weak": []},
                {"index": 0, "exclude": True, "excludeReason": "여성용",
                 "reason": "가장 가까운 대안", "matched": [], "weak": []},
            ]}

    scored = [_sp("p0"), _sp("p1"), _sp("p2")]
    reranked, cards, excluded, _ = asyncio.run(
        rg.rerank_by_intent(_Legacy(), scored, {"recentUtterances": []}))
    assert [sp.product.id for sp in reranked] == ["p1", "p0", "p2"]
    assert excluded == {"p0": "여성용"}
    assert "p2" not in excluded


def test_rerank_mock_path_excludes_nothing():
    """mock/실패 폴백 — 위반 없는 출력이면 excluded는 빈 dict (기존 경로 무영향)."""
    class _Plain:
        name = "stub"

        async def generate_json(self, messages, task, context=None, **kwargs):
            return {"verdicts": [], "order": [0], "cards": [
                {"index": 0, "reason": "r", "matched": [], "weak": []}]}

    scored = [_sp("a"), _sp("b")]
    _, _, excluded, matrix = asyncio.run(rg.rerank_by_intent(_Plain(), scored, {}))
    assert excluded == {}
    assert matrix["nearMissRequested"] is False


def test_select_shown_full_compliance():
    reranked = [_sp(f"p{i}") for i in range(6)]
    shown, near_miss = select_shown(reranked, excluded={}, top_k=5)
    assert [sp.product.id for sp in shown] == ["p0", "p1", "p2", "p3", "p4"]
    assert near_miss == {}


def test_select_shown_partial_pool_shows_fewer_not_filled():
    """준수 후보가 top_k 미만이면 그만큼만 — 위반품으로 채우지 않는다."""
    reranked = [_sp(f"p{i}") for i in range(6)]
    excluded = {f"p{i}": "위반" for i in (0, 2, 3, 5)}
    shown, near_miss = select_shown(reranked, excluded, top_k=5)
    assert [sp.product.id for sp in shown] == ["p1", "p4"]
    assert near_miss == {}


def test_select_shown_all_excluded_shows_near_miss_by_default():
    """전부 위반이면 근접 대안 3개를 **기본으로** 사유와 함께 노출한다 (2026-08-18 개정 —
    파일럿에서 opt-in은 빈손 11회 중 2회만 사용됐고 나머지는 과제 포기로 이어졌다).
    부재 고지("다 맞는 상품은 없다")는 렌더러(near_miss_text)가 유지한다."""
    reranked = [_sp(f"p{i}") for i in range(6)]
    excluded = {f"p{i}": f"이유{i}" for i in range(6)}
    shown, near_miss = select_shown(reranked, excluded, top_k=5)
    assert [sp.product.id for sp in shown] == ["p0", "p1", "p2"]
    assert near_miss == {"p0": "이유0", "p1": "이유1", "p2": "이유2"}


def test_select_shown_empty_pool():
    shown, near_miss = select_shown([], {}, top_k=5)
    assert shown == [] and near_miss == {}


def test_merge_near_miss_reason_lands_in_card_weak():
    """근접 대안 카드의 weak 첫 항목 = 요청과 다른 점 (카드 수준 고지)."""
    cards = {"p0": {"reason": "가장 가까운 대안", "matched": ["소재 좋음"], "weak": ["가격대 높음"]}}
    merge_near_miss_into_cards(cards, {"p0": "여성용임"})
    assert cards["p0"]["weak"][0] == "여성용임"
    assert "가격대 높음" in cards["p0"]["weak"]
    merge_near_miss_into_cards(cards, {"p0": "여성용임"})
    assert cards["p0"]["weak"].count("여성용임") == 1


def test_empty_handed_text_names_blocking_criterion():
    text = rg.empty_handed_text(["최소 16GB 램"])
    assert "찾지 못했" in text
    assert "최소 16GB 램" in text     # 어떤 기준이 걸렸는지 밝힌다
    assert "?" in text                 # 다음 방향은 사용자가 고른다
    assert "가까운" in text            # 근접 후보 opt-in 제안


def test_near_miss_text_is_honest_and_asks():
    shown = [_sp("p0"), _sp("p1")]
    text = rg.near_miss_text(shown)
    assert "찾지 못했" in text or "없" in text
    assert "?" in text
    assert "2" in text


def test_no_result_text_exists():
    text = rg.near_miss_text([])
    assert ("찾지 못했" in text or "없" in text) and "?" in text
