# ValueCommit Graph Ontology — Design & Implementation Plan

**Date:** 2026-06-10 (decisions A1–A4 resolved 2026-06-11; framing revision F1 2026-06-11)
**Status:** design accepted; Phases 1–3 implemented (see §6); Phase 4 pending data

> **F1 — framing revision (2026-06-11): the "global trait / local motivation" two-tier
> reading is retired.** TCV values are *choice-situational* by the theory's own axioms
> (values contribute differentially per choice situation; Conditional value is defined
> situationally), so treating the TCV-5 as stable person traits was a misreading. Both
> dimensions are now read as **two scenario-scoped lenses on one choice situation**:
> the value dimension (TCV 5) explains *why this alternative is worth choosing*
> (choice/object level); the motivation dimension (A&R 6 + Babin) explains *why engage
> in shopping at all* (activity/episode level). Participant-level accumulation
> (`AnchorMapping` per participant, spec file, RIG) is **reinterpreted, not removed**:
> it is memory of *recurring patterns across choice situations* — a hypothesis source
> for the next session — not a stable-trait estimate. Synthesis GT moved to
> persona×scenario units accordingly (`personas_nemotron_profiles_v2.json`). Graph
> structures below are unchanged; wording that asserted the old reading is edited in
> place and the original phrasing is preserved in git history. Internal identifiers
> (`TRAIT_ANCHORS`, "trait" edge labels) are kept for migration safety.
**Related:** `research-framing.md` (RQs), `formative-study-design.md` (FS1),
`algorithm-audit.md` (constants must be justified there), theory module spec
(`../../ValueCommit_Theoretical_Module_Upgrade_Spec.md`), RIG paper
(Relational Intention Graph; Amazon M2, intent nodes + VERA-validated
intent–intent relations + concept tier).

---

## 1. Purpose and decisions

This document specifies the target graph ontology for ValueCommit and how to
implement it on top of the existing codebase. It records four design decisions
made during planning:

| # | Decision | Rationale |
|---|---|---|
| D1 | **Explicitness becomes a property of evidence edges, not intention nodes.** A node is *hidden* iff it has no explicit-channel evidence edge. | The same intention can be supported by an utterance (explicit) and by feedback (latent). A single node label conflates channels; the per-edge definition makes "hidden" precise and makes Latent Yield auditable. |
| D2 | **No theory–theory edges.** Theory-stage transitions remain *derived analytics* (aggregated trajectory statistics in `rig.py`), never asserted ontology edges. | Neither TCV (Sheth/Newman/Gross) nor Arnold & Reynolds is a stage theory. Asserting a logical order would invent unsupported structure. Empirical transition statistics (e.g., hedonic→utilitarian drift) stay queryable without being ontological claims. |
| D3 | **"Topic" is renamed "Intention" at the conceptual level.** `IntentionTopic` *is* the intention node of the planned graph. | The plan's 의도 node and the implemented topic are the same construct; the dual naming caused repeated confusion. DB table names stay (migration safety); docs, research views, and new code use *intention*. |
| D4 | **Causal intention–intention edges require a validation protocol** (threshold + verification status + human annotation sample). | RIG's lesson: relation classification went through a dedicated validator (VERA, PDTB-trained, F1 0.89, 0.9 threshold). No Korean VERA exists, so we use an LLM judge with a fixed rubric, thresholding, and sampled human verification. |

### 1.1 Resolved structural decisions (2026-06-11)

