"""Sample N Nemotron-Personas-Korea personas for the user-agent simulation pool.

Proportional (= uniform random over the dataset → follows real KR demographics),
reproducible via SEED. Shopping-decision traits (priceSensitivity, valueOrientation,
communicationStyle …) are intentionally NOT stored here — they are synthesized later
through agent dialogue. We keep identity + demographics + rich narratives only.

To stay under the datasets-server rate limit we pull a handful of small scattered
windows (few calls) and uniformly sample N from that pool. Nemotron rows are i.i.d.
(PGM-sampled, no ordering), so contiguous windows are effectively random.

Run:  .venv/bin/python scripts/sample_nemotron_personas.py
"""
import json
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DATASET = "nvidia/Nemotron-Personas-Korea"
CONFIG, SPLIT = "default", "train"
SEED, N = 42, 50
WINDOWS, WIN_LEN = 10, 15          # 10 calls × 15 rows = 150 candidate pool
OUT = Path(__file__).resolve().parent.parent / "seed" / "personas_nemotron.json"
ROWS_API = "https://datasets-server.huggingface.co/rows"
INFO_API = "https://datasets-server.huggingface.co/info"

NARRATIVE_FIELDS = [
    "professional_persona", "sports_persona", "arts_persona", "travel_persona",
    "culinary_persona", "family_persona", "cultural_background",
    "skills_and_expertise", "hobbies_and_interests", "career_goals_and_ambitions",
]
DEMO_FIELDS = [
    "sex", "age", "marital_status", "military_status", "family_type",
    "housing_type", "education_level", "bachelors_field", "occupation",
    "district", "province", "country",
]


def _get(url: str, tries: int = 6):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "valuecommit-sampler/1.0"})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                ra = e.headers.get("Retry-After")
                wait = int(ra) if (ra and str(ra).isdigit()) else 20 * (i + 1)
                print(f"    · 429 rate-limited → waiting {wait}s")
                time.sleep(wait)
                continue
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
        except Exception:  # noqa: BLE001
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
    raise RuntimeError("exhausted retries")


def total_rows() -> int:
    try:
        d = _get(f"{INFO_API}?dataset={urllib.parse.quote(DATASET)}")
        info = d["dataset_info"]
        info = info.get(CONFIG, info)
        return info["splits"][SPLIT]["num_examples"]
    except Exception:  # noqa: BLE001
        return 1_000_000


def fetch_window(offset: int, length: int) -> list[dict]:
    url = (f"{ROWS_API}?dataset={urllib.parse.quote(DATASET)}"
           f"&config={CONFIG}&split={SPLIT}&offset={offset}&length={length}")
    return [r["row"] for r in _get(url).get("rows", [])]


def derive_name(persona: str, age, sex) -> str:
    m = re.match(r"\s*([가-힣]{2,4})\s*씨", persona or "")
    return m.group(1) if m else f"{age}세 {sex or ''}".strip()


def to_record(row: dict) -> dict:
    persona = row.get("persona") or ""
    return {
        "id": "nk_" + str(row.get("uuid", ""))[:8],
        "name": derive_name(persona, row.get("age"), row.get("sex")),
        "source": "nemotron_personas_korea",
        "uuid": row.get("uuid"),
        "personaNarrative": persona,
        "demographics": {k: row.get(k) for k in DEMO_FIELDS},
        "narratives": {k: row.get(k) for k in NARRATIVE_FIELDS if row.get(k)},
    }


def main(target: int):
    """target명까지 확장 — 기존 풀은 그대로 두고 부족분만 새로 뽑아 덧붙인다.

    기존 persona의 id(uuid 기반)·세션·GT가 전부 살아 있어야 하므로 재추첨이 아니라
    병합이다. 파일이 없을 때 target=50이면 원래 동작과 동일(시드 42 재현).
    """
    existing: list[dict] = []
    if OUT.exists():
        existing = json.loads(OUT.read_text(encoding="utf-8"))
    have_uuids = {p.get("uuid") for p in existing}
    need = target - len(existing)
    if need <= 0:
        print(f"이미 {len(existing)}명 ≥ 목표 {target}명 — 변경 없음")
        return

    total = total_rows()
    # 확장 실행은 기존과 다른 행이 필요하므로 시드를 (SEED, target)으로 파생 — 결정론 유지
    rng = random.Random(SEED if not existing else SEED + target)
    windows = max(WINDOWS, -(-need * 2 // WIN_LEN))  # 후보 풀 ≈ 필요분의 2배
    base_offsets = rng.sample(range(0, max(1, total - WIN_LEN)), windows)
    pool: list[dict] = []
    for n, off in enumerate(base_offsets, 1):
        rows = fetch_window(off, WIN_LEN)
        pool.extend(rows)
        print(f"  window {n:>2}/{windows}  off={off:<7} +{len(rows)}  pool={len(pool)}")
        time.sleep(1.5)

    # de-dup by uuid (기존 풀 제외), then uniform sample need
    seen, uniq = set(have_uuids), []
    for r in pool:
        u = r.get("uuid")
        if u not in seen:
            seen.add(u)
            uniq.append(r)
    chosen = rng.sample(uniq, need) if len(uniq) >= need else uniq
    new_records = [to_record(r) for r in chosen]
    out = existing + new_records
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in new_records:
        d = r["demographics"]
        print(f"  + {r['name']:<10} {d.get('age')}{(d.get('sex') or '')[:1]} · "
              f"{d.get('occupation')} · {d.get('province')}")
    print(f"\n✓ 기존 {len(existing)} + 신규 {len(new_records)} = {len(out)}명 → {OUT}")
    if len(uniq) < need:
        print(f"⚠ 후보 부족으로 {need - len(new_records)}명 모자람 — 같은 명령을 다시 실행하면 추가 표집")


if __name__ == "__main__":
    import sys
    target = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else N
    main(target)
