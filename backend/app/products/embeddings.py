"""의미 기반(임베딩) 상품 검색 — 키워드 적합도를 보완하는 하이브리드용.

DeepSeek는 임베딩 API가 없으므로, chat provider와 무관하게 항상 OpenAI
text-embedding-3-small을 직접 호출한다(httpx — provider.py와 동일 패턴).
provider가 mock이거나 OPENAI_API_KEY가 없으면 비활성 → 키워드 폴백.
(테스트는 mock으로 돌므로 외부 호출이 일어나지 않는다.)

상품 벡터는 프로세스당 1회 계산해 메모리에 캐시한다(600개 규모 → 벡터DB 불필요,
순수 파이썬 코사인으로 충분). 호출/실패는 graceful — 실패 시 키워드로 강등.
"""
from __future__ import annotations

import logging
import math

import httpx

from app.core.config import settings

_log = logging.getLogger("embeddings")
_DIM = 1536  # text-embedding-3-small 전체 차원 (품질 우선)

_product_vectors: dict[str, list[float]] = {}
_loaded = False


def enabled() -> bool:
    """mock provider이거나 키가 없으면 비활성 (테스트·오프라인 안전)."""
    return settings.llm_provider != "mock" and bool(settings.openai_api_key)


def loaded() -> bool:
    return _loaded


def _normalize(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def cosine(a: list[float], b: list[float]) -> float:
    """벡터는 저장 시 정규화 → 내적이 곧 코사인 (0~1 부근)."""
    return sum(x * y for x, y in zip(a, b))


_EMBED_BATCH = 500  # OpenAI 한도: 요청당 입력 2,048개 — 대량 증분(수천 개) 시 청크 필수 (2026-07-04)

# 재사용 클라이언트 — 매 턴의 쿼리 임베딩이 TLS 핸드셰이크를 새로 하지 않게 (2026-08-14).
# httpx.Client는 요청 단위 thread-safe라 uvicorn 워커 안에서 공유해도 된다.
_client: httpx.Client | None = None


def _http_client() -> httpx.Client:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.Client(timeout=120)
    return _client


def _embed(texts: list[str]) -> list[list[float]] | None:
    if not texts:
        return []
    out: list[list[float]] = []
    try:
        client = _http_client()
        for i in range(0, len(texts), _EMBED_BATCH):
            chunk = texts[i:i + _EMBED_BATCH]
            resp = client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"model": settings.embedding_model, "input": chunk, "dimensions": _DIM},
            )
            resp.raise_for_status()
            out.extend(_normalize(d["embedding"]) for d in resp.json()["data"])
            if len(texts) > _EMBED_BATCH:
                _log.info("embedded %d/%d", len(out), len(texts))
        return out
    except Exception as e:  # noqa: BLE001 — 실패는 키워드 폴백으로 강등
        _log.warning("embedding call failed: %s", e)
        return None


def _product_text(p) -> str:
    """임베딩 텍스트 — BM25 _doc와 정합.

    프로필(product_profiles.json, 오프라인 LLM enrichment)이 있으면 **정체성 필드만**으로
    구성 — title/titleFull/productType/keyAttributes/audience/category. 프로필 산문(profile)은
    의도적으로 제외한다: 산문의 용도 서술("여행·출퇴근에 적합")이 카테고리를 넘어 공명해
    "여행용 가벼운 노트북" 쿼리에 이어폰을 끌어오는 누수를 만들었다(2026-07-02 진단 —
    retrieval은 정체가 지배해야 하고, 용도 적합은 rerank가 판단한다). 프로필이 없는 풀
    (seed/, seed_naver/)은 기존 구성 유지 — 그 풀들의 벡터 캐시가 계속 유효하다.
    ※ 구성 변경 시 해당 seed의 product_vectors.json을 지우고 재임베딩할 것 (캐시는 id-키)."""
    from app.products import profiles

    attrs = p.attributes or {}
    prof = profiles.get(p.id)
    if prof:
        parts = [
            p.category or "", prof.get("productType") or "",
            p.title or "", attrs.get("titleFull") or "",
            " ".join(prof.get("keyAttributes") or []), prof.get("audience") or "",
        ]
        return " ".join(s for s in parts if s).strip()
    tags = " ".join(p.tags or [])
    cat_path = attrs.get("categoryPath", "")
    return f"{p.title or ''} {p.description or ''} {tags} {cat_path} {p.category or ''}".strip()


