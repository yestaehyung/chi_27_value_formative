"""태그 기반 제약 필터 — hard_constraint_match(속성식)의 보완.

사용자가 요구한 태그의 '반대극'만 가진 상품을 제외한다(상호배타쌍 사전 기반).
태그가 없거나 무관하면 소프트 통과(제외 안 함). 가격 등 숫자 제약은 scoring 쪽 유지.
모순쌍은 라벨 vocab(config/tag_taxonomy.json)에 맞춰 작성.
"""
import json

from app.core.config import BACKEND_DIR

_TAX_PATH = BACKEND_DIR / "config" / "tag_taxonomy.json"


def _load_all_tags() -> set[str]:
    try:
        tax = json.loads(_TAX_PATH.read_text(encoding="utf-8"))
        s: set[str] = set()
        for k, v in tax.items():
            if not k.startswith("_") and isinstance(v, list):
                s.update(v)
        return s
    except Exception:  # noqa: BLE001
        return set()


ALL_TAGS = _load_all_tags()

# 상호배타 그룹 — 같은 그룹 내 태그는 동시에 참이기 어렵다.
MUTEX_GROUPS: list[set[str]] = [
    {"유선", "무선"},
    {"반팔", "긴팔"},
    {"남성", "여성", "아동"},
    {"슬림", "오버핏"},
    {"얇음", "두꺼움"},
    {"오픈형", "커널형", "골전도"},
    {"브이넥", "라운드넥", "터틀넥", "하이넥"},
]


def _group_of(tag: str) -> set[str] | None:
    for g in MUTEX_GROUPS:
        if tag in g:
            return g
    return None


def required_tags(query: str) -> list[str]:
    """질의에 등장한 vocab 태그(길이 2+, 1글자 태그는 substring 오탐 위험으로 제외)."""
    q = query or ""
    return [t for t in ALL_TAGS if len(t) >= 2 and t in q]


def tag_constraint_ok(product_tags, required: list[str]) -> bool:
    """요구 태그 r에 대해, 상품이 r의 반대극만 보유(r은 없음)하면 제외."""
    pt = set(product_tags or [])
    for r in required:
        if r in pt:
            continue
        g = _group_of(r)
        if g and (pt & (g - {r})):
            return False
    return True
