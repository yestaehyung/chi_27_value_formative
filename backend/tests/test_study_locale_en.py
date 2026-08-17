"""참가자 화면 언어 스위치 (VC_STUDY_LOCALE=en, 2026-08-16).

L(ko, en)은 호출 시점에 settings.study_locale을 읽고, system_for(task)는 참가자
대면 태스크에만 영어 지시를 붙인다. 영어 스터디의 searchText는 영어 전용
시드의 BM25·임베딩과 같은 언어를 사용한다.
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
    assert "searchText stays English" in s
    assert "searchText, and constraintsNote in English" in s
    assert SYSTEM_BY_TASK["action_decision"][:50] in s
    assert "Participant-facing output language" in system_for("topic_extraction")
    assert "in English" in system_for("rerank")
    assert system_for("anchor_mapping") == SYSTEM_BY_TASK["anchor_mapping"]


def test_system_for_korean_mode_is_passthrough():
    from app.llm.prompts import SYSTEM_BY_TASK, system_for

    assert system_for("topic_extraction") == SYSTEM_BY_TASK["topic_extraction"]


def test_english_seed_category_metadata_and_scenario_context(en_locale):
    from app.api.meta import CATEGORY_LABELS
    from app.products.seed_loader import get_scenario

    assert CATEGORY_LABELS["Office Chairs"]["blurb"] == "Chairs for long work sessions"
    assert CATEGORY_LABELS["Earphones & Earbuds"]["emoji"] == "🎧"
    assert get_scenario("cat:Laptops")["context"] == "Participant-selected category"
