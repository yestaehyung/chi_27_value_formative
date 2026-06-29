"""E: OpenAI/DeepSeek _call은 일시적 네트워크 오류에 재시도해야 한다.

버그: @with_retries가 no-op인 _augment_payload(동기 훅)에 붙어 있어 실제 네트워크
호출(_call)에는 재시도가 없었다(Anthropic만 _call에 데코). times=2 → 총 3회 시도.
"""
import asyncio
import os
import tempfile

os.environ.setdefault("VC_DB_PATH", os.path.join(tempfile.mkdtemp(prefix="vc_test_"), "test.db"))
os.environ.setdefault("VC_LLM_PROVIDER", "mock")

import httpx

from app.llm.provider import OpenAIProvider


class _FakeResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": "{}"}}]}


def test_call_retries_on_transient_error(monkeypatch):
    # retry 사이 sleep 제거(테스트 속도)
    async def _no_sleep(*a, **k):
        return None
    monkeypatch.setattr("app.llm.retry.asyncio.sleep", _no_sleep)

    calls = {"n": 0}

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            calls["n"] += 1
            if calls["n"] < 3:  # 처음 2회 실패 → 3회째 성공
                raise httpx.ConnectError("transient")
            return _FakeResp()

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    # __init__(키 필요)을 우회해 순수 _call 경로만 검증
    p = object.__new__(OpenAIProvider)
    p.api_key = "k"
    p.model = "gpt-4o-mini"
    p.api_url = "https://example.test/v1/chat/completions"
    p.max_tokens_param = "max_tokens"

    out = asyncio.run(p._call([{"role": "user", "content": "x"}], max_tokens=10, json_mode=True))
    assert out == "{}"
    assert calls["n"] == 3, calls  # 2 failures + 1 success