def ensure_product_vectors(products) -> None:
    """상품 임베딩을 계산해 캐시 (id → 정규화 벡터). 실패 시 다음 호출에서 재시도.

    디스크 캐시(seed_dir/product_vectors.json)는 **증분**이다 — 캐시에 있는 id는 재사용하고
    캐시에 없는 id(새로 추가된 상품)만 임베딩한다. 그래서 풀에 N개를 추가해도 기존 수백 개를
    재임베딩하지 않는다(비파괴 upsert와 짝). 캐시는 현재 상품 id 집합으로 prune해 다시 쓴다."""
    global _loaded
    if _loaded or not enabled():
        return
    import gzip
    import json
    items = [(p.id, _product_text(p)) for p in products]

    # 캐시 파일: .json.gz 우선(2026-07-04 — 풀 6천+ 규모에서 평문 JSON이 GitHub 단일
    # 파일 한도 100MB를 넘어 gzip+6자리 반올림으로 전환), 없으면 legacy .json 폴백
    # (seed/·seed_naver 기존 캐시 유효 유지).
    cache_gz = settings.seed_dir / "product_vectors.json.gz"
    cache = settings.seed_dir / "product_vectors.json"
    cached: dict[str, list[float]] = {}
    loaded_from_gzip = False
    try:
        if cache_gz.exists():
            cached = json.loads(gzip.decompress(cache_gz.read_bytes()).decode("utf-8"))
            loaded_from_gzip = True
        elif cache.exists():
            cached = json.loads(cache.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        _log.warning("vector cache read failed: %s", e)
    # 캐시에 있는 현재 상품 벡터는 그대로 재사용
    _product_vectors.update({pid: cached[pid] for pid, _ in items if pid in cached})
    # 캐시에 없는 id만 임베딩 (증분 — 새 상품만)
    missing = [(pid, txt) for pid, txt in items if pid not in cached]
    if missing:
        vecs = _embed([t for _, t in missing])
        if vecs is None:
            return  # 실패 — _loaded 유지 안 함, 다음 호출에서 재시도
        _product_vectors.update({pid: v for (pid, _), v in zip(missing, vecs)})
        _log.info("embedded %d new product vectors (%d reused from cache)",
                  len(missing), len(items) - len(missing))
    else:
        _log.info("product vectors loaded from disk cache (%d)", len(items))
    _loaded = True
    # 디스크 캐시를 현재 상품 id 집합으로 갱신 (삭제된 id prune, 새 id 포함).
    # 6자리 반올림(유사도 오차 ~1e-6) + gzip — 항상 .json.gz로 쓴다.
    # 완전히 일치하는 gzip 캐시는 다시 쓰지 않는다. gzip 헤더 시각만 바뀌어도 버전드
    # 시드의 vectorCacheSha256가 깨지고, 200MB 캐시를 매 기동마다 재압축하게 된다.
    current_ids = {pid for pid, _ in items}
    cache_needs_write = bool(missing) or set(cached) != current_ids or not loaded_from_gzip
    if not cache_needs_write:
        return
    try:
        payload = {pid: [round(x, 6) for x in _product_vectors[pid]]
                   for pid, _ in items if pid in _product_vectors}
        cache_gz.write_bytes(gzip.compress(json.dumps(payload).encode("utf-8"), compresslevel=6))
    except Exception as e:  # noqa: BLE001
        _log.warning("vector cache write failed: %s", e)


def retrieve(query: str, n: int = 200) -> list[str] | None:
    """임베딩 의미 검색 — query와 코사인 상위 n개 product_id. 비활성/실패/미로드 시 None
    (→ 호출부가 BM25로 폴백). 카테고리 필터는 호출부 책임(인터페이스 단순 유지)."""
    out = retrieve_scored(query, n)
    return None if out is None else [pid for pid, _ in out]


def retrieve_scored(query: str, n: int = 200,
                    include_ids: set[str] | None = None) -> list[tuple[str, float]] | None:
    """retrieve와 같되 (product_id, 코사인 유사도) 쌍을 반환 — 유사도를 랭킹에 쓰기 위함.
    유사도(의미 적합도)는 최종 점수의 주 신호여야 한다(retrieve 순위가 버려지지 않게).

    include_ids(하이브리드 union용, 2026-07-06): BM25가 올린 후보처럼 top-n 밖이어도
    유사도가 필요한 id들 — 전 상품 스캔은 어차피 하므로 쿼리 임베딩 추가 호출 없이
    top-n 뒤에 붙여 반환한다."""
    if not enabled() or not _loaded:
        return None
    qv = query_vector(query)
    if qv is None:
        return None
    scored = [(pid, cosine(qv, v)) for pid, v in _product_vectors.items()]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:n]
    if include_ids:
        have = {pid for pid, _ in top}
        top += [(pid, s) for pid, s in scored[n:] if pid in include_ids and pid not in have]
    return top


def product_vector(product_id: str) -> list[float] | None:
    return _product_vectors.get(product_id)


def query_vector(text: str) -> list[float] | None:
    if not enabled():
        return None
    vecs = _embed([text])
    return vecs[0] if vecs else None
