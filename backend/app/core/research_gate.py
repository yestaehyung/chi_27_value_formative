"""연구자 API 보호 (스터디 분리, 2026-07-02).

research/exports 라우터는 참가자 설문·대화 전체를 읽는 표면이므로, 라이브 스터디
배포에서 키 없이 접근할 수 없어야 한다. main.py가 두 라우터에 dependency로 건다.

규칙 (config.settings):
- VC_RESEARCH_KEY 설정      → X-Research-Key 헤더(또는 ?key= 쿼리) 일치 시 통과.
- 키 미설정 + APP_MODE=study → 항상 403 (fail-closed — 키를 깜빡해도 안 열림).
- 키 미설정 + 그 외(로컬)    → 개방 (기존 개발 동작 유지).
"""
from fastapi import HTTPException, Request

from app.core.config import settings


def require_research_key(request: Request) -> None:
    if settings.research_key:
        supplied = request.headers.get("x-research-key") or request.query_params.get("key")
        if supplied != settings.research_key:
            raise HTTPException(status_code=403, detail="research key required")
        return
    if settings.app_mode == "study":
        raise HTTPException(status_code=403, detail="research API is disabled on the study deployment")
