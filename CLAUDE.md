# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**ValueCommit Shopping Agent Demo** — an HCI research prototype, not a shopping recommender. It studies how a conversational agent infers a user's *hidden intentions* (value-grounded decision criteria the user didn't state) from utterances + chosen/rejected feedback, externalizes them, and lets the user correct them. The research goal is **surfacing hidden intention**, not recommendation accuracy.

The project sits inside a larger research repo. The actual app is `valuecommit/`. Sibling spec/design docs live one level up: `../ValueCommit_Shopping_Agent_Coding_Spec.md` (the implementation spec, sections referenced in code as `§N`), `../ValueCommit_Theoretical_Module_Upgrade_Spec.md` (theory module), `../ValueCommit_Theoretical_Rationale_Note.md`. The `../PSCon/` dataset is a CRS benchmark used for scenario seeding and analysis (it is *not* loaded at runtime).

In-repo design docs under `docs/` are the source of truth for non-obvious decisions: `research-framing.md` (HCI experiments/RQs), `formative-study-design.md` (FS1 study + Design Goals DG1–DG6), `algorithm-audit.md` (every heuristic/constant justified or flagged), `pscon-analysis.md` (EN/CN data findings), `ontology-graph-design.md` (graph ontology: node/edge schema, evidence-edge explicitness, graph scopes, resolved decisions D1–D4/A1–A4), `llm-measurement-design.md` (categorical-over-scalar measurement M1–M9, rubric prompts, judge layer — implemented; `app/ontology/levels.py` is the level→cache conversion source), `session-handoff.md` (most recent UI/feature work, current run state, TODO, detached-server ops — read this to resume mid-stream work). **Read the relevant doc before changing scoring weights, prompts, or the ontology pipeline.**

## Commands

```bash
# Backend (FastAPI, :8000) — run from valuecommit/backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --port 8000

# Tests (always run with the mock provider; no API key needed)
.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m pytest tests/test_acceptance.py::test_3_conflict_detection -q   # single test

# PSCon real-dialogue prevalidation (makes real LLM calls)
.venv/bin/python scripts/pscon_prevalidation.py

# Re-sample the simulation persona pool from Nemotron-Personas-Korea (HF datasets-server; seed 42)
.venv/bin/python scripts/sample_nemotron_personas.py

# Synthesis v2 (real LLM calls): derive persona×scenario GT, then run batches
.venv/bin/python scripts/derive_persona_profiles_v2.py          # → seed/personas_nemotron_profiles_v2.json
.venv/bin/python scripts/run_llm_simulations_v2.py              # single session → data/synthesis_v2/
.venv/bin/python scripts/run_multi_session_simulations_v2.py    # 10 × 2 sessions → data/synthesis_multi_v2/

# Batch-analyze PSCon conversations through the pipeline (offline, resumable; real LLM calls)
.venv/bin/python scripts/analyze_pscon.py 50   # N convs; omit N = all 648 → backend/data/pscon_analysis.json

# Frontend (Next.js 14, :3000) — run from valuecommit/frontend
npm install && npm run dev
./node_modules/.bin/tsc --noEmit     # typecheck (preferred over `next build` while dev server runs)

# NAVER formative-study variant (real NAVER products + persistent study DB) — from valuecommit/backend
bash run_nv_study.sh          # pins VC_SEED_DIR=seed_naver (600 enriched NAVER products) + VC_DB_PATH=nv_study.db; .env supplies LLM keys
# detached (survives shell/session close): nohup bash run_nv_study.sh > .uvicorn_naver.log 2>&1 & disown
```

## Deployment (Railway, Nixpacks — no Docker)

Two Railway services off one GitHub repo (`valuecommit/` is the repo root). See `DEPLOY.md` for the step-by-step runbook. Backend uses `backend/Procfile` (`uvicorn … --port $PORT`); frontend is auto-detected Next.js (`next build`/`next start`, honors `$PORT`). All config is env-driven (`app/core/config.py`) — see `backend/.env.example`. SQLite lives on a Railway volume at `/data`. (Docker/compose files were removed 2026-06-19 — Nixpacks builds both services.)

