"""상품 프로필 배치 생성 — 오프라인 LLM enrichment (기법: ONCE WSDM'24 / LLM-Rec NAACL'24).

상품당 1회 LLM 호출로 정규화 프로필({profile, productType, audience, keyAttributes,
caveats})을 만들어 seed_dir/product_profiles.json에 **증분 캐시**한다 (이미 있는 id는
건너뜀 — product_vectors.json과 같은 패턴). 환각 금지 규칙은 prompts.PRODUCT_PROFILE_SYSTEM.

  cd backend && PYTHONPATH=. .venv/bin/python scripts/build_product_profiles.py

VC_SEED_DIR 기본 seed_amazon. provider는 .env(VC_LLM_PROVIDER=deepseek)에서.
600개 기준 ~10분/~$0.2. 25개마다 체크포인트 저장 — 중단해도 재실행이 이어서 처리.
"""
import asyncio
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("VC_SEED_DIR", str(BACKEND / "seed_amazon"))

from app.llm.provider import LLMMessage, get_provider  # noqa: E402
from app.llm.prompts import SYSTEM_BY_TASK, render_user_context  # noqa: E402

SEED_DIR = Path(os.environ["VC_SEED_DIR"])
OUT = SEED_DIR / "product_profiles.json"
CONCURRENCY = 8
CHECKPOINT_EVERY = 25

REQUIRED_KEYS = ("profile", "productType", "audience", "keyAttributes", "caveats")


def _valid(prof: dict) -> bool:
    if not isinstance(prof, dict) or not all(k in prof for k in REQUIRED_KEYS):
        return False
    if not isinstance(prof.get("profile"), str) or not prof["profile"].strip():
        return False
    for k in ("keyAttributes", "caveats"):
        if not isinstance(prof.get(k), list):
            return False
        prof[k] = [a for a in prof[k] if isinstance(a, str) and a.strip()]
    return True


async def _one(provider, sem: asyncio.Semaphore, p: dict) -> tuple[str, dict | None]:
    attrs = p.get("attributes") or {}
    context = {
        "title": p.get("title") or "",
        "titleFull": attrs.get("titleFull") or "",
        "titleEn": attrs.get("titleEn") or "",
        "description": p.get("description") or "",
        "category": p.get("category") or "",
        "price": p.get("price"),
    }
    async with sem:
        try:
            out = await provider.generate_json(
                [LLMMessage(role="system", content=SYSTEM_BY_TASK["product_profile"]),
                 LLMMessage(role="user", content=render_user_context(context))],
                task="product_profile", context=context,
            )
        except Exception as e:  # noqa: BLE001
            print(f"  ! {p['id']}: {e}")
            return p["id"], None
    return p["id"], out if _valid(out) else None


async def main() -> None:
    provider = get_provider()
    print(f"provider={provider.name}  seed={SEED_DIR}")
    if provider.name == "mock":
        print("mock provider로는 프로필을 만들지 않는다 — .env의 실 provider 필요")
        return

    products = json.loads((SEED_DIR / "products.json").read_text(encoding="utf-8"))
    done: dict[str, dict] = {}
    if OUT.exists():
        done = json.loads(OUT.read_text(encoding="utf-8"))
    todo = [p for p in products if p["id"] not in done]
    print(f"products={len(products)}  cached={len(done)}  todo={len(todo)}")

    sem = asyncio.Semaphore(CONCURRENCY)
    failed: list[str] = []
    for i in range(0, len(todo), CHECKPOINT_EVERY):
        batch = todo[i:i + CHECKPOINT_EVERY]
        results = await asyncio.gather(*[_one(provider, sem, p) for p in batch])
        for pid, prof in results:
            if prof is None:
                failed.append(pid)
            else:
                done[pid] = prof
        OUT.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  checkpoint: {len(done)}/{len(products)} (failed so far: {len(failed)})")

    print(f"done: {len(done)} profiles → {OUT}")
    if failed:
        print(f"failed {len(failed)} (재실행하면 이어서 시도): {failed[:10]}")


if __name__ == "__main__":
    asyncio.run(main())
