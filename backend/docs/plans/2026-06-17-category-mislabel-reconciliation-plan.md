# Category mislabel reconciliation — plan (prepared 2026-06-17)

## Problem (confirmed)
`scripts/build_naver_products_stratified.py::classify(title)` assigns `category` by **unanchored
substring regex over the product title** (`re.search(inc, title)`). This produces systemic
mislabels because a category keyword appears as a substring of unrelated titles:
- `니트` ⊂ "미**니트**릿" (cat treat) → `니트·가디건`
- `코트` ⊂ "테라**코트**/방수**코트**" (paint) → `코트·패딩·자켓`
- `바지` ⊂ "이**바지**떡" (rice cake) → `팬츠·바지`
- plus 무릎보호대, 뜨개질실/바늘, 원피스변기, 원피스 앞치마, 수영장기저귀, 패딩부츠 …

Aggravating detail: every clothing rule in `TAXONOMY` carries a `강아지/애견` exclude **except
`니트·가디건` (line 38)** — that single omission is what let `nv_1034389427141766136` (the cat treat,
already fixed individually 2026-06-17) through. See [[naver-offdomain-recommendation-leak]].

The script author already flagged the real fix in the module docstring (line 8): use **NAVER API
`category1~4`** instead of title keywords.

## Why we do NOT need to re-run the 10GB build
`attributes.categoryPath` (from `enrich_naver_images.py`, NAVER API `category1~4`) is **already present
for 520/650 products** in the live seed. So the authoritative category is in the data — a
reconciliation pass over the existing seed fixes all categories at once, with no dependency on the
raw `*.csv.gz` dumps (which also may no longer be extracted to `/tmp/nv/*.tsv`).

Measured scope (nv_study.db, 2026-06-17): total 650 · has categoryPath 520 · `domain=의류` with
non-fashion path **≥72** (lower bound — excludes 전자기기 conflicts and within-domain miscategorization).

## Decisions to confirm before executing
1. **Fix strategy** — recommended: reconcile existing seed from `categoryPath` **and** fix the build
   script to be categoryPath-first (so future builds don't regress). Alternatives: keyword-exclude
   patch only (brittle, needs re-run), or reconcile-seed-only (leave build script for later).
2. **Out-of-scope items** (path clearly outside the clothing/electronics study scope — 변기, 페인트,
   떡, 기저귀, 무릎보호대, 뜨개질실…): recommended **drop** them (a fashion/electronics study catalog
   shouldn't contain them; consistent with `clean_pool.py`'s existing noise removal). Alternative:
   reclassify-and-keep as orphans, or flag-only for human review.
3. **No-path products (130)**: no `categoryPath` to reconcile against — recommended keep current
   keyword `category` but re-run it through the hardened classifier; flag count in the report.

## Execution — sub-agent brief (investigation-first; minimal grounded change)
The sub-agent READS before changing (the user's required discipline):
1. Read `scripts/build_naver_products_stratified.py` (classify + TAXONOMY), `scripts/enrich_naver_images.py`
   (`category_path()` → how categoryPath is formed), `scripts/clean_pool.py`, `scripts/merge_labels.py`,
   and `app/products/seed_loader.py` (canonical file = `seed_dir/products.json`).
2. Build a **categoryPath → study-category mapping** from NAVER paths to the catalog's category vocab
   (니트·가디건, 코트·패딩·자켓, 원피스, 팬츠·바지, 티셔츠·셔츠, 잠옷·홈웨어, 수영복·래쉬가드, 무선이어폰,
   노트북, 태블릿, 키보드·마우스, 모니터, 헤드셋·헤드폰). Paths outside this set → out-of-scope (per decision 2).
3. Apply reconciliation to **both** the canonical seed JSON (`seed_naver/products.json`, via Edit/whole-file
   rewrite) **and** the live `nv_study.db` (UPDATE), keeping them in sync. Back up both first.
4. Rebuild the FTS index for changed rows (mirror `search_index.index_product` / `build_index`; single-row
   replaces if the server is live — check `lsof -i :8000`).
5. Harden the build script per decision 1 (categoryPath-first when present; add the missing
   `강아지|반려|애견|고양이|간식` exclude to `니트·가디건` as a belt-and-suspenders fallback for no-path items).

## Acceptance criteria (verify, pure SQL where possible)
- `domain=의류 & non-fashion path` count drops to 0 (or only intentionally-kept orphans remain).
- The end-to-end pipeline check (re-run `search_products` for a 니트 query) shows **no off-domain items**
  in top-3 across a spot-check of categories (니트·가디건, 코트·패딩·자켓, 원피스, 팬츠·바지).
- Seed JSON and DB agree (same category for every id).
- Report: rows reclassified, rows dropped, no-path rows left as-is, before/after counts.

## Files
- Culprit: `scripts/build_naver_products_stratified.py` (classify/TAXONOMY)
- Ground truth: `attributes.categoryPath` via `scripts/enrich_naver_images.py`
- Clean stage (likely home for reconciliation): `scripts/clean_pool.py`
- Live data: `seed_naver/products.json` (canonical) + `nv_study.db`
- Not loaded but keep consistent: `seed_naver/products_naver.json`
