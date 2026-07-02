"""연구자 API 게이트 (스터디 분리 2026-07-02) — research_gate 규칙 검증."""
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.config import settings
from app.core.research_gate import require_research_key


def _req(headers: dict | None = None, query: str = "") -> Request:
    scope = {
        "type": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
        "query_string": query.encode(),
    }
    return Request(scope)


def test_key_set_correct_header_passes(monkeypatch):
    monkeypatch.setattr(settings, "research_key", "secret1")
    monkeypatch.setattr(settings, "app_mode", "study")
    require_research_key(_req({"X-Research-Key": "secret1"}))  # no raise


def test_key_set_query_param_passes(monkeypatch):
    monkeypatch.setattr(settings, "research_key", "secret1")
    require_research_key(_req(query="key=secret1"))  # no raise


def test_key_set_wrong_or_missing_403(monkeypatch):
    monkeypatch.setattr(settings, "research_key", "secret1")
    with pytest.raises(HTTPException) as e:
        require_research_key(_req({"X-Research-Key": "wrong"}))
    assert e.value.status_code == 403
    with pytest.raises(HTTPException):
        require_research_key(_req())


def test_no_key_study_mode_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, "research_key", "")
    monkeypatch.setattr(settings, "app_mode", "study")
    with pytest.raises(HTTPException) as e:
        require_research_key(_req())
    assert e.value.status_code == 403


def test_no_key_local_dev_open(monkeypatch):
    monkeypatch.setattr(settings, "research_key", "")
    monkeypatch.setattr(settings, "app_mode", "")
    require_research_key(_req())  # no raise — 기존 로컬 동작 유지