| # | Decision | Rationale |
|---|---|---|
| A1 | **Rejection/avoidance is NOT a negative edge.** The rejection *event* stays in the evidence layer (`FeedbackEvent` valence on the Product–Dialogue edge); the rejection's *meaning* enters the intention layer as an ordinary Intention node with `kind="avoidance"`. Meta-path statistics MUST split counts by `kind` so "sought X" and "avoided X" never aggregate into one number. | A negative edge captures *what* was rejected but not *why* — and the why is the research object. Avoidance-as-node keeps the criterion externalizable (chip), correctable, anchor-mappable, and meta-path-eligible. |
| A2 | **No cross-session intention–intention edges.** `IntentionRelation` stays session-scoped. Cross-session structure exists only in the personal-global graph and is mediated by shared Concept/Theory nodes (as `rig.py` already does via concept sequences). | Cross-session LLM pair classification is combinatorially expensive and unverifiable. Note: RIG's meta-paths were population-scoped because Amazon sessions are anonymous; with `Participant` the same path template reads primarily as a *within-person* trajectory. |
| A3 | **Concept is a shared dictionary; instance graphs are per-user.** The instance layer (dialogues, intentions, evidence, trait accumulations) is strictly per-participant and never merges. The vocabulary layer (Theory ×12, Product catalog, Concept dictionary) is shared by design — two users' intentions may *reference* the same concept entry, which holds no user data. **Cross-user borrowing is a separate, initially-OFF switch**: enabled only when the user's own history is empty (back-off order: personal > population), output restricted to clarify questions/probes (never silent recommendation changes), conditioned on concept × scenario, and gated by **concept stability** — the cross-user variance of anchor distributions among intentions referencing the concept ("선물" is stable/safe; "가성비" is value-laden/unsafe). Rejection rate of borrowed anticipatory questions is the borrowing-quality metric, measurable on the synthesis corpus first. | Per-user independence and RIG-style sparsity relief coexist by separating instance from vocabulary. Externalization (DG1–3) converts population priors from silent stereotyping into correctable hypothesis proposals. |
| A4 | **The graph holds current state only; history is reconstructed from three existing mechanisms**: (1) `correction_events` (UI edits: before/after + turn), (2) `PreferenceStateSnapshot` (per-turn state replay), (3) `REVISES`/`WEAKENS` relation chains (dialogic revision creates a new node pointing at the weakened old one — history visible *in* the graph). No new versioning infrastructure. Known asymmetry to handle at analysis time: chip edits mutate in place + log; dialogic revisions append nodes + edges — "correction counts" must union both sources. | The system is already event-sourced enough; a bi-temporal graph would duplicate it. |

What this graph is *for* (in priority order):

1. **Hidden-intention provenance** — every value claim traces to evidence with
   a channel label (the research identity; must survive any extension).
2. **Meta-path inference** — anticipatory clarification, final-intention
   prediction, recommendation explanation (`rig.py`, clarify tier 2).
3. **Sparsity relief** — borrowing evidence across users through shared
   Concept/Theory nodes (population scope).

---

## 2. Graph schema

### 2.1 Node types (5)

| Node | Definition | Backing store | Cardinality |
|---|---|---|---|
| **Product** | An item from Naver shopping data (currently 12 seed mocks) | `Product` | thousands (Naver) |
| **Dialogue** | One user–agent session | `Session` | per session |
| **Intention** | Natural-language sentence the LLM hypothesizes from evidence ("선물로 너무 저렴해 보이지 않기") | `IntentionTopic` | per session, ~3–10 |
| **Concept** | 1–3 word abstraction of intentions; cross-session TBox with lifecycle + origin provenance | `Concept` | shared, grows |
| **Theory** | One of 12 fixed elements: 5 TCV trait anchors + 7 motivation dims | enumeration in `ontology/anchor_mapper.py` (`TRAIT_ANCHORS`, `MOTIVATION_DIMS`); materialized as nodes only in graph export | exactly 12 |

An Intention node is a **hypothesis, not a fact**: its validator is the user
(chip confirm/reject/edit), not the LLM. This is the deliberate difference
from RIG, whose intent nodes are population-level plausibility statements
generated from product attributes with no per-user evidence.

### 2.2 Edge types

**Attribution edges**

| Edge | Backing store | Notes |
|---|---|---|
| Product → Dialogue | `ProductImpression` (+ `FeedbackEvent` for valence: like/dislike/purchase) | exists |
| Dialogue → Intention (**evidence edge**) | **NEW: `IntentionEvidence`** (§4.1) — currently only the `evidence_ids` JSON list on the topic | carries `channel` + `explicitness` per edge (D1) |
| Intention → Concept | `TopicConcept` | exists |
| Concept → Theory | `ConceptAnchorMapping` | exists |
| Intention → Theory (value) | `AnchorMapping` (score, confidence, evidence_strength, decision_impact, temporal_status, rationale) | exists; targets the TCV value dimension only (internal name `trait` kept) |
| Dialogue → Theory (motivation) | `PreferenceStateSnapshot.motivation_scores` | motivation edges hang off the Dialogue node, **not** Intention nodes. This asymmetry is intentional and mirrors the two lenses (F1): values attach to choice criteria (intentions); motivations attach to the shopping episode (dialogue). |

