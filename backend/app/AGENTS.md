# Backend Application Guide

## Scope

This directory is the FastAPI and SQLAlchemy application for ValueCommit, an HCI research prototype for recovering and correcting hidden shopping intentions. Preserve research validity and evidence provenance ahead of recommendation polish.

## Domain Map

- `main.py` composes the app, startup lifecycle, middleware, and mode-dependent routers.
- `api/` owns HTTP boundaries: request parsing, authorization dependencies, response assembly, and calls into domain services.
- `core/` owns configuration, identifiers, and the fail-closed researcher-access gate.
- `db/` owns SQLAlchemy models, engine/session setup, additive migrations, and JSON serialization.
- `preference_commit/` turns new utterance or feedback evidence into an updated preference state.
- `ontology/` extracts, merges, maps, and relates evidence-backed intentions and builds snapshots.
- `agents/` orchestrates the live conversational turn, planning, recommendation, and response generation.
- `llm/` provides the model boundary, task contracts, retries, parsing, and deterministic mock behavior.
- `products/` owns seed loading, retrieval, constraints, profiles, embeddings, and ranking inputs.
- `graph/`, `evaluation/`, and `wimhf/` expose researcher-facing derived artifacts; they must not become alternate writers of raw participant evidence.

## Central Turn Flow

1. `api/turns.py` or `api/feedback.py` validates the request and resolves the session.
2. `agents/service_agent.py` persists the raw `Turn` or `FeedbackEvent` and commits it immediately.
3. `preference_commit/commit_engine.py` runs evidence extraction and independent ontology fetches, then applies the resulting mutations in a short transaction.
4. The service agent plans the next action, optionally retrieves and reranks products, and renders the reply.
5. The agent turn, impressions, snapshots, conflicts, and research traces are persisted before the API serializes the result.

Simulation paths reuse this flow. Do not create a parallel implementation that bypasses the service agent or preference commit pipeline.

## Cross-Cutting Invariants

### SQLite transactions

- Never hold a SQLite write transaction across an LLM, embedding, network, or other slow `await`.
- Follow the established `LLM-first, write-last` pattern: commit raw evidence, perform slow read-only work, then apply mutations in one short transaction.
- Ontology stages keep `fetch_*` functions DB-write-free and `apply_*` functions await-free.
- Preserve WAL and `busy_timeout` behavior in `db/database.py`.
- Schema changes are additive and belong in `db/database.py::_migrate`; do not replace or recreate a study database.

### Study isolation

- `VC_APP_MODE=study` is a structural isolation boundary, not a UI preference.
- Do not mount simulation, synthesis, or PSCon routers in study mode, and do not let synthetic sessions enter the study database.
- Research and export routes remain behind the fail-closed research-key dependency.
- Keep seed and database selection environment-driven; never silently fall back across study, simulation, NAVER, or Amazon stores.

### Evidence and status

- Raw utterances, feedback, corrections, and conflict resolutions are the evidence layer; ontology state is derived from them.
- Recommendation inputs may use stated evidence and intentions confirmed or corrected by the user. Unconfirmed inferred intentions remain hypotheses and must not silently affect ranking.
- Preserve source IDs, explicitness, status, and correction history when merging or relabeling intentions.
- Synthetic ground truth must not be visible to the live service-agent recovery path. Post-hoc evaluation metadata is written only after a simulation finishes.

### Serialization

- Return API payloads through `db/serializers.py`; never expose ORM instances directly.
- Preserve the camelCase wire contract consumed by `frontend/lib/types.ts`.
- Add a serializer alongside a new model or response shape, and update the frontend contract in the same change.

## Child Guide Routing

- Read `agents/AGENTS.md` before changing turn orchestration, planner actions, recommender calls, or response grounding.
- Read `llm/AGENTS.md` before adding a model task or changing provider, prompt, schema, mock, or retry behavior.
- Read `products/AGENTS.md` before changing seed loading, retrieval, hard constraints, profiles, embeddings, or ranking inputs.
- Rules in a child guide refine this file for that subtree; this file remains authoritative for cross-domain boundaries.
