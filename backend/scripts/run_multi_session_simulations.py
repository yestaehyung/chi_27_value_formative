"""멀티 세션 합성 — 같은 persona가 Participant로 묶여 2개 시나리오를 차례로 진행.

검증 목표 (global/local 2층 가치 모델):
  - trait(global)는 시나리오가 바뀌어도 일관되게 복원되는가
  - motivation(local)은 시나리오에 따라 달라지는가
  - participant 누적(spec 문서)이 세션을 넘어 작동하는가

시나리오 배정(테스트 단계 — 단순 규칙): 세션1 = 프로필 매칭 시나리오,
세션2 = 선물 시나리오(이미 선물이면 가성비) — 자기용↔타인용 대비를 공짜로 확보.
대비 쌍 정교화는 테스트 결과를 보고 결정 (사용자 합의 2026-06-11).

  cd backend && .venv/bin/python scripts/run_multi_session_simulations.py        # 10명 × 2세션
  cd backend && .venv/bin/python scripts/run_multi_session_simulations.py 4      # 4명만

재실행 시 산출 md가 있는 persona는 건너뛴다. 실 LLM 호출 (.env=deepseek), 동시 2.
"""
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/ → import app

from app.db.database import SessionLocal, init_db  # noqa: E402

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
PROFILES_PATH = SEED_DIR / "personas_nemotron_profiles.json"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "synthesis_multi"
MAX_USER_TURNS = 8
N_DEFAULT = 10


def second_scenario_id(first: str) -> str:
    """테스트용 단순 대비 규칙 — 자기용↔선물 대비."""
    return "gift_for_other" if first != "gift_for_other" else "budget_value"


def select_diverse_personas(profiles: dict, n: int) -> list[dict]:
    """dominant 구성이 다양하게 — 희귀한 dominant 그룹부터 round-robin (결정론)."""
    groups: dict[tuple, list[dict]] = {}
    for p in sorted(profiles.values(), key=lambda x: x["personaId"]):
        sig = tuple(sorted(a for a, lv in p["traitLevels"].items() if lv == "dominant"))
        groups.setdefault(sig, []).append(p)
    ordered_groups = sorted(groups.items(), key=lambda kv: (len(kv[1]), kv[0]))  # 희귀 그룹 우선
    chosen: list[dict] = []
    while len(chosen) < n and any(g for _, g in ordered_groups):
        for _, g in ordered_groups:
            if g and len(chosen) < n:
                chosen.append(g.pop(0))
    return chosen


def _top(scores: dict, k: int = 2) -> list[str]:
    return [a for a, v in sorted((scores or {}).items(), key=lambda kv: -kv[1]) if v > 0.1][:k]


def write_multi_md(persona: dict, profile: dict, runs: list[dict], spec_md: str | None) -> Path:
    injected = [a for a, lv in profile["traitLevels"].items() if lv == "dominant"]
    s1, s2 = runs[0], runs[1]
    t1, t2 = set(_top(s1["anchorScores"])), set(_top(s2["anchorScores"]))
    m1, m2 = _top(s1["motivationScores"]), _top(s2["motivationScores"])
    trait_consistent = bool(t1 & t2)
    motivation_differs = set(m1) != set(m2)

    lines = [
        f"# [멀티 세션] {persona.get('name')} ({persona['id']})",
        "",
        "## 주입 프로필 (GT — 두 세션 공통, service agent 비노출)",
        f"- dominant trait: {injected}",
        f"- motivationTendencies: {profile.get('motivationTendencies')}",
        "- hiddenIntentions:",
        *[f"  - {h}" for h in profile.get("hiddenIntentions", [])],
        "",
        "## 세션 횡단 비교 (2층 가치 모델 검증)",
        f"- **trait 일관성** (global — 시나리오가 바뀌어도 유지돼야 함): "
        f"세션1 {sorted(t1)} vs 세션2 {sorted(t2)} → {'✅ 일관' if trait_consistent else '❌ 비일관'}",
        f"- **motivation 변화** (local — 시나리오 따라 달라져야 함): "
        f"세션1 {m1} vs 세션2 {m2} → {'✅ 변화함' if motivation_differs else '⚠️ 동일 (대비 부족?)'}",
        f"- GT 복원: 세션1 {'✅' if set(injected) & t1 else '❌'} · 세션2 {'✅' if set(injected) & t2 else '❌'}",
        "",
    ]
    for i, r in enumerate(runs, 1):
        lines += [
            f"## 세션 {i} — {r['scenarioTitle']} (`{r['sessionId']}`, {r['ended']})",
            f"- 복원 trait: { {k: round(v, 2) for k, v in r['anchorScores'].items() if v > 0.1} }",
            f"- 복원 motivation: { {k: v for k, v in r['motivationScores'].items() if v} }",
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
        "## Participant spec (두 세션 누적 후 — KG의 자연어 미러)",
        "```markdown",
        (spec_md or "(스펙 미생성)").strip(),
        "```",
        "",
        "## 검수 메모",
        "- trait가 세션을 넘어 일관되게 복원됐는가: ",
        "- motivation이 시나리오를 따라 갔는가: ",
        "- 세션 2에서 에이전트가 세션 1의 학습을 활용하는 징후(선행 질문 등): ",
    ]
    out = OUT_DIR / f"{persona['id']}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


