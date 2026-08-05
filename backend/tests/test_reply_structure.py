"""에이전트 답변의 구조 문법 보존 검증 (2026-08-06).

이전에는 말풍선이 평문 렌더라 `_strip_markdown`이 마크다운을 전부 지웠다. 지금은 프론트
`StructuredText`가 불릿·번호 목록·표·굵게를 렌더하므로, **그 넷은 살아남아야 하고
렌더러가 다루지 않는 문법은 계속 지워져야 한다**. 둘 중 하나만 어긋나도 참가자 화면에
문제가 생긴다 — 살려야 할 것을 지우면 구조가 사라지고, 지워야 할 것을 살리면 '### 요약'이
글자 그대로 노출된다.
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_struct_"), "test.db"))
os.environ["VC_LLM_PROVIDER"] = "mock"

import pytest

from app.agents.response_generator import _strip_markdown


@pytest.mark.parametrize("kept", [
    "- 화면 크기\n- 가격대",                       # 불릿
    "1. 예산\n2. 화면\n3. 브랜드",                  # 번호 목록
    "| 항목 | 화면 |\n| 27인치 | 넉넉함 |",          # 표
    "**썬더볼트**는 미기재예요",                     # 굵게
])
def test_renderable_syntax_survives(kept: str):
    assert _strip_markdown(kept) == kept.strip()


@pytest.mark.parametrize("raw,gone", [
    ("### 요약\n내용", "###"),
    ("`코드`", "`"),
    ("__밑줄__", "__"),
    ("> 인용문", ">"),
])
def test_unrenderable_syntax_is_removed(raw: str, gone: str):
    assert gone not in _strip_markdown(raw)


def test_table_with_divider_row_is_untouched():
    """구분행(|---|)은 백엔드가 건드리지 않는다 — 프론트 렌더러가 버린다."""
    table = "| 항목 | 화면 |\n|---|---|\n| 27인치 | 넉넉함 |"
    assert _strip_markdown(table) == table


def test_heading_removal_keeps_the_text():
    """제목 문법만 벗기고 문구는 남긴다 — 내용까지 사라지면 답변에 구멍이 난다."""
    assert _strip_markdown("## 비교해볼게요") == "비교해볼게요"


def test_prompt_never_names_a_screen_direction():
    """프롬프트에 방향 어휘가 들어가면 모델이 그걸 집어 쓴다.

    2026-08-06 실측: 규칙4가 금지 예시로 '오른쪽 패널'을 적고 있었는데, 그 단어가
    컨텍스트에 들어가는 바람에 모델이 "오른쪽 카드에서 확인해 주세요"(심지어 "왼쪽"도)를
    12%(5/40) 확률로 냈다. 카드는 말풍선 **아래**에 붙으므로 전부 오안내다.
    금지 예시를 지우고 "아래"를 알려주자 0/40이 됐다.

    금지 규칙이 아니라 오염원 제거다 — 프롬프트 어디에도 방향 어휘가 없어야 한다.
    """
    from app.llm.prompts import AGENT_REPLY_SYSTEM

    for word in ("오른쪽", "왼쪽", "우측", "좌측", "사이드"):
        assert word not in AGENT_REPLY_SYSTEM, (
            f"프롬프트에 '{word}'가 있으면 모델이 그 방향을 안내한다"
        )
    assert "아래" in AGENT_REPLY_SYSTEM, "카드가 어디 있는지는 알려줘야 한다"


def test_prompt_describes_the_four_supported_forms():
    """프롬프트와 렌더러가 같은 문법 집합을 가리켜야 한다.

    한쪽만 바뀌면 모델이 렌더 안 되는 문법을 쓰거나(글자 노출), 렌더 가능한데 안 쓴다.
    """
    from app.llm.prompts import AGENT_REPLY_SYSTEM

    for form in ("불릿", "번호 목록", "표", "굵게"):
        assert form in AGENT_REPLY_SYSTEM, f"프롬프트에 {form} 설명이 없다"
    # 렌더러가 못 다루는 것은 쓰지 말라고 명시돼 있어야 한다
    assert "코드블록" in AGENT_REPLY_SYSTEM
