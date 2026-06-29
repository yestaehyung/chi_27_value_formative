"""B: 충돌 해결 확인 메시지는 시나리오 중립 + 실제 기준에 근거해야 한다.

버그: conflict_resolver.MESSAGE_BY_ACTION이 선물/최저가 데모 도메인 문자열을 박아서,
다른 도메인(이어폰·의류 등)의 충돌을 해결하면 사실과 다른 확인 메시지가 사용자에게 그대로
나간다 (api/conflicts.py가 LLM 리라이트 없이 raw 반환 — 유일한 미경유 발화).
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_test_"), "test.db"))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

import pytest

from app.preference_commit.conflict_resolver import build_resolution_message

_LEAKS = ("선물", "최저가", "예산 상한")


def test_accept_new_is_grounded_on_the_new_criterion():
    msg = build_resolution_message("accept_new", old_label="가격이 낮을수록 좋음",
                                   new_label="오래 쓰는 배터리")
    assert "오래 쓰는 배터리" in msg
    for leak in _LEAKS:
        assert leak not in msg, msg


def test_merge_references_the_actual_avoidance_not_gift_text():
    msg = build_resolution_message("merge", old_label="가격이 낮을수록 좋음",
                                   avoidance_label="저소음 아닌 제품 제외")
    assert "저소음 아닌 제품 제외" in msg
    for leak in _LEAKS:
        assert leak not in msg, msg


def test_keep_old_and_fallback_are_neutral():
    assert build_resolution_message("keep_old", old_label="긴 배터리")
    assert build_resolution_message("unknown_action")  # 폴백 — 빈 문자열 아님
    for action in ("keep_old", "manual_edit", "unknown_action"):
        msg = build_resolution_message(action)
        for leak in _LEAKS:
            assert leak not in msg, (action, msg)
