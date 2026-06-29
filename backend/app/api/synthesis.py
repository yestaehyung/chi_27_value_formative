"""합성(LLM user agent) 대화 검수 뷰어 — read-only.

run_llm_simulations*.py(단일 세션)와 run_multi_session_simulations*.py(멀티 세션 —
Participant 묶음)가 만든 `mode=simulation` · `meta.llmUserAgent` 세션을, 주입 GT
프로필과 `personaId`로 조인해 "주입한 숨은 의도 ↔ 시스템이 복원한 것"을 **나란히**
보여준다. 자동 판정(✅/❌ match)은 내려주지 않는다 — 평가는 사람·LLM이 나중에
별도 단계로 한다 (생성 단계는 평가 가능성만 보존).

GT 버전 (meta.gtVersion으로 구분):
- v1 (스탬프 없음): persona 단독 GT — personas_nemotron_profiles.json
- v2: persona×scenario GT — personas_nemotron_profiles_v2.json. 세션마다 그 시나리오의
  GT가 주입되었으므로, 상세에서 GT 블록이 세션을 따라간다.
은닉 원칙상 GT는 DB에 없다 (llm_user_agent.py 참조) — 파일과 버전 스탬프로 연결한다.
"""
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy import func

from app.db import models, serializers
from app.db.database import SessionLocal
from app.products.seed_loader import get_persona, get_scenario
from app.llm.prompts import SYSTEM_BY_TASK, render_user_context
from app.llm.provider import LLMMessage, get_provider
from app.ontology.anchor_mapper import MOTIVATION_DIMS, TRAIT_ANCHORS

_IN_CHUNK = 800  # SQLite IN(...) 파라미터 한도 회피

router = APIRouter(prefix="/api/synthesis", tags=["synthesis"])

_SEED = Path(__file__).resolve().parents[2] / "seed"
PROFILES_V1_PATH = _SEED / "personas_nemotron_profiles.json"
PROFILES_V2_PATH = _SEED / "personas_nemotron_profiles_v2.json"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _top_anchors(scores: dict | None, k: int = 2) -> list[str]:
    return [a for a, v in sorted((scores or {}).items(), key=lambda kv: -kv[1]) if v and v > 0.1][:k]


def _is_synthesis(sess: models.Session) -> bool:
    return bool((sess.meta or {}).get("llmUserAgent"))


def _normalize_v1(prof: dict) -> dict:
    """v1 persona 단독 GT → 공통 표시 형태."""
    return {
        "gtVersion": "v1",
        "valueLevels": prof.get("traitLevels") or {},
        "motivationLevels": prof.get("motivationTendencies") or {},
        "hiddenIntentions": prof.get("hiddenIntentions") or [],
        "personaDistinction": None,
        "matchRationale": prof.get("matchRationale"),
        "speechStyle": prof.get("speechStyle"),
    }


def _normalize_v2(entry: dict, scenario_id: str | None) -> dict | None:
    gt = (entry.get("scenarios") or {}).get(scenario_id)
    if gt is None:
        return None
    return {
        "gtVersion": "v2",
        "valueLevels": gt.get("valueLevels") or {},
        "motivationLevels": gt.get("motivationLevels") or {},
        "hiddenIntentions": gt.get("hiddenIntentions") or [],
        "personaDistinction": gt.get("personaDistinction"),
        "matchRationale": gt.get("matchRationale"),
        "speechStyle": entry.get("speechStyle"),
    }


def _gt_for_session(sess: models.Session, v1: dict | None, v2: dict | None) -> dict | None:
    """세션에 실제로 주입된 GT — gtVersion 스탬프와 세션 시나리오로 해석."""
    # 직접 실행에서 즉석 도출한 GT는 세션 종료 후 meta.ondemandGt에 post-hoc 기록됨 (복원 무오염).
    od = (sess.meta or {}).get("ondemandGt")
    if od:
        return od
    if (sess.meta or {}).get("gtVersion") == "v2" and v2:
        gt = _normalize_v2(v2, sess.scenario_id)
        if gt:
            return gt
    return _normalize_v1(v1) if v1 else None


