"""PSCon CRS dataset viewer + precomputed analysis (read-only on the web).

Dataset is a sibling (../../PSCon/dataset/conversation_en_fully_rated.json).
Analysis is precomputed OFFLINE in batch by `scripts/analyze_pscon.py` (writes
`backend/data/pscon_analysis.json`); the web just visualizes the stored results
*instantly* — no per-request LLM wait. `analyze_one_conversation` is the shared
single-conversation analyzer the batch script reuses.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.core.ids import new_id
from app.db import models
from app.db.database import SessionLocal
from app.llm.provider import get_provider
from app.preference_commit.commit_engine import run_preference_commit

router = APIRouter(prefix="/api/pscon", tags=["pscon"])

# Safe default: handle environments where repo siblings aren't available (Railway)
_FILE_DIR = Path(__file__).resolve().parents[2]  # backend/
_DEFAULT_PSCON = _FILE_DIR.parent / "PSCon" / "dataset" / "conversation_en_fully_rated.json"
if _DEFAULT_PSCON.exists():
    DEFAULT_PATH = _DEFAULT_PSCON
else:
    DEFAULT_PATH = Path("/dev/null")  # Sentinel for "not available"

PSCON_PATH = Path(os.environ.get("VC_PSCON_PATH", str(DEFAULT_PATH)))
_RESULTS_DEFAULT = _FILE_DIR / "data" / "pscon_analysis.json"
RESULTS_PATH = Path(
    os.environ.get("VC_PSCON_ANALYSIS", str(_RESULTS_DEFAULT))
)


@lru_cache(maxsize=1)
def _load() -> list:
    if not PSCON_PATH.exists():
        return []
    return json.loads(PSCON_PATH.read_text(encoding="utf-8"))


def _rating_map(turns: list) -> dict:
    m: dict = {}
    for t in turns:
        for pr in (t.get("user_rating") or []):
            s = pr.get("product_rate") or ""
            pid = pr.get("product_id")
            if not pid:
                continue
            if "(liked)" in s:
                m[pid] = "liked"
            elif "(disliked)" in s:
                m[pid] = "disliked"
    return m


@lru_cache(maxsize=1)
def _index() -> tuple:
    out = []
    for c in _load():
        turns = c.get("conversation", []) or []
        first_user = next((t.get("content") for t in turns if t.get("role") == "user"), "")
        first_kw = next(
            (t.get("keywords") for t in turns if t.get("role") == "user" and t.get("keywords")), []
        )
        rm = _rating_map(turns)
        out.append({
            "convId": c.get("conv_id"),
            "turnCount": len(turns),
            "firstUserMessage": first_user,
            "keywords": first_kw,
            "recommendTurns": sum(1 for t in turns if t.get("recommended_products")),
            "liked": sum(1 for v in rm.values() if v == "liked"),
            "disliked": sum(1 for v in rm.values() if v == "disliked"),
        })
    return tuple(out)


def _results() -> dict:
    """배치 분석 결과를 매번 새로 읽는다 (배치가 점증적으로 쓰므로 캐시 X)."""
    if RESULTS_PATH.exists():
        try:
            return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return {}
    return {}


# ── 단일 대화 분석 (배치 스크립트가 재사용하는 핵심) ───────────────────────────
async def analyze_one_conversation(conv: dict) -> dict:
    """PSCon user 발화들을 우리 run_preference_commit 파이프라인에 흘려보내
    anchor_scores / topics 를 뽑아 dict 로 반환한다 (실 LLM 호출)."""
    db = SessionLocal()
    try:
        user_turns = [
            t["content"] for t in conv.get("conversation", [])
            if t.get("role") == "user" and t.get("content")
        ]
        session = models.Session(
            id=new_id("sess"), mode="pscon", scenario_id="pscon",
            current_stage="exploration", status="analyzing",
            meta={"psconConvId": conv.get("conv_id")},
        )
        db.add(session)
        db.commit()
        provider = get_provider()
        for idx, content in enumerate(user_turns):
            turn = models.Turn(
                id=new_id("turn"), session_id=session.id,
                turn_index=idx, role="user", content=content,
            )
            db.add(turn)
            db.commit()
            await run_preference_commit(
                db, provider, session,
                turn_ids=[turn.id], feedback_ids=[], source="user_utterance",
            )
        snap = (
            db.query(models.PreferenceStateSnapshot)
            .filter(models.PreferenceStateSnapshot.session_id == session.id)
            .order_by(models.PreferenceStateSnapshot.created_at.desc())
            .first()
        )
        topics = (
            db.query(models.IntentionTopic)
            .filter(models.IntentionTopic.session_id == session.id)
            .filter(models.IntentionTopic.status.notin_(["rejected_by_user", "inactive"]))
            .all()
        )
        session.status = "completed"
        db.commit()
        return {
            "anchorScores": (snap.anchor_scores if snap else {}),
            "anchorBreakdown": (snap.anchor_breakdown if snap else {}),
            # 동기 7축 (M8 — commit engine이 user 발화마다 감지·누적, snapshot에 미러됨)
            "motivationScores": (snap.motivation_scores if snap else {}),
            "topics": [
                {"label": t.label, "explicitness": t.explicitness, "priority": t.priority}
                for t in topics
            ],
            "userTurnCount": len(user_turns),
        }
    finally:
        db.close()


def _richness(r: dict | None) -> tuple[float, list[str]]:
    """데모용 분석 풍부도 — 다양한 축 + 뉘앙스 축(비-Functional/비-Utilitarian)에 가산점.
    교수님께 보여줄 '의미 있는' 대화를 상단에 올리기 위한 정렬 키. topDims는 카드 배지용."""
    if not r:
        return -1.0, []
    av = {k: v for k, v in (r.get("anchorScores") or {}).items() if v > 0.1}
    mv = {k: v for k, v in (r.get("motivationScores") or {}).items() if v > 0.1}
    n_topics = len(r.get("topics") or [])
    # Functional/Utilitarian은 거의 항상 떠서 변별력↓ → 나머지(뉘앙스) 축에 2배 가산
    nuance = sum(1 for k in av if k != "Functional") + sum(1 for k in mv if k != "Utilitarian")
    score = len(av) + len(mv) + 2.0 * nuance + 0.5 * n_topics
    top = [k for k, _ in sorted([*av.items(), *mv.items()], key=lambda kv: -kv[1])[:3]]
    return score, top


@router.get("/conversations")
def list_conversations():
    res = _results()
    convs = []
    for c in _index():
        cid = str(c["convId"])
        score, top = _richness(res.get(cid))
        convs.append({**c, "analyzed": cid in res, "richness": round(score, 1), "topDims": top})
    convs.sort(key=lambda x: x["richness"], reverse=True)  # 분석 풍부순 → 상단
    return {
        "available": PSCON_PATH.exists(),
        "count": len(convs),
        "analyzedCount": len(res),
        "conversations": convs,
    }


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: str):
    for c in _load():
        if str(c.get("conv_id")) == str(conv_id):
            return {
                "convId": c.get("conv_id"),
                "conversation": c.get("conversation", []),
                "ratingMap": _rating_map(c.get("conversation", []) or []),
                "analysis": _results().get(str(conv_id)),
            }
    raise HTTPException(404, "conversation not found")


@router.get("/conversations/{conv_id}/timeline")
def conversation_timeline(conv_id: str):
    """재생(B)용 — 이 대화의 pscon 세션이 *user 턴마다* 남긴 스냅샷 시퀀스.
    배치 분석 때 run_preference_commit이 턴마다 스냅샷을 DB에 남겼으므로
    재실행 없이 그대로 읽는다(read-only). 없으면 available=False."""
    db = SessionLocal()
    try:
        sess = None
        for s in (
            db.query(models.Session)
            .filter(models.Session.mode == "pscon")
            .order_by(models.Session.started_at.desc())
            .all()
        ):
            if str((s.meta or {}).get("psconConvId")) == str(conv_id):
                sess = s
                break
        if sess is None:
            return {"available": False, "steps": []}
        topics = (
            db.query(models.IntentionTopic)
            .filter(models.IntentionTopic.session_id == sess.id)
            .all()
        )
        tmap = {
            t.id: {"label": t.label, "explicitness": t.explicitness, "priority": t.priority}
            for t in topics
        }
        snaps = (
            db.query(models.PreferenceStateSnapshot)
            .filter(models.PreferenceStateSnapshot.session_id == sess.id)
            .order_by(models.PreferenceStateSnapshot.created_at)
            .all()
        )
        steps = [
            {
                "turnIndex": sn.turn_index,
                "anchorScores": sn.anchor_scores or {},
                "anchorBreakdown": sn.anchor_breakdown or {},
                "motivationScores": sn.motivation_scores or {},
                "topics": [tmap[i] for i in (sn.active_topic_ids or []) if i in tmap],
            }
            for sn in snaps
        ]
        return {"available": True, "userTurns": len(steps), "steps": steps}
    finally:
        db.close()


@router.get("/conversations/{conv_id}/evidence")
def conversation_evidence(conv_id: str):
    """라디어 축 클릭 → 대화 하이라이트용. anchor → 그 축을 근거한 대화 turn index 목록.
    체인: anchor ←(AnchorMapping) topic ←(IntentionEvidence) turn ↔ 대화의 user 발화."""
    conv = next((c for c in _load() if str(c.get("conv_id")) == str(conv_id)), None)
    if conv is None:
        raise HTTPException(404, "conversation not found")
    conv_turns = conv.get("conversation", []) or []
    # user 발화의 대화-배열 인덱스 (분석 때 turn_index 순서와 일치)
    user_conv_idx = [
        i for i, t in enumerate(conv_turns) if t.get("role") == "user" and t.get("content")
    ]

    db = SessionLocal()
    try:
        sess = None
        for s in (
            db.query(models.Session).filter_by(mode="pscon")
            .order_by(models.Session.started_at.desc()).all()
        ):
            if str((s.meta or {}).get("psconConvId")) == str(conv_id):
                sess = s
                break
        if sess is None:
            return {"available": False, "byAnchor": {}}
        turnid_order = {
            t.id: t.turn_index for t in db.query(models.Turn).filter_by(session_id=sess.id).all()
        }
        by_anchor: dict[str, set] = {}
        for t in db.query(models.IntentionTopic).filter_by(session_id=sess.id).all():
            idxs = set()
            for e in db.query(models.IntentionEvidence).filter_by(topic_id=t.id).all():
                if e.evidence_type == "turn" and e.evidence_id in turnid_order:
                    order = turnid_order[e.evidence_id]
                    if 0 <= order < len(user_conv_idx):
                        idxs.add(user_conv_idx[order])
            for a in db.query(models.AnchorMapping).filter_by(topic_id=t.id).all():
                by_anchor.setdefault(a.anchor, set()).update(idxs)
        # 동기: 턴별 스냅샷에서 점수가 '증가한' 턴 = 그 동기의 근거 발화 (재실행 없이 derive)
        by_mot: dict[str, set] = {}
        prev: dict[str, float] = {}
        for sn in (
            db.query(models.PreferenceStateSnapshot).filter_by(session_id=sess.id)
            .order_by(models.PreferenceStateSnapshot.created_at).all()
        ):
            cur = sn.motivation_scores or {}
            conv_i = (
                user_conv_idx[sn.turn_index]
                if 0 <= sn.turn_index < len(user_conv_idx) else None
            )
            if conv_i is not None:
                for dim, score in cur.items():
                    if score > prev.get(dim, 0.0) + 1e-9:
                        by_mot.setdefault(dim, set()).add(conv_i)
            prev = cur
        return {
            "available": True,
            "byAnchor": {k: sorted(v) for k, v in by_anchor.items()},
            "byMotivation": {k: sorted(v) for k, v in by_mot.items()},
        }
    finally:
        db.close()
