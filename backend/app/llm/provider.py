"""Provider-agnostic LLM wrapper (spec §27).

Pipeline stages call `generate_json(messages, schema=..., task=..., context=...)`.
- MockLLMProvider (default): ignores messages, dispatches `task` to deterministic
  rule functions in mock_rules.py so the demo runs end-to-end with no API key.
- AnthropicProvider: sends the rendered messages and parses JSON from the reply.
"""
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.core.config import settings
from app.llm import mock_rules
from app.llm.json_parser import extract_json
from app.llm.retry import with_retries


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMProvider:
    name = "base"

    async def generate_text(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.2,
        max_tokens: int = 1000,
    ) -> str:
        raise NotImplementedError

    async def generate_json(
        self,
        messages: List[LLMMessage],
        schema: Optional[Dict[str, Any]] = None,
        temperature: float = 0.1,
        max_tokens: int = 1500,
        task: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError

    async def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    """Deterministic demo responses (gift smartwatch scenario first, spec §27)."""

    name = "mock"

    async def generate_text(self, messages, temperature=0.2, max_tokens=1000) -> str:
        return mock_rules.generic_text(messages[-1].content if messages else "")

    async def generate_json(self, messages, schema=None, temperature=0.1,
                            max_tokens=1500, task=None, context=None) -> Dict[str, Any]:
        handler = mock_rules.TASK_HANDLERS.get(task or "")
        if handler is None:
            return {}
        return handler(context or {})

    async def embed(self, texts: List[str]) -> List[List[float]]:
        # Cheap deterministic bag-of-character embedding, good enough for MVP dedup.
        return [[(sum(ord(c) for c in t) % 997) / 997.0] for t in texts]


class OpenAIProvider(LLMProvider):
    """OpenAI chat completions (gpt-5 family: max_completion_tokens, reasoning_effort,
    temperature is fixed to the model default)."""

    name = "openai"
    api_url = "https://api.openai.com/v1/chat/completions"
    max_tokens_param = "max_completion_tokens"  # gpt-5 family naming

    def __init__(self) -> None:
        self.api_key = settings.openai_api_key
        self.model = settings.openai_model
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")

    def _prepare_messages(self, messages: List[LLMMessage], task: Optional[str],
                          context: Optional[Dict[str, Any]], json_mode: bool) -> list[dict]:
        from app.llm.prompts import FORMAT_BY_TASK, SYSTEM_BY_TASK, render_user_context

        msgs = [{"role": m.role, "content": m.content} for m in messages]
        # some call sites pass bare/empty messages and rely on task+context
        if task and not any(m["role"] == "system" for m in msgs) and task in SYSTEM_BY_TASK:
            msgs.insert(0, {"role": "system", "content": SYSTEM_BY_TASK[task]})
        if not any(m["role"] == "user" for m in msgs):
            msgs.append({"role": "user", "content": render_user_context(context or {})})
        if json_mode:
            fmt = FORMAT_BY_TASK.get(task or "", "")
            msgs[-1] = {**msgs[-1], "content": msgs[-1]["content"] + "\n" + fmt + "\n\n반드시 유효한 JSON 객체로만 응답하라."}
        return msgs

    @with_retries(times=2)
    def _augment_payload(self, payload: Dict[str, Any]) -> None:
        """Subclass hook: mutate the request payload before send. No-op by default."""

    async def _call(self, msgs: list[dict], max_tokens: int, json_mode: bool,
                    temperature: float = 0.2) -> str:
        import httpx

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": msgs,
            # reasoning tokens come out of this budget — keep it generous
            self.max_tokens_param: max(max_tokens * 3, 4000),
        }
        if self.model.startswith("gpt-5"):
            # gpt-5 family: fixed temperature, tunable reasoning effort
            payload["reasoning_effort"] = settings.openai_reasoning_effort
        else:
            payload["temperature"] = temperature
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        self._augment_payload(payload)  # subclass hook (DeepSeek thinking toggle 등)
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                self.api_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"] or ""

    async def generate_text(self, messages, temperature=0.7, max_tokens=1000) -> str:
        msgs = self._prepare_messages(messages, None, None, json_mode=False)
        return await self._call(msgs, max_tokens, json_mode=False, temperature=temperature)

    async def generate_json(self, messages, schema=None, temperature=0.1,
                            max_tokens=1500, task=None, context=None) -> Dict[str, Any]:
        import logging

        msgs = self._prepare_messages(messages, task, context, json_mode=True)
        text = await self._call(msgs, max_tokens, json_mode=True, temperature=temperature)
        out = extract_json(text)
        logging.getLogger("llm").info("task=%s raw=%s", task, text[:500].replace("\n", " "))
        return out

    async def embed(self, texts: List[str]) -> List[List[float]]:
        import httpx

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"model": "text-embedding-3-small", "input": texts},
            )
            resp.raise_for_status()
            return [d["embedding"] for d in resp.json()["data"]]


