# Backend Scripts Guide

This directory mixes maintained workflows, reproducible experiments, historical data migrations,
and destructive repair tools. A script being checked in does not mean it is safe to rerun.

## Classify Before Running

- Current synthesis: `sample_nemotron_personas.py`, `derive_persona_profiles_v2.py`,
  `run_llm_simulations_v2.py`, `run_multi_session_simulations_v2.py`, and the two `run_*.sh`
  batch wrappers.
- Current offline analysis/export: `analyze_pscon.py`, `pscon_prevalidation.py`,
  `download_study_sessions.py`, and `build_product_profiles.py`.
- Current evaluation gates: `eval_planner_searchtext.py`, `eval_rerank_quality.py`,
  `eval_relaxation_question.py`, `sweep_category_fit.py`, and `sweep_interaction_patterns.py`.
- Staged NAVER pipelines: `build_naver_products_stratified.py` -> `merge_labels.py` ->
  `clean_pool.py`; `build_pool.py` and `build_womens_outerwear.py` produce unwired pool files.
- Legacy synthesis: `derive_persona_profiles.py`, `run_llm_simulations.py`, and
  `run_multi_session_simulations.py`. Preserve their v1 outputs; do not regenerate them.
- Historical Amazon migrations: `augment_amazon_*.py`, `enrich_amazon_korean.py`, and
  `shorten_amazon_titles.py`. These explain the checked-in catalog; they are not routine updates.
- Destructive maintenance: `delete_v1_synthesis.py`, `dedup_multi_v2.py`,
  `clean_product_pool.py`, `remove_noise_products.py`, and `reclassify_* --apply`.
- One-off experiments and diagnostics include `bench_*`, `ab_hybrid_retrieval.py`,
  `dspy_compile_searchtext.py`, `diag_*`, `debug_*`, `llm_smoke.py`, `smoke_*`, and `verify_*`.

## Execution Contract

- Run commands from `valuecommit/backend`, using `.venv/bin/python` and `PYTHONPATH=.` where
  the script docstring shows it.
- Before every run, state the exact `VC_DB_PATH`, `VC_SEED_DIR`, LLM provider/model, expected
  network/API use, output path, and whether the command mutates seed JSON or SQLite.
- Never rely on implicit database defaults for cleanup, migration, or synthesis jobs.
- Most enrichment, evaluation, and synthesis scripts make real paid LLM or embedding calls.
  A temporary SQLite database does not imply a mock provider.
- Give long-running jobs a unique log path and use the script's resumable behavior instead of
  launching a second overlapping copy.

```bash
cd valuecommit/backend
VC_DB_PATH=/absolute/path/to/valuecommit.db \
VC_SEED_DIR=/absolute/path/to/seed \
VC_LLM_PROVIDER=deepseek VC_DEEPSEEK_MODEL=deepseek-v4-flash \
PYTHONPATH=. .venv/bin/python scripts/eval_planner_searchtext.py
```

```bash
cd valuecommit/backend
VC_DB_PATH=/absolute/path/to/valuecommit.db \
PYTHONPATH=. .venv/bin/python scripts/delete_v1_synthesis.py
# Review the dry-run, then add --apply only with the same verified environment.
```

## Data and Version Hazards

- Use only `_v2` synthesis for new generation. A `meta.gtVersion="v2"` stamp links generated
  sessions to persona-by-scenario ground truth; v1 used the retired global/local framing.
- The v2 persona/GT scripts hardcode `backend/seed`, while the database remains environment-driven.
  Verify that the GT/scenarios and selected DB belong together before starting a batch.
- `augment_amazon_*` scripts skip existing IDs but collect a fresh quota. Rerunning one can add
  another goal-sized batch rather than converge to the current catalog.
- Some Amazon scripts write directly to `seed_amazon/products.json`; others write staging files.
  Inspect the named output in the script before assuming a dry run or atomic merge.
- Product changes require this order: update products -> build product profiles -> regenerate
  embeddings -> commit seed artifacts -> deploy once with `VC_SEED_UPSERT=1`, then disable it.
- The canonical vector cache may be `product_vectors.json.gz`. Older scripts that delete only
  `product_vectors.json` do not reliably invalidate the current cache.
- Cleanup scripts with `--apply` can update both seed JSON and the selected SQLite DB. Run without
  `--apply` first; keep the generated backup and do not run while synthesis batches are active.
- `scripts_cases_shared.py` is imported by `eval_planner_searchtext.py`, but
  `dspy_compile_searchtext.py` still contains a duplicate case list. Keep them synchronized until
  that duplication is removed.

## Anti-Patterns

- Do not rerun an historical migration merely because its output exists in the current seed.
- Do not mix `seed`, `seed_naver`, and `seed_amazon` inputs or their SQLite databases.
- Do not delete vector caches, overwrite seed files, or use `--apply` without naming the target.
- Do not infer production readiness from a smoke script or an LLM-judge score alone.
- Do not add another copied augmentation script when an existing parameterized workflow can serve.