async def main(n: int) -> None:
    init_db()
    from app.agents.judge import judge_causal_relations
    from app.agents.llm_user_agent import run_llm_simulation
    from app.core.ids import new_id
    from app.db import models
    from app.products.seed_loader import get_persona, get_scenario

    profiles = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = [p for p in select_diverse_personas(profiles, n)
               if not (OUT_DIR / f"{p['personaId']}.md").exists()]
    print(f"멀티 세션 대상 {n}명 중 남은 {len(targets)}명 (persona당 2세션) · → {OUT_DIR}", flush=True)

    sem = asyncio.Semaphore(2)
    summary: list[dict] = []

    async def worker(profile: dict) -> None:
        pid = profile["personaId"]
        persona = get_persona(pid)
        if persona is None:
            print(f"  ✗ {pid} — persona 못 찾음", flush=True)
            return
        sc1 = get_scenario(profile["scenarioId"])
        sc2 = get_scenario(second_scenario_id(profile["scenarioId"]))
        if sc1 is None or sc2 is None:
            print(f"  ✗ {pid} — 시나리오 못 찾음", flush=True)
            return

        async with sem:
            db = SessionLocal()
            try:
                # persona당 Participant 1명 — 세션 횡단 누적의 단위
                part_id = f"part_{pid}"
                if db.get(models.Participant, part_id) is None:
                    db.add(models.Participant(id=part_id, label=f"[합성] {persona.get('name')}"))
                    db.commit()
                runs = []
                for sc in (sc1, sc2):  # 순차 — 세션2는 세션1의 누적 위에서 진행
                    res = await run_llm_simulation(
                        db, persona, profile, sc, MAX_USER_TURNS, participant_id=part_id)
                    res["scenarioTitle"] = sc.get("title")
                    await judge_causal_relations(res["sessionId"])
                    runs.append(res)
                part = db.get(models.Participant, part_id)
                spec_md = part.spec_markdown if part else None
            except Exception as e:  # noqa: BLE001
                print(f"  ✗ {pid} 실패: {e}", flush=True)
                return
            finally:
                db.close()

        path = write_multi_md(persona, profile, runs, spec_md)
        injected = [a for a, lv in profile["traitLevels"].items() if lv == "dominant"]
        t1, t2 = set(_top(runs[0]["anchorScores"])), set(_top(runs[1]["anchorScores"]))
        m_diff = set(_top(runs[0]["motivationScores"])) != set(_top(runs[1]["motivationScores"]))
        summary.append({
            "personaId": pid, "name": persona.get("name"),
            "scenarios": [sc1["id"], sc2["id"]],
            "injectedDominant": injected,
            "traitConsistent": bool(t1 & t2),
            "motivationDiffers": m_diff,
            "gtRecovered": [bool(set(injected) & t1), bool(set(injected) & t2)],
        })
        print(f"  ✓ {persona.get('name')} · {sc1['id']}→{sc2['id']} · trait일관={'O' if t1 & t2 else 'X'} "
              f"· motiv변화={'O' if m_diff else 'X'} → {path.name}", flush=True)

    await asyncio.gather(*(worker(p) for p in targets))
    if summary:
        (OUT_DIR / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
        tc = sum(1 for s in summary if s["traitConsistent"])
        md = sum(1 for s in summary if s["motivationDiffers"])
        print(f"\n완료 {len(summary)}명 — trait 일관 {tc}/{len(summary)} · motivation 변화 {md}/{len(summary)}", flush=True)
    print(f"검수 파일: {OUT_DIR}/*.md", flush=True)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else N_DEFAULT
    asyncio.run(main(n))