def _injected_summary(gt: dict | None) -> dict:
    if not gt:
        return {"valueDominant": [], "motivationHigh": []}
    return {
        "valueDominant": [a for a, lv in (gt.get("valueLevels") or {}).items() if lv == "dominant"],
        "motivationHigh": [d for d, lv in (gt.get("motivationLevels") or {}).items() if lv == "high"],
    }


def _find_sessions(db, pid: str) -> list[models.Session]:
    """이 persona의 LLM 합성 세션 전부 (시간순 — 단일 배치·멀티 세션 모두)."""
    return [
        s
        for s in (
            db.query(models.Session)
            .filter(models.Session.mode == "simulation")
            .order_by(models.Session.started_at.asc())
            .all()
        )
        if _is_synthesis(s) and str((s.meta or {}).get("personaId")) == str(pid)
    ]


def _final_snapshot(db, sid: str):
    return (
        db.query(models.PreferenceStateSnapshot)
        .filter(models.PreferenceStateSnapshot.session_id == sid)
        .order_by(models.PreferenceStateSnapshot.created_at.desc())
        .first()
    )


def _chunks(ids: list[str]):
    for i in range(0, len(ids), _IN_CHUNK):
        yield ids[i:i + _IN_CHUNK]


def _count_by_session(db, model, sids: list[str], *extra) -> dict[str, int]:
    """session_id별 row 수 — GROUP BY 집계 (세션당 count 쿼리 N+1 제거)."""
    out: dict[str, int] = {}
    for chunk in _chunks(sids):
        q = db.query(model.session_id, func.count()).filter(model.session_id.in_(chunk))
        for f in extra:
            q = q.filter(f)
        for sid, n in q.group_by(model.session_id).all():
            out[sid] = n
    return out


def _latest_snapshots(db, sids: list[str]) -> dict[str, models.PreferenceStateSnapshot]:
    """세션별 최신 스냅샷 — sids 전체를 한 번에 받아 Python에서 최신만 추린다."""
    out: dict[str, models.PreferenceStateSnapshot] = {}
    for chunk in _chunks(sids):
        rows = (
            db.query(models.PreferenceStateSnapshot)
            .filter(models.PreferenceStateSnapshot.session_id.in_(chunk))
            .order_by(models.PreferenceStateSnapshot.created_at.asc())
            .all()
        )
        for s in rows:  # asc 정렬이라 마지막이 최신
            out[s.session_id] = s
    return out


def _purchase_sids(db, sids: list[str]) -> set[str]:
    out: set[str] = set()
    for chunk in _chunks(sids):
        out |= {
            sid for (sid,) in db.query(models.FeedbackEvent.session_id)
            .filter(models.FeedbackEvent.session_id.in_(chunk), models.FeedbackEvent.type == "purchase")
            .distinct().all()
        }
    return out


def _cross_session(db, sessions: list[models.Session], v1: dict | None, v2: dict | None) -> dict | None:
    """participant로 묶인 세션 ≥2개 → 세션 횡단 서술 비교 (판정 없음).

    같은 사람이 다른 선택 상황을 거친 기록 — 무엇이 달라지고 무엇이 반복되는지는
    검수자가 읽고 판단한다. participant spec은 반복 패턴의 기억(자연어 미러)이다.
    """
    linked = [s for s in sessions if s.participant_id]
    if len(linked) < 2:
        return None
    per = []
    for s in linked:
        snap = _final_snapshot(db, s.id)
        scenario = get_scenario(s.scenario_id) or {}
        gt = _gt_for_session(s, v1, v2)
        per.append({
            "sessionId": s.id,
            "scenarioId": s.scenario_id,
            "scenarioTitle": scenario.get("title") or s.scenario_id,
            "injected": _injected_summary(gt),
            "topTraits": _top_anchors(snap.anchor_scores if snap else {}),
            "topMotivations": _top_anchors(snap.motivation_scores if snap else {}),
        })
    part = db.get(models.Participant, linked[0].participant_id)
    return {
        "participantId": linked[0].participant_id,
        "perSession": per,
        "specMarkdown": part.spec_markdown if part else None,
        "specVersion": part.spec_version if part else None,
    }


