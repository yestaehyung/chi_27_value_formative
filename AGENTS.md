# ValueCommit Repository Guide

## Scope

- ValueCommit is an HCI research prototype for exposing and correcting value-grounded hidden intentions in conversational shopping.
- Recommendation quality supports the study; the primary object is observable, revisable user-model evidence and state.
- This repository is independent from sibling `coding-tool`, `wimhf`, and `PSCon` projects. Run Git and build commands from `valuecommit/` or the relevant child directory.
- Read the workspace-root guide for cross-repository context. This file covers only contracts shared by the ValueCommit services.

## Structure

```text
valuecommit/
├── backend/   # FastAPI, SQLite, LLM orchestration, retrieval, tests, scripts, seeds
├── frontend/  # Next.js participant flow and researcher/prototype surfaces
├── docs/      # Research framing, design decisions, audits, plans, handoffs
├── CLAUDE.md  # Detailed architecture and current operational context
└── DEPLOY.md  # Railway/Nixpacks deployment runbook
```

- Follow `backend/AGENTS.md` and its nested guides for Python, databases, seeds, tests, and operational scripts.
- Follow `frontend/AGENTS.md` for routes, API types, participant state, UI conventions, and verification.
- Do not copy backend or frontend implementation rules into this file; keep cross-service contracts here.

## Canonical Documents

- `CLAUDE.md`: detailed architecture, environment combinations, provider behavior, and current deployment context.
- `DEPLOY.md`: current two-service Railway/Nixpacks procedure; it supersedes the stale Docker Compose section in `README.md`.
- `docs/research-framing.md` and `docs/formative-study-design.md`: RQs, study intent, and design goals.
- `docs/plans/2026-07-02-three-agent-crs-redesign.md`: current turn-loop architecture and action vocabulary.
- `docs/ontology-graph-design.md`, `docs/llm-measurement-design.md`, and `docs/algorithm-audit.md`: ontology, measurement, and heuristic contracts.
- `docs/session-handoff.md` is historical operational context; verify its dates and live state before acting on it.
- Read the relevant document before changing prompts, scoring, ontology structure, study flow, or deployment behavior.

## Cross-Service Invariants

- Frontend requests use same-origin `/api/*`; `frontend/next.config.mjs` proxies them to `BACKEND_URL`. Keep browser code behind that seam.
- Participant study isolation requires both layers: frontend `APP_MODE=study` and backend `VC_APP_MODE=study` with a non-empty `VC_RESEARCH_KEY`.
- Study mode must not expose simulation, synthesis, PSCon, comparison, ontology, or researcher-navigation surfaces.
- Research and export APIs fail closed in study mode and require `X-Research-Key`; never embed the key in tracked source.
- Preserve the participant sequence `/study/survey` -> `/study/tutorial` -> `/study/session/new` -> `/study/session/[sessionId]`.
- `VC_SEED_DIR`, `VC_DB_PATH`, and `VC_EXPORT_DIR` form one environment pairing. Never mix a seed pool with another pool's database.
- SQLite study databases, exports, surveys, turns, feedback, impressions, and preference snapshots are research records, not disposable test artifacts.
- Keep slow LLM/network work outside SQLite write transactions. Backend application code owns this guarantee.
- Backend API field names and identifiers are the service contract; update backend serializers, frontend types/client, and affected flows together.
- Deployed behavior is the deployed commit plus environment and persistent volume state; do not infer production state from the local checkout alone.

## Commands and Pointers

```bash
cd backend && .venv/bin/uvicorn app.main:app --port 8000
cd backend && test_root=$(mktemp -d) && VC_DB_PATH="$test_root/test.db" VC_EXPORT_DIR="$test_root/exports" VC_LLM_PROVIDER=mock .venv/bin/python -m pytest tests/ -q
cd frontend && npm run dev
cd frontend && npm exec -- tsc --noEmit --incremental false
```

- Use `backend/run_nv_study.sh` or `backend/run_amazon_study.sh` only after confirming the intended seed/database pair.
- Use `DEPLOY.md` for production variables, volumes, deployment order, backups, and smoke checks.
- Stop `next dev` before `npm run build`; both commands share `.next/`.

## Anti-Patterns

- Do not adopt the `README.md` Docker Compose instructions; no Compose manifest is maintained.
- Do not call LLM providers directly from pipeline modules; use the backend provider abstraction and preserve deterministic mock coverage.
- Do not run paid, destructive, reseeding, cleanup, or large batch scripts as routine validation.
- Do not point tests at checked-in or mounted study databases, and do not overwrite curated seeds to make tests pass.
- Do not treat researcher tools under `/study` as participant-safe merely because of their URL; audience is determined by behavior and middleware coverage.
- Do not return ORM objects directly or invent frontend-only API shapes outside the shared backend/client boundary.
- Do not claim live verification after local-only checks; report the exact environment and surface exercised.