**Intention–intention edges** — already implemented in
`ontology/relation_classifier.py`. Eight relation types meta-classified into
the three natures from the RIG paper via `RELATION_NATURE`:

| Nature | Types | Semantics |
|---|---|---|
| co_occurrence (동시적) | CONFLICTS_WITH, SUPPORTS, PRIORITIZES | appear together in one session |
| temporal (비동시적) | REVISES, WEAKENS, RESOLVES | later modifies earlier |
| causal (인과) | MOTIVATES, REFINES | one intention logically induces another — **requires validation (D4, §4.4)** |

**Explicitly absent:** Theory → Theory (D2). `rig.py::theory_transitions`
keeps computing dominant-anchor transition counts from value trajectories as a
*report*, not as graph edges.

---

## 3. Mapping: planned construct → existing code

Most of the plan already exists. Implementation is therefore mostly
*formalization*, plus the four deltas in §4.

| Planned | Existing | Gap |
|---|---|---|
| Intention node | `IntentionTopic` | naming only (D3) |
| Concept node (1–3 words) | `Concept` + `ontology/conceptualizer.py` | none |
| Theory node | `TRAIT_ANCHORS` + `MOTIVATION_DIMS` | materialize in graph export |
| Intention–intention relations (3 natures) | `relation_classifier.py::RELATION_NATURE` | causal validation (D4) |
| Meta-paths, intention prediction, sparsity borrowing | `rig.py` (A: theory_transitions, B: session_meta_path, C: predict_intentions) | extend to population scope (§5) |
| Dialogue–Intention evidence with channel | `IntentionTopic.evidence_ids` (flat JSON) + node-level `explicitness` | **new `IntentionEvidence` table (D1)** |
| Product nodes from Naver data | 12 seed mocks via `products/seed_loader.py` | Naver loader (§7) |

---

## 4. Design changes (the deltas)

### 4.1 D1 — Evidence edges carry explicitness

**New table** (auto-created by `create_all`; no `_migrate` entry needed for
new tables):

```python
class IntentionEvidence(Base):
    __tablename__ = "intention_evidence"
    id: str                      # pk
    topic_id: str                # FK intention_topics.id
    evidence_type: str           # turn | feedback | impression | pair
    evidence_id: str             # id in the corresponding evidence table
    channel: str                 # user_utterance | feedback | product_comparison
                                 # | wimhf_discovery | agent_inference
    explicitness: str            # explicit | implicit | latent — structural, per edge
    kind: str | None             # constraint | context | preference | avoidance
    created_at: datetime
```

- `explicitness` is computed at attach time by the existing
  `ontology/merge.py::structural_explicitness(ext, source)` — the function
  stays; only its result's storage location changes (edge, not node).
- **Node-level definition becomes derived:**
  - `intention.is_hidden` ⇔ the node has **zero** edges with
    `explicitness == "explicit"`.
  - The existing `IntentionTopic.explicitness` column is kept as a **derived
    cache** (recomputed on every evidence attach in `merge.py`), so all
    current readers (`state_builder`, serializers, eval) keep working during
    migration. Rule: cache = `explicit` if any explicit edge, else `latent`
    if all edges are latent, else `implicit`.
- **Backfill:** one-shot script iterates existing topics, emits one
  `IntentionEvidence` row per entry in `evidence_ids`, recomputing
  explicitness from the topic's `source` + `hints.kind` (same inputs
  `structural_explicitness` uses today). Old data keeps its semantics.

**Latent Yield v2** (`evaluation/ontology_eval.py::compute_latent_yield`):

```
hidden(t)        := t has no explicit evidence edge
hiddenRatio      := |{t : hidden(t)}| / |topics|
hiddenConfirmRate:= |{t : hidden(t) ∧ t.status ∈ CONFIRMED}| / |{t : hidden(t)}|
latentYield      := hiddenRatio × hiddenConfirmRate
```

Report v1 (node-label based) and v2 side by side for one release to check the
metric shift; `docs/algorithm-audit.md` gets an entry for the v2 definition.
The per-edge granularity also enables the human-coder agreement check that
`research-framing.md` §6.5 lists as an unresolved limitation — coders judge
*edges* (one evidence span, one channel), which is a far better-defined task
than judging whole topics.

### 4.2 D3 — Naming

