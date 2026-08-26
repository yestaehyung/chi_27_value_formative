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
        # 하이브리드 검색 가중치 α: rel = α·어휘(text_relevance) + (1-α)·코사인 (2026-07-06).
        # 0 = 코사인 단독(구 동작) / >0 = 임베딩∪BM25 union 후보 + 블렌드. 두 신호 모두 [0,1]이라 정규화 불요.
        # 기본 0.3 — A/B 실측(scripts/ab_hybrid_retrieval.py, 24케이스): 풀 카테고리 정합
        # 0.800→0.906, 선물 맥락어 오염(주얼리→생일캔들 4/30→30/30) 소멸, 0.5는 어휘 과잉으로 열화.
        self.hybrid_alpha = float(os.environ.get("VC_HYBRID_ALPHA", "0.3"))
        # DeepSeek — OpenAI-compatible API (https://api.deepseek.com)
        self.deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY")
        # 요청 base URL — 기본은 DeepSeek 공식 API. SSH 터널로 랩 서버의 OpenAI 호환
        # 서빙을 쓸 때는 .env에서 http://localhost:8001/v1 로 덮어쓴다.
        # (provider가 base + "/chat/completions"로 최종 URL을 조립)
        self.deepseek_base_url = os.environ.get("VC_DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        # 모델: "deepseek-v4-flash"(284B/13B) | "deepseek-v4-pro"(1.6T/49B), 둘 다 1M ctx.
        # (legacy "deepseek-chat"/"deepseek-reasoner"는 2026-07-24 폐기 예정 alias → flash 비추론/추론.)
        self.deepseek_model = os.environ.get("VC_DEEPSEEK_MODEL", "deepseek-v4-flash")
        # DeepSeek V4 thinking(추론) 토글 — "on" | "off" (기본 off = 속도 우선).
        # off → thinking={"type":"disabled"}로 reasoning 토큰 생성을 막아 4~8배 빠르다.
        # on  → thinking={"type":"enabled"} + reasoning_effort; sampling 파라미터(temperature 등)는 무시됨.
        # (실측: flash 1.4s↔6.3s, pro 2s↔16s) 추출 품질 비교는 intention eval로.
        self.deepseek_thinking = os.environ.get("VC_DEEPSEEK_THINKING", "off").lower()
        # thinking on일 때 추론 강도 — "high" | "max" (docs 기준).
        self.deepseek_reasoning_effort = os.environ.get("VC_DEEPSEEK_REASONING_EFFORT", "high")
        self.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.anthropic_model = os.environ.get("VC_ANTHROPIC_MODEL", "claude-sonnet-4-6")
        # Judge 전용 provider (M5 — 검증 독립성: service agent와 다른 모델 권장).
        # 미설정이면 주 provider를 그대로 쓴다 (mock 환경 포함).
        self.judge_provider = os.environ.get("VC_JUDGE_PROVIDER")
        self.cors_origins = os.environ.get(
            "VC_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        # ── 스터디 배포 분리 (2026-07-02) ──────────────────────────────
        # VC_APP_MODE=study → simulations·synthesis·pscon 라우터를 아예 마운트하지
        # 않는다(참가자 스터디 DB에 시뮬 데이터가 구조적으로 못 들어감). 기본 "" =
        # 전체 마운트(로컬 개발·연구). 프론트의 APP_MODE=study와 짝으로 설정한다.
        self.app_mode = os.environ.get("VC_APP_MODE", "").strip().lower()
        # 참가자 화면 언어 (ko | en) — en이면 참가자 대면 LLM 산출물·템플릿이 영어로
        # 전환된다 (core/locale.py + prompts.EN_DIRECTIVES). en 모드는 영어 전용 시드와
        # 영어 searchText를 한 묶음으로 사용한다. 프론트의 NEXT_PUBLIC_STUDY_LOCALE와 짝.
        self.study_locale = os.environ.get("VC_STUDY_LOCALE", "ko").strip().lower()
        # 참가자 카테고리 선택 화면에 노출할 카테고리 (쉼표 구분). 미설정이면 DB의 전체
        # 카테고리 노출(기존 동작). 풀에는 더 많은 카테고리를 두고(검색·향후 확장용)
        # 스터디는 일부만 제공할 때 쓴다 — 예: 풀 15개 중 10개 노출 (2026-08-17).
        self.offered_categories = [
            c.strip() for c in os.environ.get("VC_OFFERED_CATEGORIES", "").split(",") if c.strip()
        ]
        # UI 변형 도장 (예: "ours-v2") — 설정 시 새 세션 meta.uiVariant에 찍혀
        # 탐색 파일럿 데이터가 본실험과 구조적으로 구분된다. 프론트 NEXT_PUBLIC_OURS_V2와
        # 반드시 함께 켜고 함께 끈다 (2026-08-27 ours-v2 파일럿).
        self.ui_variant = os.environ.get("VC_UI_VARIANT", "").strip()
        # 자동 균형 배정에 참여하는 조건 (쉼표 구분). 미설정이면 세 조건 전체(기존 동작).
        # 물결(wave)별 순차 수집에서 이미 수집이 끝난 조건이 minimization 최소가 되는
        # 순간 다시 배정되는 누수를 막는다 — 2026-08-26 b2/ours 배치에서 b1이 8행 누수.
        self.balance_conditions = [
            c.strip() for c in os.environ.get("VC_BALANCE_CONDITIONS", "").split(",") if c.strip()
        ]
        # 연구자 API(research/exports) 보호 키 — 참가자 설문·대화 전체를 읽는 표면.
        # 설정되면 X-Research-Key 헤더(또는 ?key=)가 일치해야 통과. 미설정이면
        # study 모드에선 잠금(fail-closed), 그 외(로컬)는 기존처럼 개방.
        self.research_key = os.environ.get("VC_RESEARCH_KEY", "").strip()


settings = Settings()
