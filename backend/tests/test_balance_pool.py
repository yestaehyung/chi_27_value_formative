"""VC_BALANCE_CONDITIONS — 물결별 배정 풀 제한 (2026-08-26 b1 누수 사고 재발 방지).

b1 수집이 끝난 물결에서 b2/ours 카운트가 b1을 추월하면 minimization이 b1을
최소 조건으로 보고 다시 배정하기 시작한다. 배정 풀을 env로 제한해 차단한다.
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_test_"), "test.db"))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

from app.core import conditions
from app.core.config import settings


def test_default_pool_is_all_conditions():
    settings.balance_conditions = []
    assert conditions.balance_pool() == conditions.STUDY_CONDITIONS


def test_pool_restricts_assignment(monkeypatch):
    settings.balance_conditions = ["baseline2", "ours"]
    try:
        # b1이 최소여도 풀 밖이라 배정되지 않는다
        monkeypatch.setattr(conditions, "assigned_counts",
                            lambda db: {"baseline1": 0, "baseline2": 5, "ours": 6})
        monkeypatch.setattr(conditions, "get_forced_condition", lambda db: None)
        assert conditions.assign_condition(None) == "baseline2"
        monkeypatch.setattr(conditions, "assigned_counts",
                            lambda db: {"baseline1": 0, "baseline2": 7, "ours": 6})
        assert conditions.assign_condition(None) == "ours"
    finally:
        settings.balance_conditions = []


def test_unknown_names_ignored():
    settings.balance_conditions = ["typo", "ours"]
    try:
        assert conditions.balance_pool() == ("ours",)
    finally:
        settings.balance_conditions = []


def test_forced_condition_still_wins(monkeypatch):
    settings.balance_conditions = ["baseline2", "ours"]
    try:
        monkeypatch.setattr(conditions, "get_forced_condition", lambda db: "baseline1")
        assert conditions.assign_condition(None) == "baseline1"
    finally:
        settings.balance_conditions = []
