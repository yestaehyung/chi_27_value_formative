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


def ensure_product_vectors(products) -> None:
    """상품 임베딩을 1회 계산해 캐시 (id → 정규화 벡터). 실패 시 다음 호출에서 재시도."""
    global _loaded
    if _loaded or not enabled():
        return
    items = [(p.id, f"{p.title} {p.category or ''} {p.brand or ''}".strip()) for p in products]
    vecs = _embed([t for _, t in items])
    if vecs is None:
        return
    _product_vectors.update({pid: v for (pid, _), v in zip(items, vecs)})
    _loaded = True


def product_vector(product_id: str) -> list[float] | None:
    return _product_vectors.get(product_id)


def query_vector(text: str) -> list[float] | None:
    if not enabled():
        return None
    vecs = _embed([text])
    return vecs[0] if vecs else None
