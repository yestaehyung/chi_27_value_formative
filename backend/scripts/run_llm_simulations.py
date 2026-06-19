"""LLM user agent 합성 대화 실행 — 합성 테스트 2단계.

derive_persona_profiles.py 가 만든 프로필(GT)로 persona × scenario 대화를 합성하고,
검수용 마크다운을 data/synthesis_test/ 에 쓴다. 세션은 mode="simulation"으로
저장되므로 /research 화면에서도 replay/그래프 확인 가능.

  cd backend && .venv/bin/python scripts/run_llm_simulations.py        # 프로필 전체
  cd backend && .venv/bin/python scripts/run_llm_simulations.py 3      # 앞 3명만

재실행 시 이미 합성된 persona(산출 md 존재)는 건너뛴다.
실 LLM 호출 (VC_LLM_PROVIDER, 기본 .env=deepseek). 동시 2 (PSCon 배치와 병행 고려).
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/ → import app

from app.db.database import SessionLocal, init_db  # noqa: E402

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
PROFILES_PATH = SEED_DIR / "personas_nemotron_profiles.json"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "synthesis_test"
MAX_USER_TURNS = 8


def _fmt_levels(d: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in (d or {}).items())


def _top(scores: dict, k: int = 2) -> list[str]:
    return [a for a, v in sorted((scores or {}).items(), key=lambda kv: -kv[1]) if v > 0.1][:k]


def write_review_md(persona: dict, profile: dict, scenario: dict, res: dict) -> Path:
    injected_dominant = [a for a, lv in (profile.get("traitLevels") or {}).items() if lv == "dominant"]
    recovered_top = _top(res["anchorScores"])
    match = "✅ 일치" if set(injected_dominant) & set(recovered_top) else "❌ 불일치"
    lines = [
        f"# {persona.get('name')} ({persona['id']}) × {scenario.get('title')}",
        "",
        f"- 세션: `{res['sessionId']}` · 종료: {res['ended']}"
        + (f" · 구매: {res['purchasedProductId']}" if res.get("purchasedProductId") else ""),
        "",
        "## Persona 서사",
        persona.get("personaNarrative", ""),
        "",
        "## 주입 프로필 (GT — service agent 비노출)",
        f"- traitLevels: {_fmt_levels(profile.get('traitLevels'))}",
        f"- motivationTendencies: {_fmt_levels(profile.get('motivationTendencies'))}",
        f"- speechStyle: {profile.get('speechStyle')}",
        "- hiddenIntentions:",
        *[f"  - {h}" for h in profile.get("hiddenIntentions", [])],
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
        "## 복원 결과 (시스템이 추출한 것)",
        f"- trait anchors: { {k: round(v, 2) for k, v in res['anchorScores'].items() if v > 0} }",
        f"- motivation: { {k: v for k, v in res['motivationScores'].items() if v} }",
        "- 추출 의도:",
        *[f"  - {t['label']} ({t['hints'].get('kind', '?')}, {t['explicitness']})" for t in res["topics"]],
        "",
        "## 비공식 복원 비교",
        f"- 주입 dominant trait: {injected_dominant} / 복원 상위: {recovered_top} → {match}",
        "",
        "## 검수 메모 (직접 기입)",
        "- 대화 자연스러움 (1~5): ",
        "- 인물 일관성 — 발화가 서사·프로필과 모순 없는가: ",
        "- hidden intention이 직접 발화되지 않고 행동으로 새는가: ",
        "- 복원이 납득되는가 / 명백히 틀린 축: ",
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
        print("프로필 파일이 없음 — 먼저 scripts/derive_persona_profiles.py 실행", flush=True)
        return
    profiles = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    items = list(profiles.values())[:limit] if limit else list(profiles.values())
    todo = [p for p in items if not (OUT_DIR / f"{p['personaId']}.md").exists()]
    print(f"프로필 {len(items)}명 · 이미 합성됨 {len(items) - len(todo)}명 · 남은 {len(todo)}명 · → {OUT_DIR}", flush=True)

    sem = asyncio.Semaphore(2)
    summary: list[dict] = []

    async def worker(profile: dict) -> None:
        pid = profile["personaId"]
        persona = get_persona(pid)
        scenario = get_scenario(profile["scenarioId"])
        if persona is None or scenario is None:
            print(f"  ✗ {pid} — persona/scenario 못 찾음", flush=True)
            return
        db = SessionLocal()
        try:
            async with sem:
                res = await run_llm_simulation(db, persona, profile, scenario, MAX_USER_TURNS)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {pid} 실패: {e}", flush=True)
            return
        finally:
            db.close()
        await judge_causal_relations(res["sessionId"])
        path = write_review_md(persona, profile, scenario, res)
        injected = [a for a, lv in (profile.get("traitLevels") or {}).items() if lv == "dominant"]
        recovered = _top(res["anchorScores"])
        user_turns = sum(1 for t in res["transcript"] if t["role"] == "user")
        summary.append({
            "personaId": pid, "name": persona.get("name"), "scenario": scenario["id"],
            "sessionId": res["sessionId"], "userTurns": user_turns, "ended": res["ended"],
            "topics": len(res["topics"]), "injectedDominant": injected, "recoveredTop": recovered,
        })
        print(f"  ✓ {persona.get('name')} × {scenario['id']} · {user_turns}턴 · {res['ended']} · "
              f"topics={len(res['topics'])} · 주입 {injected} vs 복원 {recovered} → {path.name}", flush=True)

    await asyncio.gather(*(worker(p) for p in todo))
    if summary:
        (OUT_DIR / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n완료 — 검수 파일: {OUT_DIR}/*.md · 요약: summary.json", flush=True)
    print("연구 화면에서도 확인 가능: /research (mode=simulation 세션)", flush=True)


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    asyncio.run(main(limit))
