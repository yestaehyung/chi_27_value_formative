"""Batch-analyze PSCon conversations through our pipeline (offline · resumable · concurrent).

Writes backend/data/pscon_analysis.json = {convId: {anchorScores, anchorBreakdown,
topics, userTurnCount}}. The web reads this and visualizes instantly (no per-click
LLM wait). Makes real LLM calls (VC_LLM_PROVIDER, e.g. deepseek) — run detached:

  cd backend
  setsid nohup .venv/bin/python scripts/analyze_pscon.py 648 6 \
      > /tmp/pscon_batch.log 2>&1 < /dev/null &

Args: [N conversations from top = all 648] [concurrency = 6]. Re-run resumes
(skips already-analyzed). Concurrency overlaps the deepseek latency across
conversations; SQLite (WAL + busy_timeout) serializes the short writes. The
pipeline's _safe() wrappers degrade gracefully on a rate-limit, so the batch
keeps going. tail -f /tmp/pscon_batch.log to watch.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # backend/ → import app

from app.api.pscon import RESULTS_PATH, _load, analyze_one_conversation  # noqa: E402
from app.db.database import init_db  # noqa: E402


async def main(n: int | None, concurrency: int) -> None:
    init_db()
    convs = _load()
    if not convs:
        print("PSCon 데이터셋을 못 찾음.", flush=True)
        return
    if n:
        convs = convs[:n]

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    results: dict = {}
    if RESULTS_PATH.exists():
        try:
            results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            results = {}

    todo = [c for c in convs if str(c.get("conv_id")) not in results]
    total = len(todo)
    print(
        f"대상 {len(convs)}건 · 이미 분석됨 {len(results)}건 · 남은 {total}건 · 동시 {concurrency} · → {RESULTS_PATH}",
        flush=True,
    )

    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    done = 0
    failed = 0

    async def worker(conv: dict) -> None:
        nonlocal done, failed
        cid = str(conv.get("conv_id"))
        async with sem:
            try:
                res = await analyze_one_conversation(conv)
            except Exception as e:  # noqa: BLE001
                async with lock:
                    failed += 1
                    print(f"  #{cid} 실패: {e}", flush=True)
                return
        async with lock:
            results[cid] = res
            RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
            done += 1
            sc = {k: round(v, 2) for k, v in (res.get("anchorScores") or {}).items()}
            print(f"[{done}/{total}] #{cid} ✓ topics={len(res.get('topics', []))} {sc}", flush=True)

    await asyncio.gather(*(worker(c) for c in todo))
    print(f"\n완료 — 신규 {done}건 · 실패 {failed}건 · 총 {len(results)}건 저장됨.", flush=True)


if __name__ == "__main__":
    arg_n = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    arg_c = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 6
    asyncio.run(main(arg_n, arg_c))
