"""축 2 agentic 루프 스모크 — 페인팅 대화 재현 (2026-07-07).

파이프라인에서 렌더러 재해석 모순이 났던 실제 로컬 대화(sess_6ff640260a 턴 6-7:
"패인팅 들어간 건 없나?" → "피하고 싶으시군요" + 그래픽 티 노출)를 agentic 경로로
재생한다. 기대: 해석·응답이 한 컨텍스트 → 모순 소멸.

  cd backend && .venv/bin/python scripts/smoke_agentic_painting.py   # 실 LLM 호출
"""
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ["VC_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="vc_agentic_"), "smoke.db")
os.environ.setdefault("VC_LLM_PROVIDER", "deepseek")
os.environ.setdefault("VC_DEEPSEEK_MODEL", "deepseek-v4-flash")
os.environ["VC_SEED_DIR"] = str(BACKEND / "seed_amazon")
os.environ["VC_TURN_LOOP"] = "agentic"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

UTTERANCES = [
    "남자 티셔츠를 사고 싶어",
    "운동할 때 입을 거예요",
    "좋네요, 혹시 캐주얼하게 학교 갈 때 입는 것도 있을까요?",
    "옷에 패인팅이 들어간건 없나?",
]


def main():
    with TestClient(app) as c:
        # scenarioId="custom" = 자유 대화 (실제 페인팅 세션과 동일하게 시나리오 무제약)
        r = c.post("/api/sessions", json={"mode": "manual", "studyCondition": "correctable",
                                          "scenarioId": "custom",
                                          "customTitle": "티셔츠 자유 탐색",
                                          "customContext": ""})
        assert r.status_code == 200, r.text
        sid = r.json()["sessionId"]
        for utt in UTTERANCES:
            out = c.post(f"/api/sessions/{sid}/turns",
                         json={"role": "user", "content": utt}).json()
            ar = out.get("agentResponse") or {}
            print(f"\n👤 {utt}")
            print(f"🤖 [{ar.get('agentAction')}] {(ar.get('content') or '')[:400]}")
            for p in (out.get("recommendations") or [])[:5]:
                title = p.get("title") or (p.get("product") or {}).get("title") or "?"
                print(f"   - {title[:60]}")
        # llm_calls에 남은 agentic trace 확인
        from app.db import models
        from app.db.database import SessionLocal

        db = SessionLocal()
        try:
            for call in db.query(models.LLMCall).filter(
                    models.LLMCall.session_id == sid,
                    models.LLMCall.task == "agentic_loop").all():
                print("TRACE:", call.response)
        finally:
            db.close()


if __name__ == "__main__":
    main()
