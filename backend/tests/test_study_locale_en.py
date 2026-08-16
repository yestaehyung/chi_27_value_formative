"""참가자 화면 언어 스위치 (VC_STUDY_LOCALE=en, 2026-08-16).

L(ko, en)은 호출 시점에 settings.study_locale을 읽고, system_for(task)는 참가자
대면 태스크에만 영어 지시를 붙인다. searchText는 영어 모드에서도 한국어 유지가
계약 — 검색 인덱스(한국어 임베딩·FTS)와의 정합 때문이다.
(모듈 임포트 시점에 고정되는 상수 dict들은 프로세스 기동 env로 결정 — 프로덕션 경로.)
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_test_"), "test.db"))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

import pytest

from app.core.config import settings


@pytest.fixture
def en_locale(monkeypatch):
    monkeypatch.setattr(settings, "study_locale", "en")


def test_L_switches_at_call_time(en_locale):
    from app.core.locale import L

    assert L("한국어", "English") == "English"


def test_templates_switch_to_english(en_locale):
    from app.agents import response_generator as rg

    assert "picked" in rg.recommend_text([None] * 5)
    assert "find a product" in rg.near_miss_text([])
    assert "relax" in rg.empty_handed_text(["min 16GB RAM"])
    assert "min 16GB RAM" in rg.empty_handed_text(["min 16GB RAM"])


def test_korean_default_unchanged():
    from app.agents import response_generator as rg

    assert "골라봤어요" in rg.recommend_text([None] * 5)


def test_system_for_appends_directive_only_for_participant_tasks(en_locale):
    from app.llm.prompts import SYSTEM_BY_TASK, system_for

    s = system_for("action_decision")
    assert "keep searchText in KOREAN" in s
    assert SYSTEM_BY_TASK["action_decision"][:50] in s
    assert "Participant-facing output language" in system_for("topic_extraction")
    assert "in English" in system_for("rerank")
    assert system_for("anchor_mapping") == SYSTEM_BY_TASK["anchor_mapping"]


def test_system_for_korean_mode_is_passthrough():
    from app.llm.prompts import SYSTEM_BY_TASK, system_for

    assert system_for("topic_extraction") == SYSTEM_BY_TASK["topic_extraction"]