**Do not run `next build` while `next dev` is running** — they share `.next/` and corrupt each other's chunks (`Cannot find module './948.js'`). Use `tsc --noEmit` to verify types; only build after stopping the dev server.

The frontend proxies `/api/*` to the backend via `next.config.mjs` rewrite (`BACKEND_URL`, default `http://localhost:8000`). Browser-facing tests should hit `:3000`, not `:8000` directly.

**Two DBs + two seed dirs (env-driven, `app/core/config.py`).** `VC_DB_PATH` selects the SQLite file: the original demo/simulation data is `backend/valuecommit.db`; the NAVER formative-study runs against `backend/nv_study.db`. `VC_SEED_DIR` selects the startup seed dir: default `seed/` (demo products), `seed_naver/` for the 600 enriched NAVER products (built by `scripts/build_naver_products.py`, image/seller/category/real-price enriched by `scripts/enrich_naver_images.py` via the Naver Search API). `run_nv_study.sh` pins both and is the canonical way to start the NAVER backend (its launch env was previously undocumented and easy to forget). Both servers are launched detached (`nohup … & disown`), so they outlive the starting shell/session — check with `lsof -i :8000 -i :3000`, and never start a second copy on a port already bound. (The study DB previously lived in the ephemeral `/tmp` — moved to a persistent path 2026-06-17.)

## LLM provider layer (central abstraction)

All model calls go through `app/llm/provider.py::get_provider()`, selected by `VC_LLM_PROVIDER` (`mock` | `openai` | `deepseek` | `anthropic`). Config + `.env` loading is in `app/core/config.py`. `DeepSeekProvider` subclasses `OpenAIProvider` (DeepSeek is OpenAI-compatible, base `https://api.deepseek.com`; model via `VC_DEEPSEEK_MODEL`).

- Pipeline stages never call a model directly — they call `provider.generate_json(messages, task="...", context={...})`. The `task` string is the dispatch key.
- **MockLLMProvider** is a deterministic rule engine (`app/llm/mock_rules.py`, `TASK_HANDLERS` dict). It is the default, requires no API key, reproduces the gift-smartwatch demo exactly, and is what **all tests run against**. Every pipeline `task` must have a mock handler.
- **Real providers** render the system prompt + per-task JSON contract from `app/llm/prompts.py` (`SYSTEM_BY_TASK`, `FORMAT_BY_TASK`) and parse JSON tolerantly. Adding a pipeline stage = add to `mock_rules.TASK_HANDLERS` **and** `prompts.SYSTEM_BY_TASK`/`FORMAT_BY_TASK`.
- Small models (gpt-4o-mini) are unreliable on self-classification. Two structural corrections already exist and should be preserved: anchor names are split when the model emits `"Social|Conditional"`, and **`explicitness` is derived structurally from source** (`ontology/merge.py::structural_explicitness`), NOT from the model's self-label — feedback-derived topics are implicit/latent by construction (theory §2.2). Pipeline stages are wrapped in `_safe()` so one malformed stage degrades gracefully instead of 500-ing the turn.

## Backend architecture: the Preference Commit pipeline

The core flow is in `app/preference_commit/commit_engine.py::run_preference_commit`, invoked on every user turn and every feedback event. New evidence (turns/feedback) is treated as a *commit* against the current preference state:

```
extract topics → semantic merge → (anchors ∥ concepts ∥ relations ∥ conflicts) → snapshot
```

**Concurrency design (critical, do not break):** SQLite write locks must NOT be held across slow LLM calls, or simulations and live browser sessions deadlock (`database is locked`). The pattern is **LLM-first, write-last**:
1. `service_agent.py` saves the turn/feedback and `db.commit()`s *immediately* (releases the lock).
2. The commit engine runs all LLM fetches (topic extraction, then anchors/concepts/relations/conflicts via `asyncio.gather`) against read-only context — no writes held open.
3. All DB mutations happen in one short transaction at the end (`merge_topics` → `apply_*`).

