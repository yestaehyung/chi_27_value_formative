# Product Pipeline Guide

## Scope and ownership

- This package owns seed ingestion, product text/cue construction, retrieval, filtering,
  relevance scoring, rerank inputs, product-profile lookup, and embedding caches.
- Keep stage boundaries visible: retrieve for recall, apply deterministic constraints and
  value-blind relevance here, then let the recommender's LLM reranker choose the shown set.
- `seed_loader.py` is the boundary from JSON fixtures into database models. Parse source
  fields there; downstream modules should operate on model fields rather than reopen seeds.
- `search_index.py` owns lexical BM25 retrieval. `embeddings.py` owns semantic retrieval.
  `search.py` blends candidates, filters them, scores them, and returns the rerank pool.
- `profiles.py` only reads offline enrichment keyed by product ID. Absence or malformed
  enrichment must preserve the raw-product fallback rather than block recommendations.

## Retrieval and evidence purity

- Preserve the distinction between product identity evidence and inferred use-fit.
  Embedding text may use title, category, factual attributes, and structured profile identity
  fields; do not inject profile persuasion prose, user preferences, or reranker judgments.
- Retrieval must not convert a noisy detected category into an unintended hard exclusion.
  Category, tag, and price constraints should follow the current explicit contracts and tests.
- Do not discard retrieval rank accidentally. Semantic similarity and lexical relevance are
  ranking signals; deterministic tie-breaking/diversity must not erase their ordering.
- The final explanation must be grounded in the products actually selected for display, not
  an earlier retrieval pool. Keep excluded and near-miss products out of shown-card evidence.
- Cue summaries and derived labels must be traceable to factual seed fields. Never fabricate
  specifications or treat offline LLM enrichment as verified catalog truth.

## Seeds, database state, and caches

- `VC_SEED_DIR` selects one complete seed family. Keep it paired with its matching database:
  `seed_amazon` with `amazon_ko.db`, and historical `seed_naver` with `nv_study.db`.
- The default `seed/` tree is the demo/test fixture, not a substitute for a study catalog.
- Prefer `upsert_seed_products` when adding products. Forced reseed removes Product and
  ProductImpression rows; never use it casually against participant-study data.
- Product IDs are the join key across seeds, DB rows, profiles, indexes, and vectors. Any ID
  change requires checking every derived artifact and rebuilding the in-memory search index.
- Vector caches are incremental and ID-keyed. Adding IDs can reuse existing vectors, but a
  change to embedding text construction requires deleting and regenerating the selected
  seed family's cache; ID equality alone cannot detect text-recipe changes.
- `.json.gz` is the preferred large-cache format; legacy `.json` remains a supported fallback.
  Preserve compression and rounding conventions when regeneration is explicitly requested.
- Files under `seed/`, `seed_naver/`, and `seed_amazon/` may be machine-derived yet tracked.
  Treat tracked profiles, vectors, labels, and pools as maintained fixtures: do not normalize,
  overwrite, or regenerate them unless the task explicitly includes the resulting data diff.
- Never edit `backend/data/`, `backend/exports/`, or any seed fixture as a side effect of a
  product-code change. Use temporary seed/export directories in tests.

## Verification

- Keep tests focused at the changed seam. Relevant regression files include
  `test_category_hard_filter.py`, `test_hybrid_blend.py`, `test_price_range.py`,
  `test_seed_upsert.py`, `test_rerank_exclude.py`, and `test_reply_grounding.py`.
- Use small in-memory databases and temporary seed directories. Do not require production
  catalogs, network embeddings, or a developer's current vector cache for unit tests.
- For retrieval changes, cover the embedding path and BM25 fallback, stale IDs, constraints,
  stable ordering, and an empty/failed retriever path without asserting natural-language prose.
- Run the narrow regression test first, then the broader backend suite when the change affects
  seed loading, shared scoring, candidate ordering, or the final displayed product set.
