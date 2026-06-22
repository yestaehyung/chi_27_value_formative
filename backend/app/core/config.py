"""Application settings. Environment-overridable for tests / deployment.

A `.env` file in the backend directory is loaded at import time (existing
environment variables take precedence, so tests can still force the mock).
"""
import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BACKEND_DIR / ".env")


class Settings:
    def __init__(self) -> None:
        self.db_path = Path(os.environ.get("VC_DB_PATH", str(BACKEND_DIR / "valuecommit.db")))
        self.seed_dir = Path(os.environ.get("VC_SEED_DIR", str(BACKEND_DIR / "seed")))
        self.export_dir = Path(os.environ.get("VC_EXPORT_DIR", str(BACKEND_DIR / "exports")))
        # "mock" (deterministic demo rules) | "openai" | "deepseek" | "anthropic"
        self.llm_provider = os.environ.get("VC_LLM_PROVIDER", "mock")
        self.openai_api_key = os.environ.get("OPENAI_API_KEY")
        self.openai_model = os.environ.get("VC_OPENAI_MODEL", "gpt-5-nano")
        # gpt-5 family reasoning effort: minimal | low | medium | high
        self.openai_reasoning_effort = os.environ.get("VC_OPENAI_REASONING_EFFORT", "minimal")
        # 의미 기반 상품 검색용 임베딩 (chat provider와 무관하게 OpenAI 사용 — DeepSeek는 임베딩 없음)
        self.embedding_model = os.environ.get("VC_EMBEDDING_MODEL", "text-embedding-3-small")
        # DeepSeek — OpenAI-compatible API (https://api.deepseek.com)
        self.deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY")
        self.deepseek_model = os.environ.get("VC_DEEPSEEK_MODEL", "deepseek-chat")
        # DeepSeek V4 thinking(추론) 토글 — "on" | "off" (기본 off = 속도 우선).
        # off면 thinking={"type":"disabled"}를 보내 reasoning 토큰 생성을 막아 4~8배 빠르다.
        # 추출 품질이 떨어지면 on으로 되돌려 A/B 비교할 것. (실측: flash 1.4s↔6.3s, pro 2s↔16s)
        self.deepseek_thinking = os.environ.get("VC_DEEPSEEK_THINKING", "off").lower()
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.anthropic_model = os.environ.get("VC_ANTHROPIC_MODEL", "claude-sonnet-4-6")
        # Judge 전용 provider (M5 — 검증 독립성: service agent와 다른 모델 권장).
        # 미설정이면 주 provider를 그대로 쓴다 (mock 환경 포함).
        self.judge_provider = os.environ.get("VC_JUDGE_PROVIDER")
        self.cors_origins = os.environ.get(
            "VC_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")


settings = Settings()
