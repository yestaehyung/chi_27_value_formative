"""하이브리드 검색 blend (2026-07-06) — rel = α·lex + (1-α)·cosine.

KGGen(llm_deduplicate.py)의 0.5/0.5 raw 합산은 BM25 스케일 무한계 문제가 있으나,
우리는 두 신호 모두 [0,1]로 정규화돼 있어(text_relevance cap 1.0, cosine) 안전:
- α=0 → 코사인 단독 = 기존 동작과 바이트 동일 (A/B 대조군 보장)
- sim 없음(임베딩 비활성/mock) → 어휘 단독 = 기존 폴백과 동일
"""
from app.products.search import blend_relevance


def test_alpha_zero_is_pure_cosine():
    # 기본값(α=0)에서 기존 동작 보존 — lex가 아무리 높아도 무시
    assert blend_relevance(lex=0.9, sim=0.4, alpha=0.0) == 0.4


def test_alpha_blends_bounded_signals():
    assert abs(blend_relevance(lex=0.8, sim=0.4, alpha=0.5) - 0.6) < 1e-9
    assert abs(blend_relevance(lex=1.0, sim=0.0, alpha=0.3) - 0.3) < 1e-9


def test_no_sim_falls_back_to_lex():
    # 임베딩 비활성(mock/키 없음) 경로 — α와 무관하게 어휘 단독 (기존 폴백 보존)
    assert blend_relevance(lex=0.7, sim=None, alpha=0.5) == 0.7
    assert blend_relevance(lex=0.7, sim=None, alpha=0.0) == 0.7
