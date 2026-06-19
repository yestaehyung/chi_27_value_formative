"""v1 합성 세션 DB 정리 — framing 전환(v2) 후 검수 뷰어를 v2만 보이게.

대상(삭제): mode="simulation" · meta.llmUserAgent · **meta.gtVersion 없음(=v1)** 세션과
그에 딸린 모든 행(턴/노출/피드백/의도/근거엣지/개념링크/앵커매핑/관계/스냅샷/충돌/
페어/LLM로그 등 — session_id/topic_id 컬럼을 가진 전 테이블), 그리고 세션이 모두
사라져 비게 된 "[합성]" participant.

보존: v2 세션(meta.gtVersion="v2"), 참가자 스터디·manual·pscon 세션,
data/synthesis_test|multi/*.md 와 seed/personas_nemotron_profiles.json (v1 기록 파일),
Concept TBox(공유 사전 — v1 기여분이 남지만 사용자 데이터가 아니므로 유지).

  cd backend && .venv/bin/python scripts/delete_v1_synthesis.py          # dry-run: 개수만 출력
  cd backend && .venv/bin/python scripts/delete_v1_synthesis.py --apply  # 실제 삭제

특정 GT 버전 세션을 지울 때(예: GT 파일을 재도출해 기존 세션을 폐기하는 재생성 사이클):
  cd backend && .venv/bin/python scripts/delete_v1_synthesis.py --gt v2          # dry-run
  cd backend && .venv/bin/python scripts/delete_v1_synthesis.py --gt v2 --apply

합성 배치가 도는 중이면 끝난 뒤 실행 권장 (짧은 쓰기 트랜잭션이라 충돌은 안 나지만 안전하게).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/ → import app

from app.db import models  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import Base  # noqa: E402

CHUNK = 500  # SQLite IN 절 파라미터 한도 회피


def _chunks(ids: list[str]):
    for i in range(0, len(ids), CHUNK):
        yield ids[i:i + CHUNK]


def main(apply: bool, gt: str | None) -> None:
    init_db()
    db = SessionLocal()
    try:
        def is_target(s) -> bool:
            m = s.meta or {}
            if not m.get("llmUserAgent"):
                return False
            # 기본: 스탬프 없는 v1 / --gt <버전>: 해당 버전 스탬프 세션
            return m.get("gtVersion") == gt if gt else not m.get("gtVersion")

        targets = [
            s for s in db.query(models.Session).filter(models.Session.mode == "simulation").all()
            if is_target(s)
        ]
        sids = [s.id for s in targets]
        label = f"gtVersion={gt}" if gt else "v1(스탬프 없음)"
        print(f"대상 {label} 합성 세션: {len(sids)}개", flush=True)
        if not sids:
            print("지울 것이 없습니다.", flush=True)
            return

        topic_ids: list[str] = []
        for chunk in _chunks(sids):
            topic_ids += [
                t.id for t in db.query(models.IntentionTopic)
                .filter(models.IntentionTopic.session_id.in_(chunk)).all()
            ]

        # session_id / topic_id 컬럼을 가진 모든 매핑 테이블을 자동 수집
        topic_classes, session_classes = [], []
        for mapper in Base.registry.mappers:
            cls = mapper.class_
            if cls in (models.Session, models.Participant):
                continue
            cols = {c.key for c in mapper.columns}
            if "topic_id" in cols:
                topic_classes.append(cls)
            if "session_id" in cols:
                session_classes.append(cls)

        def wipe(cls, col_name: str, ids: list[str]) -> int:
            col = getattr(cls, col_name)
            n = 0
            for chunk in _chunks(ids):
                q = db.query(cls).filter(col.in_(chunk))
                n += q.count() if not apply else q.delete(synchronize_session=False)
            return n

        # 자식부터: topic 종속 행 → session 종속 행 → 세션
        for cls in topic_classes:
            n = wipe(cls, "topic_id", topic_ids)
            if n:
                print(f"  {cls.__tablename__:32s} (topic_id)   {n:6d}행", flush=True)
        for cls in session_classes:
            n = wipe(cls, "session_id", sids)
            if n:
                print(f"  {cls.__tablename__:32s} (session_id) {n:6d}행", flush=True)
        n = wipe(models.Session, "id", sids)
        print(f"  {'sessions':32s}              {n:6d}행", flush=True)

        # 세션이 모두 사라진 합성 participant 정리 (실제 스터디 참가자는 label이 다름)
        for p in db.query(models.Participant).filter(models.Participant.label.like("[합성%")).all():
            remaining = (
                db.query(models.Session)
                .filter(models.Session.participant_id == p.id)
                .filter(models.Session.id.notin_(sids))  # 삭제 대상 제외 후 남는 세션
                .count()
            )
            if remaining == 0:
                print(f"  participant {p.id} ({p.label}) — 남는 세션 0개, 삭제 대상", flush=True)
                if apply:
                    db.delete(p)

        if apply:
            db.commit()
            print("\n삭제 완료.", flush=True)
        else:
            print("\n(dry-run — 실제로 지우려면 --apply 를 붙여 다시 실행)", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    gt_arg = sys.argv[sys.argv.index("--gt") + 1] if "--gt" in sys.argv else None
    main(apply="--apply" in sys.argv, gt=gt_arg)
