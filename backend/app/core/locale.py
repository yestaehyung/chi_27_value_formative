"""참가자 화면 언어 (VC_STUDY_LOCALE: ko | en).

백엔드가 만드는 참가자 대면 텍스트의 언어를 결정한다 — LLM 산출물(칩 라벨·응답·
답변칩·충돌 카드·카드 이유)은 프롬프트 지시 주입으로(prompts.EN_DIRECTIVES),
결정론 템플릿·폴백은 L(ko, en)으로 전환한다.

연구 로그와 kind 같은 내부 계약은 언어와 무관하게 유지된다. searchText는 검색
인덱스와 같은 언어여야 하므로 영어 스터디에서는 영어 전용 시드와 함께 영어로 쓴다.
"""
from app.core.config import settings


def is_en() -> bool:
    return settings.study_locale == "en"


def L(ko: str, en: str) -> str:
    """참가자 대면 문자열의 로케일 선택 (프론트 studyI18n.tr()의 백엔드 판)."""
    return en if is_en() else ko


# seed_ms_v2 가격은 USD 원가 × 1350으로 빌드됨 (scripts/build_staged_amazon_catalog.py
# DEFAULT_USDKRW). 표시·프롬프트가 같은 환율로 역산해야 예산 해석이 어긋나지 않는다.
# 프론트 studyI18n.formatStudyPrice의 KRW_PER_USD와 반드시 동일하게 유지.
KRW_PER_USD = 1350


def usd(krw: float) -> str:
    """KRW 저장가 → 참가자 표시용 USD 문자열 (빌드 환율 역산)."""
    return f"${krw / KRW_PER_USD:,.2f}"


def product_display_price(product) -> str | None:
    """EN 참가자 표시용 가격 — 아마존 원본 정가(attributes.priceUsd, 배포 KRW와
    정합 검증된 상품에만 존재)를 우선하고, 없으면 빌드 환율 역산."""
    price = getattr(product, "price", None)
    if product is None or price is None:
        return None
    raw = (getattr(product, "attributes", None) or {}).get("priceUsd")
    try:
        val = float(raw) if raw is not None else None
    except (TypeError, ValueError):
        val = None
    if val and val > 0:
        return f"${val:,.2f}"
    return usd(price)


def product_display_title(product) -> str | None:
    """참가자 표시·LLM 컨텍스트용 상품명 — EN 모드면 아마존 원문 제목을 우선한다."""
    if product is None:
        return None
    if is_en():
        t = ((getattr(product, "attributes", None) or {}).get("titleEn") or "").strip()
        if t:
            return t
    return product.title
