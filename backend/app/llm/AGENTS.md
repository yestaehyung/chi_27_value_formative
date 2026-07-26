# LLM Layer Rules

These rules apply to every file in `backend/app/llm/` and to callers that add or change an LLM task.

## Provider Boundary

- Pipeline code calls `get_provider()` and the `LLMProvider.generate_json(...)` interface.
- Do not instantiate OpenAI, DeepSeek, Anthropic, or raw HTTP clients outside `provider.py`.
- Do not branch on provider names in pipeline stages; provider-specific behavior belongs in provider implementations.
- Pass a stable, descriptive `task` name and structured `context` at every call site. The task name is a runtime dispatch key, not a logging label.
- Keep application decisions outside the transport layer. Providers send requests, enforce response contracts, and return parsed data; callers own domain fallbacks.

## Named Task Contract

Every new pipeline task must be added in the same change to all three registries:

1. `prompts.SYSTEM_BY_TASK`: task instructions and behavioral constraints.
2. `prompts.FORMAT_BY_TASK`: the exact machine-readable JSON shape.
3. `mock_rules.TASK_HANDLERS`: deterministic, network-free behavior for tests and the mock demo.

Keep the key spelling identical across the call site and all registries. If a task is renamed or removed, update all four locations and search for persisted task-name consumers in research logs or exports.

## JSON and Retry Discipline

- `generate_json` returns a JSON object. Prompts must request JSON only, and formats must describe fields, types, and allowed vocabularies explicitly.
- Treat provider output as untrusted at the caller boundary: normalize enumerations, reject unknown identifiers, bound list sizes, and provide a deliberate fallback.
- Do not parse prose with regexes or depend on markdown fences. Keep tolerant extraction centralized in `provider.py`/`json_parser.py`.
- Retries belong on the real asynchronous network call, not on payload builders or domain functions.
- Retry only transient provider/network failures. Preserve the final exception so the caller's documented fallback can run; do not silently fabricate a successful model result.
- Keep retry tests deterministic by replacing the network seam and asserting call count plus final outcome.

## Models and Secrets

- Read provider, model, reasoning, and API-key settings from `app.core.config.settings`.
- Do not hard-code production model names, base URLs, API keys, or deployment secrets in prompts or call sites.
- `VC_LLM_PROVIDER=mock` is the default test boundary. Missing credentials must fail clearly when a real provider is selected.
- DeepSeek's OpenAI-compatible transport is still provider-specific; do not assume every OpenAI option is supported by every model.

## Tests

- Run the backend suite with `VC_LLM_PROVIDER=mock`; normal tests must never require credentials or make external calls.
- Add focused tests for task routing, malformed/partial JSON, vocabulary normalization, fallback behavior, and retry behavior when those seams change.
- Keep mock behavior deterministic and representative of the contract, but do not assert natural-language prompt prose. Assert task routing, JSON structure, and observable pipeline behavior.
- A new task is incomplete if its mock path, real prompt/format contract, or error-path coverage is missing.

## Cost and Network Boundaries

- Real-provider calls are allowed only in explicitly named smoke, evaluation, synthesis, or offline enrichment commands whose documentation warns that they incur network use and cost.
- Never add a real LLM call to import time, migration paths, unit-test setup, or an implicit startup path.
- Bound candidate/context size and output size before sending requests. Avoid duplicate calls when one structured response can serve the same decision.
- Log task/model/timing metadata through existing logging, but never log API keys, authorization headers, hidden synthesis ground truth, or unnecessary participant content.
- Preserve graceful degradation where documented: network or parsing failure may reduce capability, but must not corrupt state or bypass explicit safety and research-integrity constraints.
