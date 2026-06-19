"""Enrich seed/products_naver.json with the NAVER Search API (shop.json).

For each seeded product we query the shopping search API by a cleaned title,
pick the best match guarded by token-overlap + price proximity, and fill:
  - imageUrl              (top-level → maps to Product.image_url column)
  - attributes.categoryPath  ("패션의류 > 여성의류 > 잠옷/홈웨어")
  - attributes.lowestPrice   (lprice — Naver 최저가, for comparison)

The dump has no images, so this is the one external step. We search by NAME
(no catalogId lookup exists in the official API), so a match is best-effort:
the guards below drop low-confidence matches (imageUrl stays null → the card
falls back to its letter mark). Idempotent/resumable: products that already
have imageUrl are skipped unless --force. Writes back to the same file.

Keys come from backend/.env (VC_NAVER_CLIENT_ID / VC_NAVER_CLIENT_SECRET),
loaded by importing app.core.config.

Usage (from backend/):
  .venv/bin/python scripts/enrich_naver_images.py            # fill missing
  .venv/bin/python scripts/enrich_naver_images.py --force    # re-fetch all
  .venv/bin/python scripts/enrich_naver_images.py --limit 20 # smoke test
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# import app.core.config to populate os.environ from backend/.env
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app.core.config  # noqa: E402,F401  (side effect: loads .env)

ENDPOINT = "https://openapi.naver.com/v1/search/shop.json"

CLIENT_ID = os.environ.get("VC_NAVER_CLIENT_ID")
CLIENT_SECRET = os.environ.get("VC_NAVER_CLIENT_SECRET")

# query-noise we strip before searching: bracketed segments, sku-like codes,
# option markers. Over-cleaning loses specificity, so this is deliberately light.
_BRACKETS = re.compile(r"[\[\(【].*?[\]\)】]")
_SKU = re.compile(r"\b[A-Z0-9]*\d[A-Z0-9]*\b")          # tokens containing a digit (MBF2TS1702)
_PUNCT = re.compile(r"[_/|·,]+")
_WS = re.compile(r"\s+")
_TAGS = re.compile(r"</?b>")
_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")


def clean_query(title: str) -> str:
    q = _BRACKETS.sub(" ", title)
    q = _PUNCT.sub(" ", q)
    q = _SKU.sub(" ", q)
    q = _WS.sub(" ", q).strip()
    # keep the first ~8 meaningful tokens — Naver search is precise enough and
    # long queries over-constrain (return 0 results)
    toks = q.split()
    return " ".join(toks[:8]) if toks else title


def tokens(s: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(s) if len(t) > 1}


def search(query: str, display: int = 5) -> list[dict]:
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": query, "display": display})
    req = urllib.request.Request(url, headers={
        "X-Naver-Client-Id": CLIENT_ID,
        "X-Naver-Client-Secret": CLIENT_SECRET,
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8")).get("items", [])


def best_match(items: list[dict], product: dict) -> dict | None:
    """Pick the API item that best matches our product.

    Hard gate: token-overlap (Jaccard) >= 0.30 with the original title.
    Score: overlap, with price proximity as a tie-breaker. Returns None if
    nothing clears the gate (→ leave imageUrl null, graceful fallback)."""
    want = tokens(product["title"])
    if not want:
        return None
    target_price = product.get("price") or product.get("listPrice")
    best, best_score = None, 0.0
    for it in items:
        have = tokens(_TAGS.sub("", it.get("title", "")))
        if not have:
            continue
        jacc = len(want & have) / len(want | have)
        if jacc < 0.30:
            continue
        score = jacc
        lprice = int(it["lprice"]) if str(it.get("lprice", "")).isdigit() else None
        if target_price and lprice:
            ratio = min(lprice, target_price) / max(lprice, target_price)
            score += 0.2 * ratio                      # closer price → small bonus
        if score > best_score:
            best, best_score = it, score
    return best


def category_path(it: dict) -> str:
    parts = [it.get(f"category{i}") for i in range(1, 5)]
    return " > ".join(p for p in parts if p)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-fetch even if imageUrl set")
    ap.add_argument("--limit", type=int, default=0, help="process at most N (0=all)")
    ap.add_argument("--sleep", type=float, default=0.1, help="delay between calls (s)")
    ap.add_argument("--file", default="seed_naver/products.json",
                    help="seed product json to enrich (relative to backend/)")
    args = ap.parse_args()

    if not CLIENT_ID or not CLIENT_SECRET:
        sys.exit("ERROR: VC_NAVER_CLIENT_ID / VC_NAVER_CLIENT_SECRET not set in backend/.env")

    seed_path = Path(__file__).resolve().parents[1] / args.file
    products = json.loads(seed_path.read_text(encoding="utf-8"))
    todo = [p for p in products if args.force or not p.get("imageUrl")]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(products)} products · {len(todo)} to enrich\n")

    matched = skipped = errored = 0
    for i, p in enumerate(todo, 1):
        q = clean_query(p["title"])
        try:
            items = search(q)
        except urllib.error.HTTPError as e:
            if e.code == 429:                          # rate limited → back off
                print("  429 rate limit — sleeping 5s"); time.sleep(5); continue
            if e.code == 401:
                sys.exit("ERROR 401: invalid Naver API credentials")
            errored += 1; print(f"  [{i}] HTTP {e.code} for {q!r}"); continue
        except Exception as e:                          # noqa: BLE001
            errored += 1; print(f"  [{i}] {type(e).__name__}: {e}"); continue

        m = best_match(items, p)
        if m:
            p["imageUrl"] = m.get("image") or None
            # API link = a live product page (mostly smartstore.naver.com, some other
            # malls). Replaces the dead catalogId URL the build emits.
            p["productUrl"] = m.get("link") or None
            attrs = p.setdefault("attributes", {})
            attrs["categoryPath"] = category_path(m)
            if str(m.get("lprice", "")).isdigit():
                attrs["lowestPrice"] = int(m["lprice"])
            matched += 1
        else:
            # no confident match → clear image and the dead catalog link
            p["imageUrl"] = None
            p["productUrl"] = None
            skipped += 1

        if i % 25 == 0:
            print(f"  {i}/{len(todo)} · matched={matched} skipped={skipped} err={errored}")
            seed_path.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
        time.sleep(args.sleep)

    seed_path.write_text(json.dumps(products, ensure_ascii=False, indent=2), encoding="utf-8")
    total = matched + skipped + errored
    rate = (matched / total * 100) if total else 0
    print(f"\nDONE · matched={matched} skipped={skipped} errored={errored} "
          f"({rate:.0f}% match) → {seed_path.name}")


if __name__ == "__main__":
    main()
