"""LLM 요청 페이로드 규약 (2026-08-02).

배경 — 라이브에서 두 번 물렸다:
  ① `reasoning_effort="minimal"`을 gpt-5.6에 보내 **전 호출 400 Bad Request**.
     공식 문서: 유효값은 none/minimal/low/medium/high/xhigh/max이지만
     **지원 범위는 모델마다 다르다**("모델 페이지를 확인하라"). 코드가 설정값을
     검증 없이 그대로 보내고 있었다.
  ② 출력 예산 4,500 — 문서 권고는 "추론+출력에 최소 25,000". 부족하면 **보이는 출력
     없이** 잘려(finish_reason=length) 파이프라인 단계가 조용히 빈 결과로 통과한다.

모델별 지원 표를 코드에 박으면 곧 낡으므로, 규약은 세 가지로 고정한다:
  · 유효 집합 밖의 값은 **보내지 않는다** (모델 기본값 사용)
  · 400이 오면 파라미터를 빼고 **한 번 재시도**한다
  · 출력 예산은 min_output_budget 아래로 내려가지 않는다
"""
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_pay_"), "test.db"))
os.environ.setdefault("VC_EXPORT_DIR", tempfile.mkdtemp(prefix="vc_pay_exp_"))
os.environ["VC_LLM_PROVIDER"] = "mock"

import asyncio

import httpx
import pytest

from app.core.config import settings
from app.llm.provider import DeepSeekProvider, OpenAIProvider


class _Resp:
    def __init__(self, status=200, payload=None):
        self.status_code = status
        self._payload = payload or {
            "choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}],
            "usage": {},
        }

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)  # type: ignore[arg-type]


class _Client:
    """post() 호출을 기록하고, 미리 정한 상태코드를 순서대로 돌려주는 가짜 httpx 클라이언트."""

    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.sent: list[dict] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        # 재시도는 같은 dict를 수정해 다시 보낸다 — 스냅샷을 떠야 호출 간 차이를 볼 수 있다
        self.sent.append(dict(json))
        return _Resp(self.statuses.pop(0) if self.statuses else 200)


@pytest.fixture
def patch_client(monkeypatch):
    def _install(statuses):
        client = _Client(statuses)
        monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client)
        return client
    return _install


def _openai(monkeypatch, effort, model="gpt-5.6-terra"):
    monkeypatch.setattr(settings, "openai_api_key", "sk-test", raising=False)
    monkeypatch.setattr(settings, "openai_model", model, raising=False)
    monkeypatch.setattr(settings, "openai_reasoning_effort", effort, raising=False)
    return OpenAIProvider()


def test_valid_effort_is_sent(monkeypatch, patch_client):
    client = patch_client([200])
    p = _openai(monkeypatch, "none")
    asyncio.run(p._call([{"role": "user", "content": "x"}], 1500, json_mode=True))
    assert client.sent[0]["reasoning_effort"] == "none"


def test_unknown_effort_is_not_sent(monkeypatch, patch_client):
    """오타·폐기값이 설정돼도 요청에 실리지 않는다 — 모델 기본값으로 동작해야 한다."""
    client = patch_client([200])
    p = _openai(monkeypatch, "ultra")          # 유효 집합 밖
    asyncio.run(p._call([{"role": "user", "content": "x"}], 1500, json_mode=True))
    assert "reasoning_effort" not in client.sent[0]


def test_400_retries_without_effort(monkeypatch, patch_client):
    """모델이 그 effort를 지원하지 않아 400이면, 빼고 한 번 재시도한다 (라이브 장애 재현)."""
    client = patch_client([400, 200])
    p = _openai(monkeypatch, "minimal")        # gpt-5.6이 거부하는 값
    asyncio.run(p._call([{"role": "user", "content": "x"}], 1500, json_mode=True))
    assert len(client.sent) == 2
    assert client.sent[0]["reasoning_effort"] == "minimal"
    assert "reasoning_effort" not in client.sent[1]


def test_output_budget_floor(monkeypatch, patch_client):
    """추론 토큰이 예산에서 나가므로 바닥값 아래로 내려가면 안 된다 (문서 권고 25k)."""
    client = patch_client([200])
    p = _openai(monkeypatch, "none")
    asyncio.run(p._call([{"role": "user", "content": "x"}], 1500, json_mode=True))
    assert client.sent[0]["max_completion_tokens"] >= OpenAIProvider.min_output_budget


def test_deepseek_budget_and_param_name(monkeypatch, patch_client):
    """DeepSeek은 파라미터 이름이 max_tokens이고, thinking 토큰도 같은 예산에서 나간다."""
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-test", raising=False)
    monkeypatch.setattr(settings, "deepseek_model", "deepseek-v4-flash", raising=False)
    monkeypatch.setattr(settings, "deepseek_thinking", "on", raising=False)
    client = patch_client([200])
    p = DeepSeekProvider()
    asyncio.run(p._call([{"role": "user", "content": "x"}], 1500, json_mode=True))
    sent = client.sent[0]
    assert sent["max_tokens"] >= DeepSeekProvider.min_output_budget
    assert "max_completion_tokens" not in sent