Each ontology stage is split into `fetch_*` (LLM, no DB) and `apply_*` (DB, no await) — keep this separation when editing `app/ontology/`. SQLite runs in WAL mode with `busy_timeout=30000` (`app/db/database.py`).

### Three-layer ontology (the data model)

`app/db/models.py` (SQLAlchemy, SQLite). Theory-grounded structure:
- **Layer 1 Evidence**: `Turn`, `ProductImpression`, `FeedbackEvent`
- **Layer 2 Intention** (session-scoped, ABox): `IntentionTopic`, `Concept`, `AnchorMapping`, `ConceptAnchorMapping`, `IntentionRelation`, `PreferenceConflict`
- **Layer 3 Value** — a **two-dimension situational value model** (replaced the old flat 6-anchor list; the earlier "global trait / local motivation" framing was retired 2026-06-11 — TCV values are choice-situational by the theory's own axioms, not stable person traits; see `docs/ontology-graph-design.md` note F1). Both dimensions are defined in `ontology/anchor_mapper.py`, are **scenario-scoped**, and answer different questions about one choice situation:
  - **Value dimension** (TCV 5, Sheth/Newman/Gross 1991): `Functional`, `Social`, `Emotional`, `Epistemic`, `Conditional` — *why this alternative is worth choosing* (choice/object level). The intention→theory anchor mapping targets *only* this dimension (`TRAIT_ANCHORS` — internal name kept for migration safety; `VALUE_ANCHORS` aliases it).
  - **Motivation dimension** (Arnold & Reynolds 2003 hedonic 6 + Babin utilitarian): `Adventure`, `Gratification`, `Role`, `BargainValue`, `SocialShopping`, `Idea`, `Utilitarian` (`MOTIVATION_DIMS`) — *why engage in shopping at all* (activity/episode level), *elicited through dialogue, not a survey*, stored on `PreferenceStateSnapshot.motivation_scores`.

**Cross-session unit:** `Participant` spans a user's sessions; value scores and a human-readable **natural-language spec file** (`spec_markdown`/`spec_version`, synthesized by `spec_builder.py` — a read-only mirror of the KG) accumulate on it — read as **memory of recurring patterns across choice situations** (a hypothesis source for the next session, surfaced as hedged anticipatory questions), not a stable-trait estimate. A session is created against an existing `participantId` or mints a new participant (`api/sessions.py`).

`Concept` is the cross-session TBox with a lifecycle (`seed→observed→candidate→validated→confirmed→revised`) and `origin` provenance (`top_down_seed`/`llm_extraction`/`bottom_up_feature`/`user_correction`). Seed concepts/products/scenarios/personas load from `backend/seed/*.json` on startup (`products/seed_loader.py`). DB schema changes for new *columns* go in `app/db/database.py::_migrate` (additive `ALTER`, preserves demo data); new *tables* are auto-created by `create_all`.

Serialization to camelCase JSON for the frontend is centralized in `app/db/serializers.py` — never return ORM objects directly.

### Key subsystems

- `app/agents/service_agent.py` — turn/feedback orchestration; `action_selector.py` (rule-based next action), `response_generator.py` (LLM rewrites Korean templates; strips markdown). **Clarify-question priority is 3-tiered:** (1) `motivation.py` probe for an un-elicited shopping-motivation dim → (2) `rig.py` anticipatory question from a cross-session meta-path prediction → (3) `question_strategy.py` value-level adaptive clarify (most-uncertain *trait* anchor).
- **Theory-upgrade modules — deterministic, NOT LLM pipeline tasks (so no mock handler / prompt contract needed):** `agents/motivation.py` (keyword `detect_motivation`/`merge_motivation`/`next_probe` for the motivation tier, accumulated on `session.meta.motivationScores`), `rig.py` (Relational Intention Graph — cross-session `대화→의도→이론→의도→상품` meta-paths for next-intention/product prediction; surfaced under `/api/research/rig/*` + `/sessions/{id}/predict`), `spec_builder.py` (`update_participant_spec` re-renders the participant spec markdown each turn), `products/cue_extractor.py` (relative-in-category price cue, §6.1).
- `app/agents/user_agent.py` + `app/api/simulations.py` — the **synthetic-data simulation** (`/simulate`): a *deterministic scripted* User Agent drives the real Service Agent across persona × scenario to stress-test the pipeline (`evaluation/simulation_eval.py`). **The persona pool is now `nvidia/Nemotron-Personas-Korea`** — 50 sampled proportionally (seed 42) into `seed/personas_nemotron.json` (regenerate via `scripts/sample_nemotron_personas.py`); `load_personas()` prefers that file, else the hand-authored `personas.json`. Personas are simulation-only; the study/shopping flow never reads them.
- `app/agents/llm_user_agent.py` — the **LLM-driven user agent** (synthesis branch): role-plays a Nemotron narrative persona against the real Service Agent. Its hidden GT profile is **persona×scenario-conditioned** (v2 — values/motivations are situational): derived from the narrative by `scripts/derive_persona_profiles_v2.py` into `seed/personas_nemotron_profiles_v2.json` (anti-stereotype discipline: cited narrative grounds + `personaDistinction`), injected only into user-agent LLM calls, **never stored in `session.meta`** (the service agent reads meta — leaking GT would contaminate recovery); only a `meta.gtVersion` stamp links the session to its GT file for later evaluation. Batch runners: `scripts/run_llm_simulations_v2.py` (single session, matched scenario) and `scripts/run_multi_session_simulations_v2.py` (same persona × 2 scenarios under one `Participant`, **different GT per session**). Review outputs (`data/synthesis_v2/`, `data/synthesis_multi_v2/` + the `/simulate` synthesis viewer) record injected GT and recovered axes **side by side with no automatic match verdicts** — evaluation (human + LLM judge) is a deliberately separate later phase; generation only preserves evaluability. v1 artifacts (`personas_nemotron_profiles.json`, `run_llm_simulations.py`, `run_multi_session_simulations.py`, `data/synthesis_test/`, `data/synthesis_multi/`) are kept as the record of pre-F1 runs — don't regenerate over them.
- `app/products/` — product search is **BM25(FTS5) retrieve → tag filter → trade-off rank** (replaced the old full-scan 2026-06-17, for catalog scalability). `search_index.py` builds a SQLite FTS5 virtual table (`tokenize='trigram'` — robust to Korean 조사/복합어) at startup (`main.py` lifespan) over `title+tags+description+category`; `retrieve(query, n=200, category)` returns BM25-ranked ids and is the **swappable retrieve interface** (future: embedding rerank). `search.py::search_products` = retrieve → image filter → `hard_constraint_match` (price/demo attrs — **kept**, not replaced, so the 24 mock tests stay green) → `tag_filter.py` mutex-tag constraint (유선↔무선·반팔↔긴팔·넥라인… — drop products holding only the *opposite* of a required tag; `required_tags()` = query substrings in the vocab) → `scoring.py` §14.2 weighted score + tag-match bonus → `select_tradeoff_set` (reserves a **diagnostic slot** `PROBE_RULES` for an active-learning value probe). Empty retrieve → category/all fallback. `Product.tags` (JSON column, added via `_migrate`) carries the canonical labels.
- **NAVER product pool + labeling** (`docs/plans/2026-06-17-product-labeling-retrieval-plan.md`): `scripts/build_naver_products_stratified.py` samples top-by-purchase per **fine category** from the 4 NAVER `*.csv.gz` (joined on 19-digit catalogId — see memory `naver-smartstore-data-decode`) → `seed/products_stratified.json`; **sub-agent labeling** (one agent per category) writes `seed/labels/*.json` (tags from the fixed vocab in `config/tag_taxonomy.json`, no-hallucination) → merged `products_stratified.labeled.json` → junk-cleaned `products_stratified.clean.json`. **Labeling standard: the structured signal is `tags` (canonical per-category vocab); `attributes` holds metadata only (`categoryId`/`domain`) — no freeform keys.** (`scripts/build_naver_products.py` is the earlier *domain-only* 600-item sampler that `seed_naver/` was built from; the stratified+labeled pool is the newer, category-balanced one.)
- `app/wimhf/` — chosen-rejected pair mining → bottom-up `DiscoveredFeature` → researcher approval folds it into a `Concept` (`ontology_expander.py`).
- `app/evaluation/` — `value_profile.py` (continuous anchor/user-type/feature vector), `ontology_eval.py` (**Latent Yield** = implicit-latent ratio × user-confirm rate — the headline hidden-intention metric), `export_builder.py` (JSONL export of all tables).
- `app/api/study.py` — Formative-study (FS1) instrumentation: observation markers, evidence-inspection logging, recall-interview ground-truth gap analysis. **Pre-survey:** `POST /api/study/survey` persists the FS1 pre-survey (defined in `frontend/lib/survey.ts`, sections A–F — D=value TCV5, E=motivation, F=AI expectations; `computeProfile`/`SCORING` derive value/motivation/CorrectabilityNeed scores) onto `Participant.survey` (`{answers, profile}` JSON). This survey-derived profile is **probe-prep / researcher reference, not the runtime motivation tier** (that stays dialogue-elicited via `motivation.py`). Researcher review: `GET /api/research/participants/{id}/survey` + a `hasSurvey` flag on `list_participants` (`app/api/research.py`). The `survey` column is added by `database.py::_migrate`; older DBs created before it need that migration (fresh DBs get it from `create_all`).

## Frontend

Next.js App Router, Tailwind, no component lib. `lib/api.ts` is the single API client; `lib/types.ts` mirrors the backend camelCase types. The landing `/` is a launcher (numbered entries to the four surfaces); the header logo is a plain `ValueCommit` wordmark. Four surfaces: `/study/session/*` (participant — shows chips/conflict-card/evidence-drawer only, **never the full graph**, per spec §36), `/simulate` ("합성 데이터 생성 시뮬레이션" — the persona picker is a responsive card grid with DiceBear `notionists` avatars + a left-identity / right-narrative detail modal), `/research/*` (full ontology graph, trajectory, pairs, features, SME view, gap analysis), and `/pscon` (read-only viewer of 648 real PSCon shopping dialogues + a **precomputed-batch** pipeline-analysis radar — `scripts/analyze_pscon.py` writes `backend/data/pscon_analysis.json`, served by `app/api/pscon.py`; the web never runs analysis on-demand). `/study/session/new` can attach the session to an existing `Participant` (or mint one); `/research/session/:id` carries **`spec`** (participant spec markdown) and **`rig`** (meta-path + prediction) tabs alongside replay/ontology/trajectory. The participant flow opens with **`/study/survey`** (the FS1 pre-survey, `lib/survey.ts`, sections A–F, auto-numbered); the researcher reviews submissions at **`/research/surveys`** (left: pick a participant with `hasSurvey`; right: answers grouped by section + derived value/motivation score bars).

**Design language is indigo `#4F46E5` (brand) — deliberately not Naver green.** Positive-semantic green (`#047857`/`#ecfdf5`) is kept separate from brand color. Korean text uses `word-break: keep-all` globally (eojeol-level wrapping).

**Typography:** Google Sans (Display for `h1–h3`, Text for body) + Noto Sans KR for Hangul, loaded via a Google Fonts `<link>` in `app/layout.tsx`; the shared Korean + system fallback is the `--kr-fallback` CSS var in `globals.css`. Google Sans has no Hangul glyphs, so Korean always renders in Noto Sans KR (per-glyph fallback).

UI must follow spec §36: the agent never states inferences as fact about the user. Use hedged, correctable phrasing ("이번 상황에서는 ~을 중요하게 보고 계신 것 같아요", "맞는지 확인해 주세요"). The ontology internals (anchor scores, confidence) stay in the research views; the participant UI only shows translated, editable chips.
