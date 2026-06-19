"""persona×scenario GT(v2) 도출 — 가치·동기는 상황의 산물이라는 framing 전환.

v1(personas_nemotron_profiles.json)은 GT 단위가 persona 단독이었다(가치를 사람의
고정 trait처럼 부여). TCV는 선택 상황의 가치 이론이므로 v2는 단위를 **persona×scenario**로
바꾸고, 각 상황에 대해 valueLevels(TCV 5)와 motivationLevels(7)를 함께 도출한다.

- v1 파일은 **보존한다** — 이미 돌린 합성 세션들이 그 GT로 만들어졌으므로 기록이다.
- 시나리오 쌍 = 매칭 시나리오 + 대비 시나리오(자기용↔선물; 이미 선물이면 가성비).
  매칭은 v1 도출이 있으면 재사용하고, **없으면(풀 확장으로 새로 들어온 persona)
  scenario_match LLM 호출로 직접 매칭**한다 (speechStyle도 이때 함께 도출).
- speechStyle은 말투(사람 속성)라 상황 조건부로 다시 도출하지 않는다.
- 프로필은 대화 시작 전 고정되는 GT이며 service agent에는 절대 노출되지 않는다.

  cd backend && .venv/bin/python scripts/derive_persona_profiles_v2.py        # 풀 전체 (persona × 2시나리오)
  cd backend && .venv/bin/python scripts/derive_persona_profiles_v2.py 10     # 앞 10명만
  VC_SYNTH_CONCURRENCY=6 .venv/bin/python scripts/derive_persona_profiles_v2.py   # 동시 호출 수 (기본 3)

재실행 시 이미 도출된 (persona, scenario)는 건너뛴다. 실 LLM 호출 (.env=deepseek).
도출 temperature는 0.8 — 기본 0.1은 96건이 전부 최빈값(Functional/Utilitarian)으로
수렴하는 mode-seeking을 일으켰다 (temp0.1 도출본 백업: *_temp01.json, Functional 54%).
끝에 분산 요약을 출력한다 — 판정이 아니라 도출이 시나리오 평균/사람 평균으로
무너지지 않았는지 사람이 보기 위한 서술이다.
"""
import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/ → import app

from app.agents.motivation import MOTIVATION_SPEC  # noqa: E402
from app.llm.prompts import SYSTEM_BY_TASK, render_user_context  # noqa: E402
from app.llm.provider import LLMMessage, get_provider  # noqa: E402
from app.ontology.anchor_mapper import TRAIT_ANCHORS  # noqa: E402

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
PERSONAS_PATH = SEED_DIR / "personas_nemotron.json"
V1_PATH = SEED_DIR / "personas_nemotron_profiles.json"
OUT_PATH = SEED_DIR / "personas_nemotron_profiles_v2.json"
VALUE_LEVELS = ("dominant", "present", "trace")
MOT_LEVELS = ("high", "medium", "low")
MOTIVATION_DIMS = tuple(MOTIVATION_SPEC.keys())
CONCURRENCY = int(os.environ.get("VC_SYNTH_CONCURRENCY", "3"))
DERIVE_TEMPERATURE = 0.8


def contrast_scenario_id(first: str) -> str:
    """자기용↔선물 대비 (run_multi_session_simulations_v2와 동일 규칙)."""
    return "gift_for_other" if first != "gift_for_other" else "budget_value"


def _persona_context(persona: dict) -> dict:
    return {
        "name": persona.get("name"),
        "personaNarrative": persona.get("personaNarrative"),
        "demographics": persona.get("demographics"),
        "narratives": persona.get("narratives"),
    }


def _validate(out: dict) -> dict | None:
    values = out.get("valueLevels") or {}
    if not all(values.get(a) in VALUE_LEVELS for a in TRAIT_ANCHORS):
        return None
    motiv_raw = out.get("motivationLevels") or {}
    motiv = {d: lv for d, lv in motiv_raw.items() if d in MOTIVATION_DIMS and lv in MOT_LEVELS}
    if len(motiv) < 3:  # 동기 차원이 거의 비면 도출 실패로 본다
        return None
    for d in MOTIVATION_DIMS:  # 누락 차원은 low로 — "두드러지지 않음"의 명시화
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


