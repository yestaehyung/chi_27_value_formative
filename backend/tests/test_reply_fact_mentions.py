"""D2 절충안 (2026-08-26) — 미확인 기준 '언급 보장' 검증.

프롬프트(룰 3)의 "확인 불가 기준을 밝혀라" 지시에 대한 코드 안전망:
LLM이 자기 말로 언급하면 무변경(문체 보존), 빠뜨리면 고지 한 줄만 덧붙인다.
verbatim 강제·전체 폴백은 쓰지 않는다 — 표현 차이로 턴 전체가 템플릿화되면
평균 품질(우리 DV의 재료)이 깎인다.
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_d2_"), "t.db"))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

from app.agents.response_generator import _ensure_unverified_mentions, _mentions


def test_mention_check_requires_content_words():
    assert _mentions("the listings don't specify the color, so confirm white first", "white color")
    assert not _mentions("here are five nice shirts under $40", "white color")
    # 우연 일치 방지: 2단어 이상 라벨은 단어 1개로는 언급이 아니다
    assert not _mentions("this fits your life well", "battery life")
    assert _mentions("battery life isn't stated", "battery life")


def test_mention_requires_uncertainty_direction():
    """v2: 반대 방향 주장("white shirts입니다")은 언급으로 인정하지 않는다."""
    assert not _mentions("I found white color shirts for you.", "white color")
    assert not _mentions("These are white color business shirts. Great value!", "white color")
    assert _mentions("Color isn't stated, so white color needs a check on the page.", "white color")


def test_supplement_added_only_when_missing():
    note = {"unverifiedCriteria": {"white color": 5}}
    said = "None of these listings specify the color — confirm white on the product page."
    assert _ensure_unverified_mentions(said, note) == said, "언급했으면 무변경"

    silent = "Here are 5 business-casual shirts under $40. Take a look!"
    out = _ensure_unverified_mentions(silent, note)
    assert out.startswith(silent), "본문은 보존"
    assert "white color" in out, "고지 한 줄이 덧붙는다"
    assert ("상세 페이지" in out) or ("product page" in out)  # 로케일별 고지 문구


def test_top_two_labels_only_and_no_note_without_unverified():
    text = "Here are some desks."
    assert _ensure_unverified_mentions(text, None) == text
    assert _ensure_unverified_mentions(text, {"unverifiedCriteria": {}}) == text
    out = _ensure_unverified_mentions(text, {"unverifiedCriteria": {
        "solid wood": 5, "cable management": 4, "adjustable height": 1}})
    assert "solid wood" in out and "cable management" in out
    assert "adjustable height" not in out, "상위 2개만 고지 (본문 과밀 방지)"
