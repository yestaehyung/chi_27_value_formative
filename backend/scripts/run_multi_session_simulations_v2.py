"""멀티 세션 합성 (v2 GT) — 같은 persona가 Participant로 묶여 2개 시나리오를 차례로 진행.

v1과의 차이 (global/local framing 폐기 반영):
- **세션마다 그 시나리오의 GT를 주입한다** — 가치·동기는 상황의 산물이므로
  같은 사람이라도 세션 1(매칭 시나리오)과 세션 2(대비 시나리오)의 GT가 다르다.
- 자동 판정(trait 일관 ✅/❌ 등)을 만들지 않는다 — md에는 세션별 주입 GT와
  복원 결과를 나란히 기록만 하고, 평가는 나중에 사람·LLM이 별도로 한다.
- 세션 meta에 gtVersion="v2" 스탬프.

Participant 누적(spec 문서·RIG)은 그대로 동작한다 — "안정 trait 추정"이 아니라
선택 상황들을 가로지른 반복 패턴의 기억으로 읽는다.

  cd backend && .venv/bin/python scripts/run_multi_session_simulations_v2.py        # 10명 × 2세션
  cd backend && .venv/bin/python scripts/run_multi_session_simulations_v2.py 4      # 4명만

재실행 시 산출 md가 있는 persona는 건너뛴다. 실 LLM 호출 (.env=deepseek), 동시 2.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/ → import app

from app.db.database import SessionLocal, init_db  # noqa: E402

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
PROFILES_PATH = SEED_DIR / "personas_nemotron_profiles_v2.json"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "synthesis_multi_v2"
MAX_USER_TURNS = 8
N_DEFAULT = 10
GT_VERSION = "v2"
CONCURRENCY = int(os.environ.get("VC_SYNTH_CONCURRENCY", "2"))  # 대규모 배치는 4~6 권장


def contrast_scenario_id(first: str) -> str:
    """자기용↔선물 대비 (derive_persona_profiles_v2와 동일 규칙)."""
    return "gift_for_other" if first != "gift_for_other" else "budget_value"


def select_diverse_personas(profiles: dict, n: int) -> list[dict]:
    """매칭 시나리오 GT의 dominant 구성이 다양하게 — 희귀 그룹부터 round-robin (결정론)."""
    groups: dict[tuple, list[dict]] = {}
    for p in sorted(profiles.values(), key=lambda x: x["personaId"]):
        gt = (p.get("scenarios") or {}).get(p.get("matchedScenarioId")) or {}
        sig = tuple(sorted(a for a, lv in (gt.get("valueLevels") or {}).items() if lv == "dominant"))
        groups.setdefault(sig, []).append(p)
    ordered_groups = sorted(groups.items(), key=lambda kv: (len(kv[1]), kv[0]))  # 희귀 그룹 우선
    chosen: list[dict] = []
    while len(chosen) < n and any(g for _, g in ordered_groups):
        for _, g in ordered_groups:
            if g and len(chosen) < n:
                chosen.append(g.pop(0))
    return chosen


def _fmt_levels(d: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in (d or {}).items())


def _top(scores: dict, k: int = 2) -> list[str]:
    return [a for a, v in sorted((scores or {}).items(), key=lambda kv: -kv[1]) if v > 0.1][:k]


def write_multi_md(persona: dict, entry: dict, runs: list[dict], spec_md: str | None) -> Path:
    lines = [
        f"# [멀티 세션 v2] {persona.get('name')} ({persona['id']})",
        "",
        "같은 사람이 두 선택 상황을 차례로 진행 — 세션마다 그 상황의 GT가 주입됨",
        f"(speechStyle 공통: {entry.get('speechStyle')})",
        "",
    ]
    for i, r in enumerate(runs, 1):
        gt = r["gt"]
        lines += [
            f"## 세션 {i} — {r['scenarioTitle']} (`{r['sessionId']}`, {r['ended']})",
            "",
            "### 주입 GT (이 상황에서 — service agent 비노출)",
            f"- valueLevels: {_fmt_levels(gt.get('valueLevels'))}",
            f"- motivationLevels: {_fmt_levels(gt.get('motivationLevels'))}",
            f"- personaDistinction: {gt.get('personaDistinction')}",
            "- hiddenIntentions:",
            *[f"  - {h}" for h in gt.get("hiddenIntentions", [])],
            "",
            "### 복원 결과 (판정 없음 — 나란히 기록만)",
            f"- 가치 5축: { {k: round(v, 2) for k, v in r['anchorScores'].items() if v > 0.1} }",
            f"- 동기 7축: { {k: v for k, v in r['motivationScores'].items() if v} }",
            "",
            "### 대화",
        ]
        for t in r["transcript"]:
            if t["role"] == "user":
                lines.append(f"**사용자**: {t['content']}")
            elif t["role"] == "agent":
                lines.append(f"**에이전트**: {t['content']}")
            else:
                lines.append(f"> [행동] {t['content']}")
            lines.append("")
    lines += [
        "## Participant spec (두 세션 누적 후 — 반복 패턴의 기억)",
        "```markdown",
        (spec_md or "(스펙 미생성)").strip(),
        "```",
        "",
        "## 검수 메모 (직접 기입)",
        "- 각 세션의 복원이 그 상황의 주입 GT를 반영하는가 (가치·동기 각각): ",
        "- 두 상황 사이에서 무엇이 달라지고 무엇이 반복되는가: ",
        "- 세션 2에서 에이전트가 세션 1의 학습을 활용하는 징후(선행 질문 등): ",
    ]
    out = OUT_DIR / f"{persona['id']}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


async def main(n: int) -> None:
    init_db()
    from app.agents.judge import judge_causal_relations
    from app.agents.llm_user_agent import run_llm_simulation
    from app.db import models
    from app.products.seed_loader import get_persona, get_scenario

    if not PROFILES_PATH.exists():
        print("v2 프로필이 없음 — 먼저 scripts/derive_persona_profiles_v2.py 실행", flush=True)
        return
    profiles = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = [p for p in select_diverse_personas(profiles, n)
               if not (OUT_DIR / f"{p['personaId']}.md").exists()]
    print(f"멀티 세션 대상 {n}명 중 남은 {len(targets)}명 (persona당 2세션, 세션별 GT) · → {OUT_DIR}", flush=True)

    sem = asyncio.Semaphore(CONCURRENCY)
    summary: list[dict] = []

    async def worker(entry: dict) -> None:
        pid = entry["personaId"]
        persona = get_persona(pid)
        if persona is None:
            print(f"  ✗ {pid} — persona 못 찾음", flush=True)
            return
        sid1 = entry.get("matchedScenarioId")
        sid2 = contrast_scenario_id(sid1)
        scs = entry.get("scenarios") or {}
        if sid1 not in scs or sid2 not in scs:
            print(f"  ✗ {pid} — 시나리오 GT 누락 ({sid1}/{sid2}) — derive_v2 재실행 필요", flush=True)
            return

        async with sem:
            db = SessionLocal()
            try:
                # persona당 Participant 1명 — 세션 횡단 누적의 단위.
                # v1 멀티(part_<pid>)와 분리: v1 spec 누적이 v2에 섞이면 안 된다.
                part_id = f"part_v2_{pid}"
                if db.get(models.Participant, part_id) is None:
                    db.add(models.Participant(id=part_id, label=f"[합성v2] {persona.get('name')}"))
                    db.commit()
                runs = []
                for sid in (sid1, sid2):  # 순차 — 세션2는 세션1의 누적 위에서 진행
                    scenario = get_scenario(sid)
                    gt = scs[sid]
                    profile = {**gt, "speechStyle": entry.get("speechStyle")}
                    res = await run_llm_simulation(
                        db, persona, profile, scenario, MAX_USER_TURNS,
                        participant_id=part_id, gt_version=GT_VERSION)
                    res["scenarioTitle"] = scenario.get("title")
                    res["gt"] = gt
                    await judge_causal_relations(res["sessionId"])
                    runs.append(res)
                part = db.get(models.Participant, part_id)
                spec_md = part.spec_markdown if part else None
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {pid} 실패: {e}", flush=True)
                return
            finally:
                db.close()

        path = write_multi_md(persona, entry, runs, spec_md)
        summary.append({
            "personaId": pid, "name": persona.get("name"),
            "scenarios": [sid1, sid2],
            "sessions": [
                {
                    "sessionId": r["sessionId"], "scenarioId": r["scenarioId"], "ended": r["ended"],
                    "injected": {
                        "valueDominant": [a for a, lv in r["gt"]["valueLevels"].items() if lv == "dominant"],
                        "motivationHigh": [d for d, lv in r["gt"]["motivationLevels"].items() if lv == "high"],
                    },
                    "recovered": {
                        "valueTop": _top(r["anchorScores"]),
                        "motivationTop": _top(r["motivationScores"]),
                    },
                }
                for r in runs
            ],
        })
        print(f"  ✓ {persona.get('name')} · {sid1}→{sid2} → {path.name}", flush=True)

    await asyncio.gather(*(worker(p) for p in targets))
    if summary:
        (OUT_DIR / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n완료 {len(summary)}명 × 2세션 — 주입/복원은 summary.json에 나란히 기록 (판정 없음)", flush=True)
    print(f"검수 파일: {OUT_DIR}/*.md", flush=True)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else N_DEFAULT
    asyncio.run(main(n))