async def match_one(provider, persona: dict, scenarios: list[dict]) -> dict | None:
    """v1 매칭이 없는 persona의 시나리오 캐스팅 + speechStyle 도출."""
    context = {
        "persona": _persona_context(persona),
        "scenarios": [
            {"id": s["id"], "title": s.get("title"), "targetCategory": s.get("targetCategory"),
             "initialUserNeed": s.get("initialUserNeed")}
            for s in scenarios
        ],
    }
    out = await provider.generate_json(
        [LLMMessage(role="system", content=SYSTEM_BY_TASK["scenario_match"]),
         LLMMessage(role="user", content=render_user_context(context))],
        task="scenario_match", context=context, temperature=DERIVE_TEMPERATURE,
    )
    if isinstance(out, dict) and out.get("scenarioId") in {s["id"] for s in scenarios}:
        return out
    return None


async def derive_one(provider, persona: dict, scenario: dict) -> dict | None:
    context = {
        "persona": _persona_context(persona),
        "scenario": {
            "id": scenario["id"], "title": scenario.get("title"),
            "targetCategory": scenario.get("targetCategory"),
            "initialUserNeed": scenario.get("initialUserNeed"),
            "description": scenario.get("description"),
        },
    }
    out = await provider.generate_json(
        [LLMMessage(role="system", content=SYSTEM_BY_TASK["persona_profile"]),
         LLMMessage(role="user", content=render_user_context(context))],
        task="persona_profile", context=context, temperature=DERIVE_TEMPERATURE,
    )
    return _validate(out) if isinstance(out, dict) else None


def variance_summary(profiles: dict) -> None:
    """서술적 분산 요약 — 시나리오 고정관념(시나리오 주효과만 남음) 또는
    persona 평균화(상황 간 무변화)로 무너졌는지 사람이 볼 수 있게."""
    by_scenario_dom: dict[str, Counter] = {}
    same, differ = 0, 0
    for p in profiles.values():
        scs = p.get("scenarios") or {}
        for sid, gt in scs.items():
            dom = tuple(sorted(a for a, lv in gt["valueLevels"].items() if lv == "dominant"))
            by_scenario_dom.setdefault(sid, Counter())[dom or ("없음",)] += 1
        gts = list(scs.values())
        if len(gts) >= 2:
            if gts[0]["valueLevels"] == gts[1]["valueLevels"] and \
               gts[0]["motivationLevels"] == gts[1]["motivationLevels"]:
                same += 1
            else:
                differ += 1
    print("\n[분산 요약 — 참고용 서술]", flush=True)
    print(f"- 같은 persona의 두 시나리오 GT: 다름 {differ} · 동일 {same}"
          f"  (동일이 많으면 상황 조건부가 안 먹은 것)", flush=True)
    for sid, ctr in sorted(by_scenario_dom.items()):
        top = ", ".join(f"{'·'.join(k)}×{v}" for k, v in ctr.most_common(4))
        print(f"- {sid}: dominant 분포 {top}"
              f"  (한 조합에 쏠리면 시나리오 고정관념 의심)", flush=True)


