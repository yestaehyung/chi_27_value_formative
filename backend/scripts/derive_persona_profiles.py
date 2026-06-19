"""Nemotron persona 10명 선정 + 쇼핑 프로필(GT) 도출 — 합성 테스트 1단계.

교수님 가이드(유형은 페르소나와 매칭되어야 함)의 조작화: 프로필을 무작위 배정하지
않고 서사에서 LLM이 도출하고(scenarioId 매칭 포함), 결과를 사람이 검토할 수 있게
seed/personas_nemotron_profiles.json 에 저장한다. 프로필은 대화 시작 전 고정되는
ground truth이며 service agent에는 절대 노출되지 않는다.

선정: 인구통계(성별 × 연령대)가 겹치지 않게 결정론적으로 10명 — "특색"은 서사가
제공하고, 선정은 스펙트럼이 넓게.

  cd backend && .venv/bin/python scripts/derive_persona_profiles.py        # 10명
  cd backend && .venv/bin/python scripts/derive_persona_profiles.py 15     # N명

재실행 시 이미 도출된 persona는 건너뛴다 (파일을 지우면 처음부터).
실 LLM 호출 (VC_LLM_PROVIDER, 기본 .env=deepseek).
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/ → import app

from app.llm.prompts import SYSTEM_BY_TASK, render_user_context  # noqa: E402
from app.llm.provider import LLMMessage, get_provider  # noqa: E402
from app.ontology.anchor_mapper import TRAIT_ANCHORS  # noqa: E402

SEED_DIR = Path(__file__).resolve().parent.parent / "seed"
OUT_PATH = SEED_DIR / "personas_nemotron_profiles.json"
LEVELS = ("dominant", "present", "trace")


def select_diverse(personas: list[dict], n: int) -> list[dict]:
    """성별 × 연령대 그룹이 겹치지 않게 우선 선정 (결정론적 — id 정렬 순회)."""
    chosen: list[dict] = []
    seen_groups: set[tuple] = set()
    for p in sorted(personas, key=lambda x: x["id"]):
        demo = p.get("demographics") or {}
        group = (demo.get("sex"), int(demo.get("age", 0)) // 10)
        if group in seen_groups:
            continue
        seen_groups.add(group)
        chosen.append(p)
        if len(chosen) >= n:
            return chosen
    for p in sorted(personas, key=lambda x: x["id"]):  # 그룹이 모자라면 채움
        if p not in chosen:
            chosen.append(p)
            if len(chosen) >= n:
                break
    return chosen


def _validate(out: dict, scenario_ids: set[str]) -> dict | None:
    levels = out.get("traitLevels") or {}
    if not all(levels.get(a) in LEVELS for a in TRAIT_ANCHORS):
        return None
    if out.get("scenarioId") not in scenario_ids:
        return None
    if not out.get("hiddenIntentions"):
        return None
    return out


async def derive_one(provider, persona: dict, scenarios: list[dict]) -> dict | None:
    context = {
        "persona": {
            "name": persona.get("name"),
            "personaNarrative": persona.get("personaNarrative"),
            "demographics": persona.get("demographics"),
            "narratives": persona.get("narratives"),
        },
        "scenarios": [
            {"id": s["id"], "title": s.get("title"), "targetCategory": s.get("targetCategory"),
             "initialUserNeed": s.get("initialUserNeed")}
            for s in scenarios
        ],
    }
    out = await provider.generate_json(
        [LLMMessage(role="system", content=SYSTEM_BY_TASK["persona_profile"]),
         LLMMessage(role="user", content=render_user_context(context))],
        task="persona_profile", context=context,
    )
    return _validate(out, {s["id"] for s in scenarios}) if isinstance(out, dict) else None


async def main(n: int) -> None:
    personas = json.loads((SEED_DIR / "personas_nemotron.json").read_text(encoding="utf-8"))
    scenarios = json.loads((SEED_DIR / "scenarios.json").read_text(encoding="utf-8"))
    profiles: dict = {}
    if OUT_PATH.exists():
        profiles = json.loads(OUT_PATH.read_text(encoding="utf-8"))

    targets = [p for p in select_diverse(personas, n) if p["id"] not in profiles]
    print(f"선정 {n}명 · 이미 도출됨 {len(profiles)}명 · 이번에 {len(targets)}명 도출", flush=True)
    provider = get_provider()
    sem = asyncio.Semaphore(3)

    async def worker(p: dict) -> None:
        async with sem:
            out = await derive_one(provider, p, scenarios)
        if out is None:
            print(f"  ✗ {p['id']} {p.get('name')} — 도출 실패(형식 불일치), 재실행으로 재시도 가능", flush=True)
            return
        profiles[p["id"]] = {"personaId": p["id"], "personaName": p.get("name"), **out}
        OUT_PATH.write_text(json.dumps(profiles, ensure_ascii=False, indent=1), encoding="utf-8")
        dom = [a for a, lv in out["traitLevels"].items() if lv == "dominant"]
        print(f"  ✓ {p['id']} {p.get('name')} → {out['scenarioId']} · dominant={dom} · "
              f"hidden={len(out['hiddenIntentions'])}개", flush=True)

    await asyncio.gather(*(worker(p) for p in targets))
    print(f"\n완료 — 총 {len(profiles)}명 프로필 저장: {OUT_PATH}", flush=True)
    print("검토: 파일을 열어 traitLevels/hiddenIntentions가 서사와 맞는지 확인 후 수정 가능 (수정해도 됨)", flush=True)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 10
    asyncio.run(main(n))