@router.get("/runs")
def list_runs():
    """합성 페르소나 목록 — 카드 그리드용 요약 (persona당 세션 1~N개, 판정 없음)."""
    v1_all = _load_json(PROFILES_V1_PATH)
    v2_all = _load_json(PROFILES_V2_PATH)
    pids = sorted(set(v1_all) | set(v2_all))
    db = SessionLocal()
    try:
        # 세션 전체를 한 번만 훑어 persona별로 묶는다 (persona당 재스캔 방지)
        by_pid: dict[str, list[models.Session]] = {}
        for s in (
            db.query(models.Session)
            .filter(models.Session.mode == "simulation")
            .order_by(models.Session.started_at.asc())
            .all()
        ):
            if _is_synthesis(s):
                by_pid.setdefault(str((s.meta or {}).get("personaId")), []).append(s)

        # 카드에 필요한 집계를 세션 전체에 대해 4개의 묶음 쿼리로 — 세션당 N+1 제거.
        # (멀티 배치가 도는 동안 SQLite 쓰기 부하와 겹쳐 느려지던 지점)
        all_sids = [s.id for ss in by_pid.values() for s in ss]
        turn_counts = _count_by_session(db, models.Turn, all_sids, models.Turn.role == "user_agent")
        topic_counts = _count_by_session(
            db, models.IntentionTopic, all_sids,
            models.IntentionTopic.status.notin_(["rejected_by_user", "inactive"]))
        purchased = _purchase_sids(db, all_sids)
        # 스냅샷은 각 persona의 '대표' 세션에만 필요 → 대표 sid만 모아 한 번에
        display_by_pid: dict[str, list[models.Session]] = {}
        for pid, sessions in by_pid.items():
            linked = [s for s in sessions if s.participant_id]
            display_by_pid[pid] = linked if len(linked) >= 2 else sessions
        snaps = _latest_snapshots(db, [d[0].id for d in display_by_pid.values() if d])

        rows = []
        for pid in pids:
            v1 = v1_all.get(pid)
            v2 = v2_all.get(pid)
            persona = get_persona(pid) or {}
            planned_sid = (v2 or {}).get("matchedScenarioId") or (v1 or {}).get("scenarioId")
            planned_scenario = get_scenario(planned_sid) or {}
            planned_gt = (_normalize_v2(v2, planned_sid) if v2 else None) or (_normalize_v1(v1) if v1 else None)
            sessions = by_pid.get(str(pid), [])
            multi_count = sum(1 for s in sessions if s.participant_id)
            name = (v2 or v1 or {}).get("personaName") or persona.get("name") or pid
            row = {
                "personaId": pid,
                "name": name,
                "occupation": (persona.get("demographics") or {}).get("occupation"),
                "scenarioId": planned_sid,
                "scenarioTitle": planned_scenario.get("title"),
                "scenarioTitles": [planned_scenario.get("title") or planned_sid],
                "injected": _injected_summary(planned_gt),
                "gtVersion": (planned_gt or {}).get("gtVersion"),
                "synthesized": bool(sessions),
                "sessionCount": len(sessions),
                "multiCount": multi_count,
                "sessionId": None,
                "recoveredTop": [],
                "topMotivations": [],
                "userTurns": 0,
                "topics": 0,
                "ended": None,
            }
            if sessions:
                # 카드 요약은 participant로 묶인 쌍 기준 (단일 배치 세션과 실험이 섞이지 않게);
                # 묶인 쌍이 없으면 전체. 상세의 세션 토글에는 모든 세션이 그대로 나온다.
                display = display_by_pid[str(pid)]
                first = display[0]
                snap = snaps.get(first.id)
                row.update({
                    "scenarioTitles": [get_scenario(s.scenario_id).get("title") if get_scenario(s.scenario_id)
                                       else s.scenario_id for s in display],
                    "sessionId": first.id,
                    "injected": _injected_summary(_gt_for_session(first, v1, v2)),
                    "gtVersion": (_gt_for_session(first, v1, v2) or {}).get("gtVersion"),
                    "recoveredTop": _top_anchors(snap.anchor_scores if snap else {}),
                    "topMotivations": _top_anchors(snap.motivation_scores if snap else {}),
                    "userTurns": sum(turn_counts.get(s.id, 0) for s in display),
                    "topics": sum(topic_counts.get(s.id, 0) for s in display),
                    "ended": "purchase" if first.id in purchased else "explore",
                })
            rows.append(row)
        # 합성된 것 먼저, 이름순 — 판정 기반 정렬 없음 (검수 우선순위는 사람이 정한다)
        rows.sort(key=lambda r: (not r["synthesized"], r["name"]))
        return {
            "available": bool(pids),
            "count": len(rows),
            "synthesizedCount": sum(1 for r in rows if r["synthesized"]),
            "multiSessionCount": sum(1 for r in rows if r["multiCount"] >= 2),
            "runs": rows,
        }
    finally:
        db.close()