async def main(limit: int | None) -> None:
    personas_list = json.loads(PERSONAS_PATH.read_text(encoding="utf-8"))
    personas = {p["id"]: p for p in personas_list}
    scenarios = {s["id"]: s for s in json.loads((SEED_DIR / "scenarios.json").read_text(encoding="utf-8"))}
    scenario_list = list(scenarios.values())
    v1 = json.loads(V1_PATH.read_text(encoding="utf-8")) if V1_PATH.exists() else {}

    profiles: dict = {}
    if OUT_PATH.exists():
        profiles = json.loads(OUT_PATH.read_text(encoding="utf-8"))

    pool_ids = [p["id"] for p in personas_list]
    if limit:
        pool_ids = pool_ids[:limit]

    provider = get_provider()
    sem = asyncio.Semaphore(CONCURRENCY)
    lock = asyncio.Lock()

    def resolved_match(pid: str) -> str | None:
        m = (profiles.get(pid) or {}).get("matchedScenarioId")
        if m in scenarios:
            return m
        m = (v1.get(pid) or {}).get("scenarioId")
        return m if m in scenarios else None

    # 1단계 — 매칭이 없는 persona(풀 확장 신규)를 scenario_match로 캐스팅
    unmatched = [pid for pid in pool_ids if resolved_match(pid) is None]
    if unmatched:
        print(f"시나리오 매칭 필요(신규) {len(unmatched)}명 — scenario_match 호출", flush=True)

        async def match_worker(pid: str) -> None:
            async with sem:
                out = await match_one(provider, personas[pid], scenario_list)
            if out is None:
                print(f"  ✗ {pid} {personas[pid].get('name')} — 매칭 실패, 재실행으로 재시도", flush=True)
                return
            async with lock:
                entry = profiles.setdefault(pid, {
                    "personaId": pid,
                    "personaName": personas[pid].get("name"),
                    "speechStyle": out.get("speechStyle") or "보통 길이, 필요한 것만 말함",
                    "scenarios": {},
                })
                entry["matchedScenarioId"] = out["scenarioId"]
                entry["matchReason"] = out.get("matchReason") or ""
                OUT_PATH.write_text(json.dumps(profiles, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"  ◇ {personas[pid].get('name')} → {out['scenarioId']}", flush=True)

        await asyncio.gather(*(match_worker(pid) for pid in unmatched))

    # 2단계 — persona × (매칭 + 대비) GT 도출
    jobs: list[tuple[str, str]] = []
    for pid in pool_ids:
        matched = resolved_match(pid)
        if matched is None:
            print(f"  ✗ {pid} — 매칭 없음(1단계 실패), 건너뜀", flush=True)
            continue
        for sid in (matched, contrast_scenario_id(matched)):
            if sid not in (profiles.get(pid, {}).get("scenarios") or {}):
                jobs.append((pid, sid))

    print(f"대상 {len(pool_ids)}명 × 2시나리오 — 남은 도출 {len(jobs)}건 (동시 {CONCURRENCY}) → {OUT_PATH.name}", flush=True)

    async def worker(pid: str, sid: str) -> None:
        persona = personas.get(pid)
        if persona is None:
            print(f"  ✗ {pid} — persona 원본 없음", flush=True)
            return
        async with sem:
            gt = await derive_one(provider, persona, scenarios[sid])
        if gt is None:
            print(f"  ✗ {pid} {persona.get('name')} × {sid} — 도출 실패(형식 불일치), 재실행으로 재시도", flush=True)
            return
        async with lock:
            entry = profiles.setdefault(pid, {
                "personaId": pid,
                "personaName": persona.get("name"),
                "speechStyle": (v1.get(pid) or {}).get("speechStyle") or "보통 길이, 필요한 것만 말함",
                "scenarios": {},
            })
            entry.setdefault("matchedScenarioId", resolved_match(pid))
            entry["scenarios"][sid] = gt
            OUT_PATH.write_text(json.dumps(profiles, ensure_ascii=False, indent=1), encoding="utf-8")
        dom = [a for a, lv in gt["valueLevels"].items() if lv == "dominant"]
        high = [d for d, lv in gt["motivationLevels"].items() if lv == "high"]
        print(f"  ✓ {persona.get('name')} × {sid} · value dominant={dom or '없음'} · motivation high={high or '없음'}", flush=True)

    await asyncio.gather(*(worker(pid, sid) for pid, sid in jobs))
    done = sum(len(p.get("scenarios") or {}) for p in profiles.values())
    print(f"\n완료 — {len(profiles)}명 · GT {done}건 저장: {OUT_PATH}", flush=True)
    variance_summary(profiles)
    print("\n검토: 파일을 열어 personaDistinction/matchRationale이 서사를 실제로 인용하는지 확인 (수정해도 됨)", flush=True)


if __name__ == "__main__":
    arg = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    asyncio.run(main(arg))
