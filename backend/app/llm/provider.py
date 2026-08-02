"""Provider-agnostic LLM wrapper (spec §27).

Pipeline stages call `generate_json(messages, schema=..., task=..., context=...)`.
- MockLLMProvider (default): ignores messages, dispatches `task` to deterministic
  rule functions in mock_rules.py so the demo runs end-to-end with no API key.
- AnthropicProvider: sends the rendered messages and parses JSON from the reply.
"""
import json
import logging
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.core.config import settings
from app.llm import mock_rules
from app.llm.json_parser import extract_json
from app.llm.retry import with_retries

# 특정 요청(asyncio Task)에만 모델/추론을 덮어쓰는 task-local override — 합성 직접 실행에서
# 빠른 모델(flash)을 쓰되 동시 스터디 요청은 전역 설정 유지. asyncio Task는 context가 격리됨.
MODEL_OVERRIDE: ContextVar[Optional[str]] = ContextVar("vc_model_override", default=None)
THINKING_OVERRIDE: ContextVar[Optional[str]] = ContextVar("vc_thinking_override", default=None)


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

    async def generate_with_tools(self, messages: list[dict], tools: list[dict],
                                  execute_tool, max_rounds: int = 3,
                                  temperature: float = 0.2, max_tokens: int = 900):
        """OpenAI-호환 function-calling 루프 (축 2 agentic 턴 루프 전용, 2026-07-07).
        mock은 미구현 — agentic 경로는 mock에서 파이프라인으로 폴백한다."""
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

    #: 추론 토큰은 출력 예산에서 나간다. 공식 문서가 "추론+출력에 최소 25,000 토큰을
    #: 확보하라"고 권고한다 — 부족하면 **보이는 출력 없이** 잘려서(finish_reason=length)
    #: 파이프라인 단계가 조용히 빈 결과로 통과한다.
    #: (cap일 뿐이므로 실제 생성분만 과금된다 — 넉넉히 잡는 데 비용이 들지 않는다.)
    min_output_budget = 25_000

    #: reasoning_effort 유효값(공식 문서). **지원 범위는 모델마다 다르다** —
    #: 예: gpt-5.6은 'minimal'을 거부하고 400을 낸다. 모델별 표를 코드에 박으면 곧 낡으므로,
    #: 값이 이 집합에 없으면 보내지 않고, 400을 만나면 파라미터를 빼고 한 번 재시도한다.
    REASONING_EFFORTS = frozenset({"none", "minimal", "low", "medium", "high", "xhigh", "max"})

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

    def _augment_payload(self, payload: Dict[str, Any]) -> None:
        """Subclass hook: mutate the request payload before send. No-op by default."""

    @with_retries(times=2)
    async def _call(self, msgs: list[dict], max_tokens: int, json_mode: bool,
                    temperature: float = 0.2) -> str:
        import httpx

        model = MODEL_OVERRIDE.get() or self.model     # task-local override(합성 등) 우선
        payload: Dict[str, Any] = {
            "model": model,
            "messages": msgs,
            # 추론 토큰이 이 예산에서 나간다 — min_output_budget 주석 참조
            self.max_tokens_param: max(max_tokens * 3, self.min_output_budget),
        }
        if model.startswith("gpt-5"):
            # gpt-5 계열: temperature 고정, reasoning_effort로 추론량 조절.
            # 설정값이 유효 집합 밖이면 아예 보내지 않는다(모델 기본값 사용).
            effort = (settings.openai_reasoning_effort or "").strip().lower()
            if effort in self.REASONING_EFFORTS:
                payload["reasoning_effort"] = effort
            elif effort:
                logging.getLogger("llm").warning(
                    "unknown reasoning_effort=%r — 전송하지 않고 모델 기본값을 쓴다 (유효값: %s)",
                    effort, sorted(self.REASONING_EFFORTS),
                )
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
            # 이 모델이 해당 effort를 지원하지 않으면 400이 온다(모델별 지원 범위가 다르다).
            # 파라미터를 빼고 한 번만 재시도 — 모델별 표를 하드코딩하지 않기 위한 대응.
            if resp.status_code == 400 and "reasoning_effort" in payload:
                logging.getLogger("llm").warning(
                    "model=%s rejected reasoning_effort=%r — 빼고 재시도한다",
                    model, payload["reasoning_effort"],
                )
                payload.pop("reasoning_effort")
                resp = await client.post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            # 토큰 예산 소진은 **예외가 아니라 빈 문자열**로 온다 — _safe()는 예외만 잡으므로
            # 파이프라인 단계가 조용히 "결과 0건"으로 통과해 버린다. 추론 모델은 reasoning
            # 토큰이 같은 예산에서 나가므로 특히 잘 터진다(실측: v4-flash thinking=on이
            # max_tokens 1500을 전부 추론에 쓰고 content=''). 실패를 눈에 보이게 남긴다.
            if choice.get("finish_reason") == "length":
                usage = data.get("usage") or {}
                logging.getLogger("llm").warning(
                    "LLM output truncated (finish_reason=length) model=%s budget=%s "
                    "completion=%s reasoning=%s — 결과가 비어 단계가 조용히 스킵될 수 있음",
                    model, payload.get(self.max_tokens_param),
                    usage.get("completion_tokens"),
                    (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                )
            return choice["message"]["content"] or ""

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

    async def generate_with_tools(self, messages: list[dict], tools: list[dict],
                                  execute_tool, max_rounds: int = 3,
                                  temperature: float = 0.2, max_tokens: int = 900):
        """OpenAI-호환 function-calling 루프 (축 2 agentic, 2026-07-07).

        messages는 raw dict 리스트(도구 프로토콜 때문에 LLMMessage 대신) —
        assistant tool_calls·tool 결과 메시지를 그대로 이어붙인다.
        execute_tool(name, args) -> JSON 직렬화 가능 dict 코루틴.
        반환: (최종 텍스트, [{name, args, result}] 도구 호출 trace).
        max_rounds 소진 시 도구 없이 마지막 답변을 강제한다(무한 루프 방지 —
        루프 상한은 판단이 아니라 자원 가드)."""
        import httpx

        model = MODEL_OVERRIDE.get() or self.model
        msgs = list(messages)
        trace: list[dict] = []

        def _payload(with_tools: bool) -> Dict[str, Any]:
            p: Dict[str, Any] = {"model": model, "messages": msgs,
                                 self.max_tokens_param: max(max_tokens * 3, 4000)}
            if model.startswith("gpt-5"):
                p["reasoning_effort"] = settings.openai_reasoning_effort
            else:
                p["temperature"] = temperature
            if with_tools:
                p["tools"] = tools
            self._augment_payload(p)
            return p

        async with httpx.AsyncClient(timeout=120) as client:
            for round_i in range(max_rounds + 1):
                with_tools = round_i < max_rounds
                resp = await client.post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=_payload(with_tools),
                )
                resp.raise_for_status()
                msg = resp.json()["choices"][0]["message"]
                tool_calls = msg.get("tool_calls") or []
                if not tool_calls:
                    return (msg.get("content") or "").strip(), trace
                msgs.append(msg)
                for tc in tool_calls:
                    name = (tc.get("function") or {}).get("name") or ""
                    try:
                        args = json.loads((tc.get("function") or {}).get("arguments") or "{}")
                    except Exception:  # noqa: BLE001
                        args = {}
                    result = await execute_tool(name, args)
                    trace.append({"name": name, "args": args, "result": result})
                    msgs.append({"role": "tool", "tool_call_id": tc.get("id") or "",
                                 "content": json.dumps(result, ensure_ascii=False)})
        return "", trace  # 도달 불가(마지막 라운드는 tools 없음 → 텍스트 반환)


