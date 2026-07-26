# ValueCommit Backend Guide

## Scope

- This directory is the FastAPI, SQLAlchemy, SQLite, LLM, and research-tooling backend.
- Use `app/AGENTS.md` for maintained application architecture and package routing.
- Use `scripts/AGENTS.md` before running or changing offline generation, enrichment, evaluation, or cleanup jobs.
- Keep backend changes here; frontend conventions live outside this directory.

## Environment and Commands

- Run commands from `valuecommit/backend`; imports assume `app` is available from this working directory.
- The checked-in dependency declaration is `requirements.txt`; the current local environment is `.venv`.
- Run the deterministic suite with `.venv/bin/python -m pytest`.
- Start the default app with `.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- Start the NAVER study pool with `bash run_nv_study.sh`; use `bash run_nv_study_dev.sh` only for reload-based development.
- Start the Amazon Korean pool with `bash run_amazon_study.sh`.
- `app/core/config.py` loads `backend/.env` at import time without overriding existing process variables.
- Never commit `.env` or API keys. Update `.env.example` only with placeholders and safe defaults.

## Maintained Source and Data Boundaries

- Maintained application code is under `app/`; maintained behavior tests are under `tests/`.
- `scripts/` is maintained operational/research code, but its outputs are not application source.
- Treat ordinary `data/` runs, `exports/`, logs, caches, `__pycache__/`, `.pytest_cache/`, and `.venv/` as generated state.
- Exception: `data/study_export/`, `data/railway_volume_backup/`, and `data/local_db_archive/` contain maintained research records. Never bulk-delete or regenerate them.
- Treat `*.db`, `*.db-wal`, `*.db-shm`, and `*.db.bak*` as live or archived study state, not fixtures.
- Seed directories are curated inputs, but vector files, synthesis products, backups, and derived profiles may be generated artifacts. Check the producing script before editing them manually.
- Do not include generated data or virtual environments when estimating maintained-code size or searching for source conventions.

## Database and Seed Pairing

- Always resolve `VC_SEED_DIR`, `VC_DB_PATH`, and `VC_EXPORT_DIR` together before startup or a script run.
- Production Amazon Korean pairing: `seed_amazon` with `/data/amazon_ko.db`; local launcher uses `backend/amazon_ko.db`.
- Historical NAVER study pairing: `seed_naver` with `/data/nv_study.db`; local launcher uses `backend/nv_study.db`.
- Never point a seed directory at the other pool's database. Product IDs, scenarios, search indexes, and recorded impressions must stay in the same pool.
- `VC_RESEED=1` force-reloads products and can remove recommendation-impression records. Use only with an explicit backup and data-loss approval.
- Prefer one-time `VC_SEED_UPSERT=1` when only adding new products; turn either flag off immediately after the intended startup.
- Do not mutate, migrate, clean, or replace a real study database merely to make a test pass.

## Study Safety

- Participant deployment must set `VC_APP_MODE=study`; this prevents simulation, synthesis, and PSCon routers from being mounted.
- A study deployment must also set a non-empty `VC_RESEARCH_KEY`; otherwise research/export access fails closed.
- Preserve the distinction between participant routes, protected researcher read/export routes, and research-only write/simulation routes.
- Keep LLM waits outside SQLite write transactions. Persist required input, release the write lock, perform network work, then use a short final write transaction.
- Treat exports, participant surveys, turns, feedback, impressions, and preference snapshots as sensitive research data.

## Test Isolation

- Default tests to `VC_LLM_PROVIDER=mock`; unit and acceptance tests must not require paid or network LLM calls.
- Set `VC_DB_PATH` and `VC_EXPORT_DIR` to temporary paths before importing `app.main`; settings and the engine are created at import time.
- Prefer temporary or in-memory SQLite with a fresh schema. Never run tests against `valuecommit.db`, `nv_study.db`, `amazon_ko.db`, or `/data/*.db`.
- Keep seed-dependent acceptance tests deterministic and avoid modifying checked-in seed files in place.
- For retrieval changes, test the embedding-disabled BM25 fallback as well as mocked embedding results; external embedding calls do not belong in the suite.