- Docs, research UI labels, paper text: **intention** (의도).
- DB tables/ORM classes unchanged (`IntentionTopic`, `intention_topics`).
- New modules use `intention` in identifiers.

### 4.3 D2 — Theory tier stays edge-free among itself

- The 12 theory nodes appear in graph exports with their tier
  (`trait` | `motivation`).
- Value (TCV) theory edges attach to Intention/Concept nodes — choice-level
  lens; they also accumulate per `Participant` as recurring-pattern memory (F1).
- Motivation theory edges attach to Dialogue nodes — episode-level lens; they
  live on snapshots.
- `theory_transitions` output is labeled "observed transition statistics" in
  the research UI — never rendered as graph edges.

### 4.4 D4 — Causal-edge validation protocol

The relation pipeline gains a verification stage:

1. **Prompt change** (`llm/prompts.py`, task `relation_classification`): for
   MOTIVATES/REFINES the model must also emit
   `plausibility: number (0..1)` and a one-sentence justification.
   Per CLAUDE.md, the mock handler in `llm/mock_rules.py` must be updated in
   the same commit as the prompt contract.
2. **Threshold:** causal relations with `plausibility < THRESHOLD` are
   downgraded to nature `co_occurrence` (kept, not dropped — the co-occurrence
   fact is still true). `THRESHOLD` starts at 0.9 (RIG's value) and must be
   justified/recalibrated in `algorithm-audit.md` once we have human-annotated
   samples.
3. **Schema:** new column on `IntentionRelation` (additive `ALTER` in
   `db/database.py::_migrate`):
   `verification: str = "unverified"  # unverified | llm_thresholded | human_verified | human_rejected`
4. **Human annotation sample:** for any corpus used in a paper, sample N≥100
   causal edges, two annotators, report agreement (κ) and precision; feed the
   measured precision back into the threshold choice. (This replaces RIG's
   VERA step, which does not transfer to Korean.)
5. Judge independence: when providers allow, run the relation-judging call
   with a different model (or at minimum a different prompt persona) than the
   extraction call, to reduce self-agreement bias.

---

## 5. Graph scopes — local / personal-global / population

Three induced views over one store. The scope is a *query parameter*, not
three databases.

| Scope | Induced by | Contains | Consumer |
|---|---|---|---|
| **Local** | one `session_id` | session's Intentions, evidence edges, motivation edges, intra-session relations | participant UI (chips), `/research/session/:id` |
| **Personal global** | one `participant_id` (all their sessions) | union of locals + accumulated trait edges + cross-session relations | spec builder, RIG anticipatory clarify, multi-session main study |
| **Population** | whole store | everything, joined through shared Concept and Theory nodes | sparsity borrowing, meta-path statistics, SME view |

**Recurrence promotion rule (session → participant memory).** Value evidence
observed in a session is *discounted by what the scenario already predicts* and
*promoted by cross-scenario recurrence*:

```
value_weight(evidence) = base_weight
                       × scenario_discount   # lower when the scenario type predicts
                                             # this anchor (gift → Social, Role)
                       × recurrence_boost    # higher when the same anchor was
                                             # evidenced in ≥2 distinct scenario types
```

Exact constants are an open calibration item (→ `algorithm-audit.md`; tune on
the synthesis branch's cross-scenario disentanglement test before the
multi-session main study). The principle (F1 reading): **a single session never
establishes a recurring pattern; recurrence across distinct scenario types does.**
What accumulates is a defeasible prior — each new choice situation still gets
fresh inference, with the accumulated pattern surfacing only as hedged
anticipatory questions (RIG), never as silent assumptions.

**Population-scope caveat (record in any paper):** meta-paths mined from
synthetic dialogues reflect injected persona logic. Predictions validated only
against more synthetic users are circular. External validity of the population
graph requires human data (multi-session main study; Naver logs if available).

---

## 6. Implementation phases

Additive-only migrations throughout (new tables via `create_all`, new columns
via `_migrate`), per CLAUDE.md. Every phase keeps `pytest tests/ -q` green
under the mock provider.

> **Implementation status (2026-06-11):** Phases 1–3 implemented and tested
> (`tests/test_graph_ontology.py`, 16/16 suite green; backfill applied to the
> dev DB — 632 topics → evidence edges). Phase 4 pending Naver data.
> New constants recorded in `algorithm-audit.md` (causal threshold 0.9,
> explicitness cache rule).

### Phase 1 — Evidence edges (foundation; enables Latent Yield v2) ✅
- `db/models.py`: add `IntentionEvidence`.
- `ontology/merge.py`: on topic create/merge, write evidence-edge rows with
  per-edge `structural_explicitness`; maintain the node-level cache.
- Backfill script `scripts/backfill_intention_evidence.py`.
- `evaluation/ontology_eval.py`: Latent Yield v2 (+ v1 alongside).
- `db/serializers.py`: serialize evidence edges (evidence drawer gains
  per-evidence channel/explicitness display — strengthens DG2).
- Tests: structural explicitness per channel; hidden-node derivation; v1↔v2
  comparison on the seeded demo session.

### Phase 2 — Causal validation ✅
- `llm/prompts.py` + `llm/mock_rules.py`: plausibility in the relation
  contract (both, same commit).
- `relation_classifier.py`: threshold + downgrade; `_migrate`: `verification`
  column.
- `api/research.py`: expose verification status; research UI badge.
- Annotation export: JSONL of causal edges for the human sample.

### Phase 3 — Graph materialization & scopes ✅ (graph export + API; rig.py population stats deferred to Phase 4)
- New `app/graph/export.py` (or extend `evaluation/export_builder.py`):
  emit nodes/edges as JSONL per scope; theory nodes materialized with tier.
- `api/research.py`: `GET /api/research/graph?scope=local|participant|population&id=...`.
- `rig.py`: extend path statistics from per-participant to population scope
  (same meta-path templates: D→I→C→I′→D′, I→T→I′, D→I→P).
- Trait promotion rule in the participant accumulation path; constants
  documented in `algorithm-audit.md`.

### Phase 4 — Population scale
- Naver product loader (replaces/extends `products/seed_loader.py`;
  `cue_extractor.py` recalibrated for real category price distributions —
  the relative-in-category cue logic already anticipates this).
- Ingest synthesis-branch corpora (user-agent sessions are already ordinary
  sessions, so they enter the graph with no special path — only a
  `mode="simulation"` filter for analyses that must exclude them).
- Population meta-path evaluation: RIG-style intention-prediction MRR as a
  sanity metric; recovery-rate evaluation against injected persona GT
  (synthesis branch protocol).

---

## 7. Evaluation hooks per branch

| Branch | Metric | Scope | Requires |
|---|---|---|---|
| CHI / FS1 | Latent Yield v2; ground-truth gap (recall interview ↔ graph) | local | Phase 1 |
| CHI / main study | correction → alignment effects; trait formation over sessions | personal global | Phases 1, 3 |
| Synthesis | injected-GT ↔ recovered comparison (both dimensions, evaluated later by human + LLM judge — no automatic match verdicts); convergence under correction ON/OFF; cross-scenario sensitivity | local + personal global | Phases 1, 3 + persona×scenario GT v2 (done) |
| Synthesis (graph) | causal-edge precision (human sample); meta-path prediction MRR | population | Phases 2, 4 |

---

## 8. Open questions

1. **Persona GT respec — RESOLVED (F1, 2026-06-11).** GT is now specified per
   persona×scenario in `seed/personas_nemotron_profiles_v2.json`: value-5 levels
   AND motivation-7 levels both scenario-conditioned, derived from the narrative
   with anti-stereotype discipline (`derive_persona_profiles_v2.py`). Sessions
   stamp `meta.gtVersion` so later evaluation can join the right GT file.
   (`seed/personas.json` legacy `valueOrientation` remains for the deterministic
   runner only.)
2. **Promotion-rule constants** — scenario_discount / recurrence_boost values;
   calibrate via synthesis before the multi-session main study.
3. **DG4 (recall-first) vs `state_builder.py:124`** — the
   `priority in ("high","medium")` filter hides low-priority intentions from
   chips, contradicting recall-first externalization. Decide before FS1; the
   decision also shapes the "correctable surface coverage" metric (you can
   only correct what is shown).
4. **Should the user-agent correct chips?** Currently simulations only
   auto-resolve conflicts; adding a GT-driven chip-reaction policy would put
   `correction_events` into synthetic corpora (dialogue + chosen-rejected +
   correction traces — a dataset signal no existing CRS corpus has).
   Tracked in the synthesis branch plan, not blocked by this document.
