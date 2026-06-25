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


def _embed(texts: list[str]) -> list[list[float]] | None:
    if not texts:
        return []
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"model": settings.embedding_model, "input": texts, "dimensions": _DIM},
            )
            resp.raise_for_status()
            return [_normalize(d["embedding"]) for d in resp.json()["data"]]
    except Exception as e:  # noqa: BLE001 — 실패는 키워드 폴백으로 강등
        _log.warning("embedding call failed: %s", e)
        return None


def _product_text(p) -> str:
    """임베딩 텍스트 — BM25 _doc와 정합. 생성 서술(description)·태그·카테고리경로 포함해
    빈약한 제목을 보강한다 (scripts/generate_product_descriptions.py 산출)."""
    tags = " ".join(p.tags or [])
    cat_path = (p.attributes or {}).get("categoryPath", "") if p.attributes else ""
    return f"{p.title or ''} {p.description or ''} {tags} {cat_path} {p.category or ''}".strip()


def ensure_product_vectors(products) -> None:
    """상품 임베딩을 계산해 캐시 (id → 정규화 벡터). 실패 시 다음 호출에서 재시도.

    디스크 캐시(seed_dir/product_vectors.json)는 **증분**이다 — 캐시에 있는 id는 재사용하고
    캐시에 없는 id(새로 추가된 상품)만 임베딩한다. 그래서 풀에 N개를 추가해도 기존 수백 개를
    재임베딩하지 않는다(비파괴 upsert와 짝). 캐시는 현재 상품 id 집합으로 prune해 다시 쓴다."""
    global _loaded
    if _loaded or not enabled():
        return
    import json
    items = [(p.id, _product_text(p)) for p in products]

    cache = settings.seed_dir / "product_vectors.json"
    cached: dict[str, list[float]] = {}
    if cache.exists():
        try:
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
    # 디스크 캐시를 현재 상품 id 집합으로 갱신 (삭제된 id prune, 새 id 포함)
    try:
        cache.write_text(
            json.dumps({pid: _product_vectors[pid] for pid, _ in items if pid in _product_vectors}),
            encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        _log.warning("vector cache write failed: %s", e)


def retrieve(query: str, n: int = 200) -> list[str] | None:
    """임베딩 의미 검색 — query와 코사인 상위 n개 product_id. 비활성/실패/미로드 시 None
    (→ 호출부가 BM25로 폴백). 카테고리 필터는 호출부 책임(인터페이스 단순 유지)."""
    out = retrieve_scored(query, n)
    return None if out is None else [pid for pid, _ in out]


def retrieve_scored(query: str, n: int = 200) -> list[tuple[str, float]] | None:
    """retrieve와 같되 (product_id, 코사인 유사도) 쌍을 반환 — 유사도를 랭킹에 쓰기 위함.
    유사도(의미 적합도)는 최종 점수의 주 신호여야 한다(retrieve 순위가 버려지지 않게)."""
    if not enabled() or not _loaded:
        return None
    qv = query_vector(query)
    if qv is None:
        return None
    scored = [(pid, cosine(qv, v)) for pid, v in _product_vectors.items()]
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:n]


def product_vector(product_id: str) -> list[float] | None:
    return _product_vectors.get(product_id)


def query_vector(text: str) -> list[float] | None:
    if not enabled():
        return None
    vecs = _embed([text])
    return vecs[0] if vecs else None
