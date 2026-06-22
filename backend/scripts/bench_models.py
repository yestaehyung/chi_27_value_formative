"""Empirical latency benchmark: deepseek-v4-flash vs -pro, reasoning on/off.

Sends the SAME realistic topic-extraction-style JSON prompt to each model/config
and measures wall-clock latency. Reads the API key from the loaded settings — never
prints it. Run from backend/:  .venv/bin/python scripts/bench_models.py
"""
import asyncio
import statistics
import time

import httpx

from app.core.config import settings

# A realistic payload: system rubric + a Korean shopping utterance, JSON-mode out.
SYSTEM = (
    "당신은 쇼핑 대화에서 사용자의 숨은 의도(가치 기준)를 추출하는 분석기다. "
    "발화에서 의도 토픽을 뽑아 JSON으로만 답하라. 각 토픽은 label, description, "
    "priority(low/medium/high/must_have), confidenceLevel(directly_stated/strong_inference/"
    "weak_inference)을 가진다. 추측을 남발하지 말고 근거 인용을 붙여라."
)
USER = (
    '발화: "운동할 때 쓸 수 있는 가성비 좋은 이어폰 추천해줘. 너무 비싸지 않으면서도 '
    '오래 쓸 수 있으면 좋겠어. 친구 선물로 줄 거라 너무 싸구려처럼 보이는 건 싫어."\n\n'
    'JSON 형식: {"topics": [{"label": "...", "description": "...", "priority": "...", '
    '"confidenceLevel": "...", "quote": "..."}]}'
)

# (model, reasoning_effort or None). DeepSeek V4 accepts reasoning_effort like the gpt-5 family.
CONFIGS = [
    ("deepseek-v4-flash", None),
    ("deepseek-v4-flash", "high"),
    ("deepseek-v4-pro", None),
    ("deepseek-v4-pro", "high"),
]
N_RUNS = 3  # repeats per config (network jitter) — take median


async def one_call(client: httpx.AsyncClient, model: str, effort: str | None) -> tuple[float, int, str]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER},
        ],
        "max_tokens": 1500,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
    }
    if effort is not None:
        payload["reasoning_effort"] = effort
    t = time.perf_counter()
    resp = await client.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
        json=payload,
    )
    elapsed = time.perf_counter() - t
    resp.raise_for_status()
    data = resp.json()
    usage = data.get("usage", {})
    completion_tokens = usage.get("completion_tokens", 0)
    reasoning_tokens = usage.get("completion_tokens_details", {}).get("reasoning_tokens", 0)
    note = f"out={completion_tokens}tok"
    if reasoning_tokens:
        note += f" (reasoning={reasoning_tokens})"
    return elapsed, completion_tokens, note


async def main() -> None:
    print(f"Benchmarking {len(CONFIGS)} configs × {N_RUNS} runs each (median reported)\n")
    print(f"{'model':<20} {'reasoning':<10} {'median(s)':<10} {'min':<7} {'max':<7} notes")
    print("-" * 78)
    async with httpx.AsyncClient(timeout=180) as client:
        for model, effort in CONFIGS:
            times = []
            note = ""
            for _ in range(N_RUNS):
                try:
                    elapsed, _, note = await one_call(client, model, effort)
                    times.append(elapsed)
                except httpx.HTTPStatusError as e:
                    note = f"HTTP {e.response.status_code}: {e.response.text[:80]}"
                    break
                except Exception as e:  # noqa: BLE001
                    note = f"ERR: {type(e).__name__}: {str(e)[:60]}"
                    break
            label = effort or "off"
            if times:
                print(f"{model:<20} {label:<10} {statistics.median(times):<10.2f} "
                      f"{min(times):<7.2f} {max(times):<7.2f} {note}")
            else:
                print(f"{model:<20} {label:<10} {'—':<10} {'':<7} {'':<7} {note}")


if __name__ == "__main__":
    asyncio.run(main())