class DeepSeekProvider(OpenAIProvider):
    """DeepSeek — OpenAI-compatible chat completions (https://api.deepseek.com).
    Reuses OpenAIProvider's message/JSON handling; differs only in endpoint, key,
    model, and the max-tokens parameter name (standard `max_tokens`).
    """

    name = "deepseek"
    api_url = "https://api.deepseek.com/chat/completions"
    max_tokens_param = "max_tokens"

    def __init__(self) -> None:
        self.api_key = settings.deepseek_api_key
        self.model = settings.deepseek_model
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set")

    def _augment_payload(self, payload: Dict[str, Any]) -> None:
        """DeepSeek V4 thinking 토글 (config). off면 reasoning 토큰 생성을 끈다 (4~8배 빠름).
        기본값(미지정)은 API상 enabled이므로, off일 때만 명시적으로 disabled를 보낸다."""
        if settings.deepseek_thinking == "off":
            payload["thinking"] = {"type": "disabled"}
        elif settings.deepseek_thinking == "on":
            payload["thinking"] = {"type": "enabled"}

    async def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError("DeepSeek has no embeddings API; MVP does not need it.")


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")

    @with_retries(times=2)
    async def _call(self, messages: List[LLMMessage], temperature: float, max_tokens: int) -> str:
        import httpx

        system = "\n".join(m.content for m in messages if m.role == "system")
        user_messages = [
            {"role": m.role, "content": m.content} for m in messages if m.role != "system"
        ]
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.anthropic_model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "system": system or None,
                    "messages": user_messages or [{"role": "user", "content": "."}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return "".join(b.get("text", "") for b in data.get("content", []))

    async def generate_text(self, messages, temperature=0.2, max_tokens=1000) -> str:
        return await self._call(messages, temperature, max_tokens)

    async def generate_json(self, messages, schema=None, temperature=0.1,
                            max_tokens=1500, task=None, context=None) -> Dict[str, Any]:
        suffix = "\n\n반드시 유효한 JSON으로만 응답하라."
        if schema:
            suffix += f"\nJSON Schema:\n{json.dumps(schema, ensure_ascii=False)}"
        msgs = list(messages)
        if msgs:
            msgs[-1] = LLMMessage(role=msgs[-1].role, content=msgs[-1].content + suffix)
        text = await self._call(msgs, temperature, max_tokens)
        return extract_json(text)

    async def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError("Use a dedicated embedding provider; MVP does not need it.")


_provider: Optional[LLMProvider] = None
_judge_provider: Optional[LLMProvider] = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        if settings.llm_provider == "openai":
            _provider = OpenAIProvider()
        elif settings.llm_provider == "deepseek":
            _provider = DeepSeekProvider()
        elif settings.llm_provider == "anthropic":
            _provider = AnthropicProvider()
        else:
            _provider = MockLLMProvider()
    return _provider


def get_judge_provider() -> LLMProvider:
    """Judge 전용 provider (측정 설계 M5). VC_JUDGE_PROVIDER 미설정이면 주 provider
    공용 — 검증 독립성을 위해 실환경에서는 service agent와 다른 모델을 권장."""
    global _judge_provider
    if settings.judge_provider in (None, "", settings.llm_provider):
        return get_provider()
    if _judge_provider is None:
        if settings.judge_provider == "openai":
            _judge_provider = OpenAIProvider()
        elif settings.judge_provider == "deepseek":
            _judge_provider = DeepSeekProvider()
        elif settings.judge_provider == "anthropic":
            _judge_provider = AnthropicProvider()
        else:
            _judge_provider = MockLLMProvider()
    return _judge_provider
