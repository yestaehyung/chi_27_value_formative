"""상품 프로필 로더 — 오프라인 LLM enrichment 산출물(seed_dir/product_profiles.json)을
id-키로 읽기 전용 제공 (설계: docs/plans/2026-07-02-three-agent-crs-redesign.md 후속,
기법 근거: ONCE WSDM'24 / LLM-Rec NAACL'24 — LLM 아이템 콘텐츠 증강).

프로필 = {profile(한 문단), productType, audience, keyAttributes[], caveats[]}.
scripts/build_product_profiles.py가 생성·증분 갱신한다. 파일이 없는 풀(seed/,
seed_naver/)에서는 모든 조회가 None → 호출부는 기존 텍스트(raw description)로 폴백.
런타임 비용 0 (시작 시 1회 로드, 조회만)."""
import json
import logging

from app.core.config import settings

_log = logging.getLogger(__name__)
_cache: dict[str, dict] | None = None


def _load() -> dict[str, dict]:
    global _cache
    if _cache is None:
        path = settings.seed_dir / "product_profiles.json"
        _cache = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                _cache = {pid: prof for pid, prof in raw.items() if isinstance(prof, dict)}
                _log.info("product profiles loaded: %d (%s)", len(_cache), path)
            except Exception as e:  # noqa: BLE001
                _log.warning("product profile load failed: %s", e)
    return _cache


def get(product_id: str) -> dict | None:
    return _load().get(product_id)


def reset() -> None:
    """테스트/재빌드용 — 다음 조회 때 다시 로드."""
    global _cache
    _cache = None
