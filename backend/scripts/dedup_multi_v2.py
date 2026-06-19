"""멀티 세션 중복 정리 — 중복 실행이 겹친 동안 한 participant에 세션 쌍이
여러 번 생긴 경우를 정리한다 (정상은 participant당 멀티 세션 2개).

규칙: 각 participant의 멀티 합성 세션을 시나리오별로 묶어, **시나리오마다 가장
최근 세션 하나만 남기고** 나머지(오래된 중복)를 딸린 행과 함께 삭제한다.
→ 결과적으로 participant당 서로 다른 시나리오 2개 = 정상 쌍.

  cd backend && .venv/bin/python scripts/dedup_multi_v2.py          # dry-run
  cd backend && .venv/bin/python scripts/dedup_multi_v2.py --apply  # 실제 삭제

삭제 후 영향받은 participant의 spec을 재생성한다. 배치가 끝난 뒤 실행할 것.
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/ → import app

from app.db import models  # noqa: E402
from app.db.database import SessionLocal, init_db  # noqa: E402
from app.db.models import Base  # noqa: E402

CHUNK = 500


def _chunks(ids):
    for i in range(0, len(ids), CHUNK):
        yield ids[i:i + CHUNK]


def main(apply: bool) -> None:
    init_db()
    db = SessionLocal()
    try:
        multi = [
            s for s in db.query(models.Session).filter(models.Session.mode == "simulation").all()
            if (s.meta or {}).get("llmUserAgent") and s.participant_id
        ]
        by_part = defaultdict(list)
        for s in multi:
            by_part[s.participant_id].append(s)

        # 삭제 대상 세션 = 시나리오별 최신 1개를 제외한 나머지 (중복 participant만)
        del_sessions = []
        affected = []
        for pid, sessions in by_part.items():
            if len(sessions) <= 2:
                continue
            affected.append(pid)
            by_scenario = defaultdict(list)
            for s in sessions:
                by_scenario[s.scenario_id].append(s)
            for sid, group in by_scenario.items():
                group.sort(key=lambda s: s.started_at or s.id)  # 오래된 → 최신
                keep = group[-1]
                drop = group[:-1]
                for s in drop:
                    del_sessions.append(s)
                part_name = pid
                print(f"  {part_name} · {sid}: {len(group)}개 → 1개 유지({keep.id}), {len(drop)}개 삭제", flush=True)

        if not del_sessions:
            print("중복 없음 — 정리할 것이 없습니다.", flush=True)
            return
        sids = [s.id for s in del_sessions]
        print(f"\n삭제 대상 세션 {len(sids)}개 · 영향 participant {len(affected)}명", flush=True)

        # 딸린 행 자동 수집 (delete_v1_synthesis와 동일 패턴)
        topic_ids = []
        for chunk in _chunks(sids):
            topic_ids += [t.id for t in db.query(models.IntentionTopic)
                          .filter(models.IntentionTopic.session_id.in_(chunk)).all()]
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

        def wipe(cls, col_name, ids):
            col = getattr(cls, col_name)
            n = 0
            for chunk in _chunks(ids):
                q = db.query(cls).filter(col.in_(chunk))
                n += q.count() if not apply else q.delete(synchronize_session=False)
            return n

        for cls in topic_classes:
            n = wipe(cls, "topic_id", topic_ids)
            if n:
                print(f"  {cls.__tablename__:30s}(topic_id)   {n:5d}", flush=True)
        for cls in session_classes:
            n = wipe(cls, "session_id", sids)
            if n:
                print(f"  {cls.__tablename__:30s}(session_id) {n:5d}", flush=True)
        n = wipe(models.Session, "id", sids)
        print(f"  {'sessions':30s}             {n:5d}", flush=True)

        if apply:
            db.commit()
            # 영향받은 participant spec 재생성 (세션 삭제로 stale)
            try:
                from app.spec_builder import build_participant_spec
                for pid in affected:
                    part = db.get(models.Participant, pid)
                    if part is not None:
                        part.spec_markdown = build_participant_spec(db, pid)
                        part.spec_version = (part.spec_version or 0) + 1
                db.commit()
                print(f"\nspec 재생성 {len(affected)}명 완료.", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"\n(spec 재생성 건너뜀: {e})", flush=True)
            print("삭제 완료.", flush=True)
        else:
            print("\n(dry-run — 실제로 지우려면 --apply)", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main(apply="--apply" in sys.argv)
