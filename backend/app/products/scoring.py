"""Product scoring (spec §14.2) + hidden-intention fit rules + rationale strings."""
from app.db import models

PRICE_CUE_ORDER = ["very_low", "low", "mid", "high", "very_high"]


def _char_bigrams(s: str) -> set[str]:
    s = "".join(ch for ch in s if ch.isalnum())
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else set()


def text_relevance(product: models.Product, query: str) -> float:
    """토큰 일치 + 문자 bigram 겹침(한국어 조사/띄어쓰기 변형에 강건)."""
    if not query:
        return 0.5
    hay = f"{product.title} {product.category or ''} {product.brand or ''} {product.description or ''}"
    tokens = [t for t in query.replace(",", " ").split() if len(t) >= 2]
    token_score = (sum(1 for t in tokens if t in hay) / len(tokens)) if tokens else 0.0
    qb, hb = _char_bigrams(query), _char_bigrams(hay)
    bigram_score = len(qb & hb) / len(qb) if qb else 0.0
    base = max(token_score, bigram_score * 0.85)
    if product.category and product.category in query:
        base = max(base, 0.9)
    return min(base + 0.1, 1.0)


def parse_budget_won(text: str) -> int | None:
    """예산 표현 파싱: 'N만원', 'N만 원', 'N십만원', 'N원'(4자리 이상), 'N만원대'."""
    import re

    m = re.search(r"(\d+(?:\.\d+)?)\s*십\s*만\s*원", text)
    if m:
        return int(float(m.group(1)) * 100000)
    m = re.search(r"(\d+(?:\.\d+)?)\s*만\s*원", text)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"(\d{4,})\s*원", text.replace(",", ""))
    if m:
        return int(m.group(1))
    return None


def parse_price_range(text: str) -> tuple[int | None, int | None]:
    """가격 표현 → (min_won, max_won). 한쪽은 None(무제한) 가능.

    실제 경로는 LLM이 범위를 canonical '가격 {min}~{max}원'으로 추출하고, 이 함수는
    그 정규형(및 일부 자연어)을 숫자로 되읽는다. 자연어 파싱은 mock·LLM 누락 시 폴백 —
    한국어 표현을 전부 커버하려 들지 않는다(그건 LLM 몫). 산수 적용은 호출부에서.
    """
    import re

    t = text.replace(",", "")
    # 1) canonical bare-won range: '100000~200000' / '~200000' / '100000~'
    m = re.search(r"(\d{4,})\s*~\s*(\d{4,})", t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b))
    m = re.search(r"~\s*(\d{4,})", t)
    if m:
        return (None, int(m.group(1)))
    m = re.search(r"(\d{4,})\s*~", t)
    if m:
        return (int(m.group(1)), None)
    # 2) 자연어 폴백 (만원/십만원)
    won = [int(float(v) * 100000) for v in re.findall(r"(\d+(?:\.\d+)?)\s*십\s*만\s*원", t)]
    if not won:
        won = [int(float(v) * 10000) for v in re.findall(r"(\d+(?:\.\d+)?)\s*만\s*원", t)]
    if not won:
        won = [int(v) for v in re.findall(r"(\d{4,})\s*원", t)]
    if not won:
        return (None, None)
    if len(won) >= 2:
        return (min(won), max(won))
    n = won[0]
    if any(k in t for k in ("이상", "초과", "넘")):
        return (n, None)
    return (None, n)


def price_in_range(product: models.Product, price_min: int | None, price_max: int | None) -> bool:
    """구조화 예산 필터 — 산수만(문자열 파싱 없음). 가격 미상 상품은 통과(데이터 없음으로 배제 안 함)."""
    if product.price is None:
        return True
    if price_min is not None and product.price < price_min:
        return False
    if price_max is not None and product.price > price_max:
        return False
    return True


def hard_constraint_match(product: models.Product, hard_constraints: list[str]) -> float:
    """1.0 if all known constraints pass, 0.0 if a known constraint fails."""
    attrs = product.attributes or {}
    for c in hard_constraints:
        if "운동" in c and not (attrs.get("gps") or attrs.get("style") in ("sport", "performance") or attrs.get("heartRate")):
            return 0.0
        if "방수" in c and not attrs.get("waterproof"):
            return 0.0
        # 예산/가격 — 범위(min~max) 둘 다 적용. 언어→숫자는 LLM/parse_price_range가, 여기선 산수만.
        if ("예산" in c or "가격" in c) and product.price is not None:
            lo, hi = parse_price_range(c)
            if lo is not None and product.price < lo:
                return 0.0
            if hi is not None and product.price > hi:
                return 0.0
    return 1.0


def compute_product_score(product: models.Product, query: str, text_rel: float | None = None) -> float:
    """랭킹 점수 = 질의 적합도(임베딩 유사도 우선; 없으면 키워드 적합도).

    2026-07-01: 추천 랭킹은 의도적으로 value-blind — 가치·의도 매칭(옛 hidden_intention_fit,
    §14.2의 soft/fit 항)은 제거했다. priceCue·rating 같은 상품 표면 cue를 손으로 짠 if로
    가치인 척 매핑하던 코드였고, 데모 문구에 튜닝돼 아마존 자유발화엔 대부분 죽어 있었다.
    가치·동기는 추천을 강제하지 않고 피드백에서 passive하게 추론한다(recommend-first,
    passive detection). 카드의 ✓/~ 문구는 rerank_by_intent(LLM)가 생성한다.
    """
    return text_rel if text_rel is not None else text_relevance(product, query)
