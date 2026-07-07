"""② exclude 채널 + 부분 정직 경로 (2026-07-07, 설계 결정: 버뮤다 진단 후속).

계약:
- rerank LLM은 제약 위반 후보에 exclude:true + 한 줄 이유를 표기할 수 있다 (판단 출력).
- 파싱은 명시 플래그만 제외로 인정 — ranking 누락은 append-back으로 살아남고 제외가 아니다.
- 노출: 준수 후보 [:top_k], 5개 미만이면 그만큼만. 전부 제외면 근접 대안 상위 3개를
  nearMiss로 노출하고, 그 사실(무엇이 다른지 포함)을 렌더러가 정직하게 고지한다.
- mock rerank는 exclude를 내지 않음 → 기존 데모/테스트 경로 무영향.
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


class _StubProvider:
    """exclude 플래그가 섞인 rerank 출력을 내는 스텁 (index 2는 일부러 누락)."""
    name = "stub"

    async def generate_json(self, messages, task, context=None, **kwargs):
        return {"ranking": [
            {"index": 1, "reason": "조건 부합", "matched": ["가격대 적정"], "weak": []},
            {"index": 0, "exclude": True, "excludeReason": "여성용이라 남성용 요청과 다름",
             "reason": "가장 가까운 대안", "matched": [], "weak": []},
        ]}


def test_rerank_parses_explicit_exclude_only():
    scored = [_sp("p0"), _sp("p1"), _sp("p2")]
    reranked, cards, excluded = asyncio.run(
        rg.rerank_by_intent(_StubProvider(), scored, {"recentUtterances": []})
    )
    # 순위: LLM이 매긴 1,0 + 누락된 2는 append-back
    assert [sp.product.id for sp in reranked] == ["p1", "p0", "p2"]
    # 제외는 명시 플래그만 — 누락(p2)은 제외가 아니다
    assert excluded == {"p0": "여성용이라 남성용 요청과 다름"}
    assert "p2" not in excluded
    # 제외 후보도 카드텍스트는 가진다 (근접 대안으로 노출될 수 있으므로)
    assert cards["p0"]["reason"]


def test_rerank_mock_path_excludes_nothing():
    """mock/실패 폴백 — exclude 없는 출력이면 excluded는 빈 dict (기존 경로 무영향)."""
    class _Plain:
        name = "stub"

        async def generate_json(self, messages, task, context=None, **kwargs):
            return {"ranking": [{"index": 0, "reason": "r", "matched": [], "weak": []}]}

    scored = [_sp("a"), _sp("b")]
    _, _, excluded = asyncio.run(rg.rerank_by_intent(_Plain(), scored, {}))
    assert excluded == {}


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


def test_select_shown_all_excluded_returns_near_misses():
    """전부 위반이면 근접 대안 상위 3개 + 이유가 nearMiss로 나온다 (부분 정직)."""
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
    # 중복 병합 안전
    merge_near_miss_into_cards(cards, {"p0": "여성용임"})
    assert cards["p0"]["weak"].count("여성용임") == 1


def test_near_miss_text_is_honest_and_asks():
    """결정론 폴백(=mock 출력)도 정직 고지 + 조건 완화 질문을 담는다."""
    shown = [_sp("p0"), _sp("p1")]
    text = rg.near_miss_text(shown)
    assert "찾지 못했" in text or "없" in text          # 정확히 맞는 상품 부재 고지
    assert "?" in text                                   # 다음 행동을 사용자에게 묻는다
    assert "2" in text                                   # 보여주는 개수 언급


def test_no_result_text_exists():
    text = rg.near_miss_text([])
    assert ("찾지 못했" in text or "없" in text) and "?" in text
