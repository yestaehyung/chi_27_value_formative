"""참가자 화면 언어 (VC_STUDY_LOCALE: ko | en).

백엔드가 만드는 참가자 대면 텍스트의 언어를 결정한다 — LLM 산출물(칩 라벨·응답·
답변칩·충돌 카드·카드 이유)은 프롬프트 지시 주입으로(prompts.EN_DIRECTIVES),
결정론 템플릿·폴백은 L(ko, en)으로 전환한다.

연구 로그·내부 계약(kind 어휘, searchText 등)은 언어와 무관하게 유지된다 —
특히 searchText는 검색 인덱스(한국어 임베딩·FTS)와 정합해야 하므로 항상 한국어다.
"""
from app.core.config import settings


def is_en() -> bool:
    return settings.study_locale == "en"


def L(ko: str, en: str) -> str:
    """참가자 대면 문자열의 로케일 선택 (프론트 studyI18n.tr()의 백엔드 판)."""
    return en if is_en() else ko