def _session_detail(db, sess: models.Session, v1: dict | None, v2: dict | None) -> dict:
    """단일 세션 상세 — 그 세션에 주입된 GT + 대화(transcript) + 복원."""
    turns = (
        db.query(models.Turn).filter_by(session_id=sess.id)
        .order_by(models.Turn.created_at).all()
    )
    feedback = (
        db.query(models.FeedbackEvent).filter_by(session_id=sess.id)
        .order_by(models.FeedbackEvent.created_at).all()
    )
    product_ids = {f.product_id for f in feedback if f.product_id}
    products = (
        {p.id: p for p in db.query(models.Product).filter(models.Product.id.in_(product_ids)).all()}
        if product_ids else {}
    )
    snap = _final_snapshot(db, sess.id)
    topics = (
        db.query(models.IntentionTopic).filter_by(session_id=sess.id)
        .filter(models.IntentionTopic.status.notin_(["rejected_by_user", "inactive"]))
        .order_by(models.IntentionTopic.created_at).all()
    )

    # 대화 + 행동을 시간순으로 한 줄기로 합친다 (.md transcript의 라이브 버전)
    stream: list[tuple] = [("turn", t.created_at or datetime.min, t) for t in turns]
    stream += [("event", f.created_at or datetime.min, f) for f in feedback]
    stream.sort(key=lambda e: e[1])
    transcript = []
    for kind, _, obj in stream:
        if kind == "turn":
            transcript.append({"kind": "turn", "turn": serializers.turn_to_dict(obj)})
        else:
            title = products[obj.product_id].title if obj.product_id in products else obj.product_id
            transcript.append({
                "kind": "event",
                "feedbackType": obj.type,
                "productTitle": title,
                "reasonText": obj.reason_text,
            })

    purchase_fb = next((f for f in feedback if f.type == "purchase"), None)
    purchased_title = (
        products[purchase_fb.product_id].title
        if purchase_fb and purchase_fb.product_id in products else None
    )
    scenario = get_scenario(sess.scenario_id) or {}
    gt = _gt_for_session(sess, v1, v2)

    return {
        "sessionId": sess.id,
        "scenarioId": sess.scenario_id,
        "scenarioTitle": scenario.get("title") or sess.scenario_id,
        "multi": sess.participant_id is not None,
        "ended": "purchase" if purchase_fb else "explore",
        "purchasedTitle": purchased_title,
        "gt": gt,
        "injected": _injected_summary(gt),
        "transcript": transcript,
        "recovered": {
            "anchorScores": (snap.anchor_scores if snap else {}),
            "anchorBreakdown": (snap.anchor_breakdown if snap else {}),
            "motivationScores": (snap.motivation_scores if snap else {}),
            "topics": [
                {
                    "label": t.label,
                    "explicitness": t.explicitness,
                    "kind": (t.hints or {}).get("kind"),
                    "source": t.source,
                }
                for t in topics
            ],
        },
    }