class DeepSeekProvider(OpenAIProvider):
    """DeepSeek — OpenAI-compatible chat completions (https://api.deepseek.com).
    Reuses OpenAIProvider's message/JSON handling; differs only in endpoint, key,
    model, and the max-tokens parameter name (standard `max_tokens`).
    """

    name = "deepseek"
    api_url = "https://api.deepseek.com/chat/completions"
    max_tokens_param = "max_tokens"
    #: DeepSeek도 thinking 토큰이 max_tokens에서 나간다. 실측(2026-08-02, v4-flash
    #: thinking=on, topic_extraction): 1500 → 전량 추론 소진·출력 0 / 4000 → 정상 /
    #: 8000 → 추론 5,066. 여유를 두되 OpenAI 권고치(25k)만큼은 필요 없다.
    min_output_budget = 12_000

    def __init__(self) -> None:
        self.api_key = settings.deepseek_api_key
        self.model = settings.deepseek_model
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set")

    def _augment_payload(self, payload: Dict[str, Any]) -> None:
        """DeepSeek V4 thinking 토글 (config). off면 reasoning 토큰 생성을 끈다 (4~8배 빠름).
        on이면 reasoning_effort를 함께 보내고, thinking 모드가 무시하는 sampling 파라미터를 제거한다
        (docs: thinking 시 temperature/top_p/presence_penalty/frequency_penalty 무효). 미지정이면 API 기본값."""
        thinking = THINKING_OVERRIDE.get() or settings.deepseek_thinking   # task-local override 우선
        if thinking == "off":
            payload["thinking"] = {"type": "disabled"}
        elif thinking == "on":
            payload["thinking"] = {"type": "enabled"}
            payload["reasoning_effort"] = settings.deepseek_reasoning_effort
            for k in ("temperature", "top_p", "presence_penalty", "frequency_penalty"):
                payload.pop(k, None)

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
