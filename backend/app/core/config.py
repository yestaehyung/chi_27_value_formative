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
        # VC_RESEED=1 → 시작 시 상품 풀만 시드에서 강제 재로드 (참가자·세션 데이터는 보존).
        # 배포 DB(볼륨)는 상품이 이미 있으면 시드를 안 읽으므로, 상품 데이터를 바꾼 뒤
        # 이 플래그로 한 번 켜고 재배포 → 반영되면 끈다. (기본 off — 실수 방지)
        self.reseed_products = os.environ.get("VC_RESEED", "").strip() in ("1", "true", "yes")
        # VC_SEED_UPSERT=1 → 시작 시 시드의 *새 상품만* INSERT (기존 상품/노출/피드백 보존, 삭제 0건).
        # reseed의 비파괴 대안 — 풀에 N개만 추가할 때. 반영 후 끈다. (기본 off)
        self.seed_upsert = os.environ.get("VC_SEED_UPSERT", "").strip() in ("1", "true", "yes")
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