@router.get("/runs/{persona_id}")
def get_run(persona_id: str):
    """합성 대화 상세 — 서사 + 세션별 주입 GT/대화/복원 + 세션 횡단 서술 비교."""
    v1 = _load_json(PROFILES_V1_PATH).get(persona_id)
    v2 = _load_json(PROFILES_V2_PATH).get(persona_id)
    if v1 is None and v2 is None:
        raise HTTPException(404, "no synthesis profile for this persona")
    persona = get_persona(persona_id) or {}
    planned_sid = (v2 or {}).get("matchedScenarioId") or (v1 or {}).get("scenarioId")
    planned_scenario = get_scenario(planned_sid) or {}

    base = {
        "personaId": persona_id,
        "name": (v2 or v1 or {}).get("personaName") or persona.get("name") or persona_id,
        "personaNarrative": persona.get("personaNarrative"),
        "demographics": persona.get("demographics") or {},
        "scenario": {"id": planned_sid, "title": planned_scenario.get("title")},
        # 합성 전 카드용 기본 GT (합성 후에는 세션별 gt가 우선)
        "gt": (_normalize_v2(v2, planned_sid) if v2 else None) or (_normalize_v1(v1) if v1 else None),
    }

    db = SessionLocal()
    try:
        sessions = _find_sessions(db, persona_id)
        if not sessions:
            return {**base, "synthesized": False, "sessions": [], "crossSession": None}

        return {
            **base,
            "synthesized": True,
            "sessions": [_session_detail(db, s, v1, v2) for s in sessions],
            "crossSession": _cross_session(db, sessions, v1, v2),
        }
    finally:
        db.close()


# ── 온디맨드 직접 실행 (LLM user agent 합성) — /simulate "직접 실행" 탭 ──
# 선택한 persona × 시나리오로 합성. 실 LLM이라 수 분 → 백그라운드+폴링.
# 미리 만든 v2 GT가 없으면(라이브 seed_naver 등) 그 자리에서 GT를 도출해 주입한다.
# (단일 worker 가정의 in-memory 상태 — Railway nixpacks 기본 1 worker.)
_RUNNING_SYNTH: set[str] = set()
_VALUE_LEVELS = ("dominant", "present", "trace")
_MOT_LEVELS = ("high", "medium", "low")


def _validate_gt(out: dict) -> dict | None:
    """derive_persona_profiles_v2._validate와 동일 계약 (TCV5 levels + 동기7 + 의도/구분)."""
    values = out.get("valueLevels") or {}
    if not all(values.get(a) in _VALUE_LEVELS for a in TRAIT_ANCHORS):
        return None
    motiv = {d: lv for d, lv in (out.get("motivationLevels") or {}).items()
             if d in MOTIVATION_DIMS and lv in _MOT_LEVELS}
    if len(motiv) < 3:
        return None
    for d in MOTIVATION_DIMS:
        motiv.setdefault(d, "low")
    if not out.get("hiddenIntentions") or not out.get("personaDistinction"):
        return None
    return {
        "valueLevels": {a: values[a] for a in TRAIT_ANCHORS},
        "motivationLevels": motiv,
        "hiddenIntentions": out["hiddenIntentions"],
        "personaDistinction": out["personaDistinction"],
        "matchRationale": out.get("matchRationale") or "",
    }


