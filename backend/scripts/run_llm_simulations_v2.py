"""LLM user agent 합성 대화 실행 (v2 GT — persona×scenario 조건부).

derive_persona_profiles_v2.py 가 만든 GT로 각 persona의 **매칭 시나리오** 대화를
합성하고, 검수용 마크다운을 data/synthesis_v2/ 에 쓴다.

v1과의 차이:
- GT가 시나리오 조건부 (가치·동기는 상황의 산물)
- md/요약에 자동 판정(✅/❌)을 넣지 않는다 — 평가는 나중에 사람·LLM이 별도로 한다.
  여기서는 주입 GT와 복원 결과를 나란히 기록만 한다 (평가 가능성 보존).
- 세션 meta에 gtVersion="v2" 스탬프 (어떤 GT 파일과 대조할지의 연결고리)

  cd backend && .venv/bin/python scripts/run_llm_simulations_v2.py        # 전체
  cd backend && .venv/bin/python scripts/run_llm_simulations_v2.py 3      # 앞 3명만

재실행 시 이미 합성된 persona(산출 md 존재)는 건너뛴다. 실 LLM 호출 (.env=deepseek), 동시 2.
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
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "synthesis_v2"
MAX_USER_TURNS = 8
GT_VERSION = "v2"
CONCURRENCY = int(os.environ.get("VC_SYNTH_CONCURRENCY", "2"))  # 대규모 배치는 4~6 권장


def _fmt_levels(d: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in (d or {}).items())


def _top(scores: dict, k: int = 2) -> list[str]:
    return [a for a, v in sorted((scores or {}).items(), key=lambda kv: -kv[1]) if v > 0.1][:k]


def write_review_md(persona: dict, gt: dict, speech_style: str, scenario: dict, res: dict) -> Path:
    lines = [
        f"# {persona.get('name')} ({persona['id']}) × {scenario.get('title')}",
        "",
        f"- 세션: `{res['sessionId']}` · 종료: {res['ended']}"
        + (f" · 구매: {res['purchasedProductId']}" if res.get("purchasedProductId") else ""),
        "",
        "## Persona 서사",
        persona.get("personaNarrative", ""),
        "",
        "## 주입 GT (이 상황에서 — service agent 비노출)",
        f"- valueLevels: {_fmt_levels(gt.get('valueLevels'))}",
        f"- motivationLevels: {_fmt_levels(gt.get('motivationLevels'))}",
        f"- speechStyle: {speech_style}",
        f"- personaDistinction: {gt.get('personaDistinction')}",
        f"- matchRationale: {gt.get('matchRationale')}",
        "- hiddenIntentions:",
        *[f"  - {h}" for h in gt.get("hiddenIntentions", [])],
        "",
        "## 대화",
    ]
    for t in res["transcript"]:
        if t["role"] == "user":
            lines.append(f"**사용자**: {t['content']}")
        elif t["role"] == "agent":
            lines.append(f"**에이전트**: {t['content']}")
        else:
            lines.append(f"> [행동] {t['content']}")
        lines.append("")
    lines += [
        "## 복원 결과 (시스템이 추출한 것 — 판정 없음, 나란히 기록만)",
        f"- 가치 5축: { {k: round(v, 2) for k, v in res['anchorScores'].items() if v > 0} }",
        f"- 동기 7축: { {k: v for k, v in res['motivationScores'].items() if v} }",
        "- 추출 의도:",
        *[f"  - {t['label']} ({t['hints'].get('kind', '?')}, {t['explicitness']})" for t in res["topics"]],
        "",
        "## 검수 메모 (직접 기입)",
        "- 대화 자연스러움 (1~5): ",
        "- 인물 일관성 — 발화가 서사·이 상황의 GT와 모순 없는가: ",
        "- hidden intention이 직접 발화되지 않고 행동으로 새는가: ",
        "- 복원이 주입 GT를 반영하는가 (가치·동기 각각): ",
    ]
    out = OUT_DIR / f"{persona['id']}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


async def main(limit: int | None) -> None:
    init_db()
    from app.agents.judge import judge_causal_relations
    from app.agents.llm_user_agent import run_llm_simulation
    from app.products.seed_loader import get_persona, get_scenario

    if not PROFILES_PATH.exists():
        print("v2 프로필이 없음 — 먼저 scripts/derive_persona_profiles_v2.py 실행", flush=True)
        return
    profiles = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    items = list(profiles.values())[:limit] if limit else list(profiles.values())
    todo = [p for p in items if not (OUT_DIR / f"{p['personaId']}.md").exists()]
    print(f"프로필 {len(items)}명 · 이미 합성됨 {len(items) - len(todo)}명 · 남은 {len(todo)}명 · → {OUT_DIR}", flush=True)

    sem = asyncio.Semaphore(CONCURRENCY)
    summary: list[dict] = []

    async def worker(entry: dict) -> None:
        pid = entry["personaId"]
        persona = get_persona(pid)
        sid = entry.get("matchedScenarioId")
        gt = (entry.get("scenarios") or {}).get(sid)
        scenario = get_scenario(sid)
        if persona is None or scenario is None or gt is None:
            print(f"  ✗ {pid} — persona/scenario/GT 못 찾음 ({sid})", flush=True)
            return
        profile = {**gt, "speechStyle": entry.get("speechStyle")}
        db = SessionLocal()
        try:
            async with sem:
                res = await run_llm_simulation(
                    db, persona, profile, scenario, MAX_USER_TURNS, gt_version=GT_VERSION)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {pid} 실패: {e}", flush=True)
            return
        finally:
            db.close()
        await judge_causal_relations(res["sessionId"])
        path = write_review_md(persona, gt, entry.get("speechStyle") or "", scenario, res)
        user_turns = sum(1 for t in res["transcript"] if t["role"] == "user")
        summary.append({
            "personaId": pid, "name": persona.get("name"), "scenario": sid,
            "sessionId": res["sessionId"], "userTurns": user_turns, "ended": res["ended"],
            "topics": len(res["topics"]),
            "injected": {
                "valueDominant": [a for a, lv in gt["valueLevels"].items() if lv == "dominant"],
                "motivationHigh": [d for d, lv in gt["motivationLevels"].items() if lv == "high"],
            },
            "recovered": {
                "valueTop": _top(res["anchorScores"]),
                "motivationTop": _top(res["motivationScores"]),
            },
        })
        print(f"  ✓ {persona.get('name')} × {sid} · {user_turns}턴 · {res['ended']} · "
              f"topics={len(res['topics'])} → {path.name}", flush=True)

    await asyncio.gather(*(worker(p) for p in todo))
    if summary:
        (OUT_DIR / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n완료 — 검수 파일: {OUT_DIR}/*.md · 요약: summary.json (판정 없음 — 주입/복원 나란히 기록)", flush=True)
    print("연구 화면에서도 확인 가능: /research (mode=simulation 세션) · /simulate 합성 검수", flush=True)


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    asyncio.run(main(limit))