async def _derive_gt(provider, persona: dict, scenario: dict) -> dict | None:
    """(persona × scenario) GT 즉석 도출 — derive_persona_profiles_v2.derive_one과 동일 프롬프트/계약."""
    context = {
        "persona": {k: persona.get(k) for k in ("name", "personaNarrative", "demographics", "narratives")},
        "scenario": {k: scenario.get(k) for k in ("id", "title", "targetCategory", "initialUserNeed", "description")},
    }
    out = await provider.generate_json(
        [LLMMessage(role="system", content=SYSTEM_BY_TASK["persona_profile"]),
         LLMMessage(role="user", content=render_user_context(context))],
        task="persona_profile", context=context, temperature=0.8,
    )
    return _validate_gt(out) if isinstance(out, dict) else None


async def _run_synthesis_bg(persona: dict, scenario: dict, pre_gt: dict | None,
                            speech_style: str | None, max_turns: int, pid: str) -> None:
    from app.agents.judge import judge_causal_relations
    from app.agents.llm_user_agent import run_llm_simulation

    db = SessionLocal()
    try:
        gt = pre_gt or await _derive_gt(get_provider(), persona, scenario)
        if not gt:
            import logging
            logging.error("synthesis: GT 도출 실패 (persona=%s, scenario=%s)", pid, scenario.get("id"))
            return
        profile = {**gt, "speechStyle": speech_style}
        res = await run_llm_simulation(db, persona, profile, scenario, max_turns, gt_version="v2")
        # 즉석 도출 GT는 세션 종료 후 meta에 post-hoc 기록 — 뷰어 '주입 GT'용. 세션이 끝났으므로
        # service agent 복원엔 영향 없음(GT를 라이브 중 meta에 두면 안 된다는 원칙과 양립).
        if not pre_gt:
            sess = db.get(models.Session, res["sessionId"])
            if sess:
                sess.meta = {**(sess.meta or {}), "ondemandGt": {**gt, "gtVersion": "v2-ondemand"}}
                db.commit()
        await judge_causal_relations(res["sessionId"])
    except Exception:  # noqa: BLE001 — 백그라운드: 실패해도 서버는 계속
        import logging
        logging.exception("synthesis on-demand run failed (persona=%s)", pid)
    finally:
        db.close()
        _RUNNING_SYNTH.discard(pid)


@router.post("/run")
async def run_synthesis(req: dict, background_tasks: BackgroundTasks):
    """선택한 persona × 시나리오로 LLM 합성을 즉시 시작(백그라운드). 미리 만든 v2 GT가 있으면 쓰고,
    없으면 그 자리에서 GT를 도출해 주입(라이브 seed_naver에서도 동작). 진행은 /run-status로 폴링.
    body: {personaId, scenarioId, maxTurns?}."""
    pid = (req or {}).get("personaId")
    if not pid:
        raise HTTPException(400, "personaId required")
    persona = get_persona(pid)
    if not persona:
        raise HTTPException(404, f"unknown persona: {pid}")
    entry = _load_json(PROFILES_V2_PATH).get(pid) or {}
    sid = req.get("scenarioId") or entry.get("matchedScenarioId")
    scenario = get_scenario(sid) if sid else None
    if not scenario:
        raise HTTPException(400, f"scenario not resolvable in current seed: {sid}")
    pre_gt = (entry.get("scenarios") or {}).get(sid)   # 있으면 사용, 없으면 백그라운드에서 즉석 도출
    if pid in _RUNNING_SYNTH:
        return {"status": "already_running", "personaId": pid, "scenarioId": sid}
    max_turns = max(2, min(12, int(req.get("maxTurns") or 6)))
    _RUNNING_SYNTH.add(pid)
    background_tasks.add_task(_run_synthesis_bg, persona, scenario, pre_gt,
                             entry.get("speechStyle"), max_turns, pid)
    return {"status": "started", "personaId": pid, "scenarioId": sid,
            "maxTurns": max_turns, "gtSource": "pre-derived" if pre_gt else "on-the-fly"}


@router.get("/run-status")
def run_synthesis_status(personaId: str):
    """폴링용 — 해당 persona가 현재 합성 중인지. 끝나면 프론트가 /runs/{pid}로 결과를 읽는다."""
    return {"running": personaId in _RUNNING_SYNTH}
