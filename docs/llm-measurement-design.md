# LLM Measurement & Judge Design

**Date:** 2026-06-11
**Status:** implemented 2026-06-11 (see Implementation status below). Remaining:
state_builder noisy-OR → M4 count rules (numeric caches keep it shape-compatible
meanwhile), OQ4 (Nemotron persona GT), human-κ / regression-set protocols (§6).

**Implementation status:**
- M1–M3: `app/ontology/levels.py` is the single conversion source. Contracts now
  categorical: topic `confidenceLevel`, relation `causalEvidence`, motivation
  levels; anchor `score` dropped from the LLM contract and derived from the
  categorical triple (OQ2 resolved = derive-from-triple). Numeric columns remain
  as derived caches.
- M4 (partial): motivation accumulation uses max-level + "≥2 suggests → asserts"
  promotion; session anchor aggregation still noisy-OR over derived caches.
- M5/M6: `app/agents/judge.py` — causal-edge judge, verdict-only writes,
  `VC_JUDGE_PROVIDER` separation, async via BackgroundTasks on turns/feedback +
  manual `POST /api/research/judge/run`. Skips `judge_*`/`human_*` (authority order).
- M8: `motivation_detection` task (survey rubric + mandatory quote + polarity
  guard), keyword path demoted to failure fallback.
- P1–P3 prompt strengthening shipped (kind block, evidence discipline, Korean
  pragmatics, discrimination battery, laddering rationale, channel caps,
  direction test). Tests: `tests/test_graph_ontology.py` (suite 20/20).
**Related:** `ontology-graph-design.md` (graph schema, D1–D4/A1–A4; this doc
governs how the graph's *labels and scores* are produced and verified),
`algorithm-audit.md` (constants), CLAUDE.md LLM-provider rules (mock handler +
prompt contract must ship together).

---

## 1. Problem

Every quantitative judgment in the pipeline is currently an **LLM-emitted
scalar** whose basis is a one-line definition, one worked example, and the
model's prior. Known failure modes:

1. LLMs generate plausible-looking numbers, they don't compute them — scores
   cluster at 0.7–0.9, snap to round values, anchor on in-prompt examples.
2. There is **no shared scale across calls** — today's 0.8 and tomorrow's 0.8
   are not comparable, yet we accumulate them (noisy-OR) and compare them
   across sessions.
3. Verbalized self-assessed scores correlate weakly with accuracy
   (LLM-as-judge literature); generation-time self-scoring is the weakest form.

Separately, the graph redesign made two prompt outputs **structurally
load-bearing** without prompt support: `kind` (drives structural explicitness,
evidence-edge kind, A1 sought/avoided splits, hard-constraint vs avoidance
rendering) appears in the prompts only as a schema enum with no definitions;
`sourceEvidence` items each become graph edges that decide hidden-ness, but the
prompt does not require exhaustive citation or minimal spans.

The project already solves this class of problem twice — structural
explicitness (LLM self-label → source-based structural decision) and node
explicitness (label → edge-derived). This document extends the same principle
to all scores and adds an independent verification layer.

---

## 2. Decisions

| # | Decision | Rationale |
|---|---|---|
| M1 | **Categorical measurement.** LLMs never emit scalar scores. Every judgment is a choice among rubric levels — categories defined by observable criteria + examples — accompanied by a **mandatory quoted evidence span**. No span → no judgment for that dimension. | LLMs are reliable at rubric classification, unreliable at scalar emission. Citations block confabulation. Rubric levels are the only output a human coder can replicate, which is what makes validation possible at all. |
| M2 | **No numeric conversion in the measurement layer.** Ordered categories are stored, aggregated, and reported as categories end-to-end (KG, research views, paper analyses). Mapping levels back to numbers (e.g., dominant→0.9) adds false cardinal claims — the defensible content is order only (already conceded in `algorithm-audit.md` for ValueScore). | "dominant > present" claims exactly what we know; 0.9 vs 0.6 silently claims a 1.5× ratio nobody can defend. |
| M3 | **Numbers live only in the decision layer.** Product ranking (§14.2) keeps its weighted formula, but its inputs/weights are **utilities, not measurements**: validated by behavioral outcomes (recommendation acceptance) and sensitivity analysis, never cited as evidence about the user. | Ranking needs a total order; measurement doesn't. Splitting the layers quarantines the arbitrariness where it can be tested. |
| M4 | **Aggregation by count/diversity rules, ties reported as ties.** Replace noisy-OR with explicit categorical rules, e.g. session anchor level = max evidence level; promotion "≥2 independent *present* evidences from different channels → *dominant*". Session-level dominant-anchor ties break by (1) evidence count, (2) channel diversity, (3) declared tie (research views show the tie; action-required consumers pick arbitrarily and log it). | Count rules are human-readable, contestable, and FS1-calibratable. Per-topic multi-anchor mapping is NOT a tie problem — one intention legitimately serving several values is by design; ties only exist at session/participant aggregation. |
| M5 | **Judge layer.** A separate LLM role audits the builder's graph claims. Judge (a) speaks only rubric categories — verdicts, never scalars (a judge emitting 0.82 reinherits the M1 problem); (b) writes **only verification fields**, never content; (c) runs **asynchronously post-turn** (chips are hedged hypotheses anyway — verification status updates later, user latency ≈ 0); (d) runs on a **different model** than the service-agent pipeline (`VC_JUDGE_PROVIDER`-style config) to avoid self-preference. | Verifying a claim against quoted evidence is an easier task than well-calibrated generation-time self-assessment (generation/verification asymmetry); independence catches builder biases the builder cannot see. |
| M6 | **Write-authority split & authority order.** Three write authorities on the graph: **generation** (service-agent pipeline — creates nodes/edges), **verification** (judge — verdict fields only), **correction** (user, or GT-driven user agent — confirm/reject/edit). Authority order: **user correction > judge verdict > builder output.** A user-confirmed chip survives a judge rejection. | Negotiated validity: the human stays the final validator (DG3, §36); the judge is QA below the user, never above. |
| M7 | **Agent inventory: service / user / judge — no persona generator.** Service and user agents are *dialogue participants*; the judge is a *verification layer above the dialogue* (it never takes turns). CHI/FS1: service + human participant + judge. Synthesis: service + user agent + judge. **Personas come from the pre-sampled Nemotron-Personas-Korea pool (`seed/personas_nemotron.json`)** — no generation agent. Model separation: service ≠ user (recovery honesty), judge ≠ service (verification independence). | Decided 2026-06-11. GT value vectors for synthesis evaluation are *specified onto* existing Nemotron personas, not generated (open item OQ4). |
| M8 | **Motivation tier moves from keyword matching to a survey-item LLM task.** The Arnold & Reynolds / Babin survey items (already in `MOTIVATION_SPEC`) become the rubric: per dimension, the LLM judges whether the utterance is evidence the person would endorse the item. Dedicated task (accuracy over cost — decided), NOT folded into topic extraction. | Fixes valence blindness ("저렴해 보이면 *싫어요*" falsely matching the BargainValue cue), catches paraphrases, and inherits content validity from validated scales — "the survey operationalized as dialogue". |
| M9 | **Citation integrity is guaranteed by code before judging; everything semantic is LLM.** Code checks only referential integrity — quoted span exists verbatim in the cited turn/feedback, evidence id exists in the input. No keyword/heuristic *semantic* checks. | A judge given a fabricated quote will validate fabricated evidence; span-existence is the one check LLMs are structurally bad at (probabilistic matching) and code is perfect at. This is input sanitation (like the existing anchor-name whitelist), not judging. |

### 2.1 Score semantics (critical for M8 and all per-evidence judgments)

A per-utterance judgment is the **evidential strength of this utterance
alone**, never a cumulative person-level estimate. The accumulator (count
rules, M4) owns person/session-level synthesis. Prompts must say: *"judge only
this utterance; do not produce an overall assessment of the person"* —
otherwise later turns double-count earlier evidence.

---

## 3. Score inventory → categorical replacement

| Current scalar | Where | Replacement levels (observable criterion) |
|---|---|---|
| `IntentionTopic.confidence` (0–1) | topic node | `directly_stated` (criterion appears verbatim in user words) / `strong_inference` (clear from span in context) / `weak_inference` (hint only). Channel caps apply: feedback-only evidence can never yield `directly_stated`. |
| `AnchorMapping.score` (0–1) | intention→theory edge | **Preferred: drop the LLM-emitted scalar entirely** and derive the level from the categorical triple already collected (confidence × evidenceStrength × decisionImpact). Alternative: single level `dominant` (value named in the span AND drove an accept/reject) / `present` (clearly inferable from span) / `trace` (weak hint). Pick one at implementation (OQ2). |
| `IntentionRelation.plausibility` (0–1, added for D4) | causal edge | `stated_cause` (user verbalized the causation — "선물*이라서*…") / `strong_inference` / `weak`. D4 threshold rule becomes interpretable: **only `stated_cause` passes as causal**; others report `effectiveNature=co_occurrence`. Self-assessment replaced by judge verdict (M5) plus a direction test: *"would B still matter if A were absent? If yes, not causal."* |
| motivation score (0.4+0.2×hits keyword) | session→theory(motivation) | Per dimension: `asserts` (utterance states endorsement of the survey item) / `suggests` (item endorsement plausible from span) / `hints` (weak) / *no judgment* (no quotable span). Quote mandatory (M1). |
| relation `strength` | relation edge | fold into the relation rubric or drop; decide at implementation (OQ3). |

Existing categorical fields (`evidenceStrength`, `decisionImpact`,
`confidence=confirmed/inferred/weak`, `temporalStatus`) already follow M1 and
stay; the free scalar `score` was the lone anomaly.

---

## 4. Prompt strengthening plan (priority order)

### P1 — `topic_extraction` (highest leverage; outputs are now graph structure)

1. **`kind` definitions block** — currently `kind` exists only as a schema
   enum. Add one self-contained block (swappable — see flag below):
   - `constraint`: hard numeric/feature bound stated by the user
     ("20만원 이하", "GPS 필수"). Tie-break: a numeric bound wins over
     avoidance ("20만원 넘으면 부담돼요" → constraint).
   - `context`: situation/recipient description that conditions criteria
     ("선물이라", "운동 좋아하는 친구").
   - `avoidance`: a direction the user rejects ("흔한 건 싫어요",
     "저렴해 보이면 안 돼요").
   - `preference`: remaining directional likes.
   - Add worked examples for `avoidance` and `constraint` (the two kinds the
     current examples never show).
   - **Flag (→ algorithm-audit):** the 4-kind taxonomy is an engineering
     classification, not theory-derived; FS1 may revise it. Keeping
     definitions in one block makes the taxonomy swappable, and consistent
     application now yields consistent data for any later revision.
2. **Evidence discipline** — cite **all** supporting evidence ids (each
   becomes an edge; omissions distort hidden-ness); no evidence → do not emit
   the topic; `quoteOrSummary` = the **minimal** supporting span (human coders
   judge spans).
3. **Korean pragmatics table** — hedged-rejection markers small models miss:
   "좀 그래요" / "굳이…" / "나쁘진 않은데" / trailing "음…" → avoidance
   candidates. Raises feedback-channel recall, the main hidden-intention source.

### P2 — `anchor_mapping`

1. **Discrimination battery** (the identifiability problem, in prompt form):
   - Social vs Emotional: how others *see* it (image/체면) vs how the user
     *feels* (불안·후회 회피).
   - Conditional vs `context` kind: Conditional only when the situation
     *changes a criterion* ("선물이라서 가격 하한이 생김"); mere situation
     mention is not an anchor.
   - Epistemic vs Social: novelty/discovery vs looking distinctive to others.
   - Anti-dumping rule for Functional: requires positive utility evidence,
     not "none of the others fit".
2. **Rationale = laddering** — must answer "왜 이 기준이 이 사용자에게
   중요한가" in one sentence referencing the span; restating the topic label
   is invalid. (This is the MEC middle rung, mirroring FS1's laddering
   interviews.)
3. **Channel caps** — sourceEvidence containing only feedback ⇒
   `evidenceStrength ≤ medium`, `confidence ≠ confirmed` (same philosophy as
   structural explicitness: the channel bounds the claim).

### P3 — `relation_classification`

Builder proposes relations only (keeps the type taxonomy + "don't invent
unclear relations"); plausibility self-assessment is **removed** in favor of
the judge verdict (M5, §5). Add the direction test to the builder prompt as
self-check.

### P4 — new `motivation_detection` task (M8)

System prompt embeds all 7 survey items verbatim as the rubric; output =
per-dimension level + mandatory quote; explicit instruction per §2.1 (this
utterance only). Replaces `detect_motivation` keyword scoring;
`merge_motivation` accumulation is replaced by M4 count rules. Implementation
obligations: `mock_rules.TASK_HANDLERS` + `prompts.SYSTEM_BY_TASK`/
`FORMAT_BY_TASK` in the same commit (CLAUDE.md rule).

Lower stakes, unchanged for now: `conceptualization`, `sme_translation`,
`feature_*`, `pair_hidden_reason` (later: add "cite only differences present
in productDiff").

---

## 5. Judge design

- **Scope (priority order):** (1) causal relations — replaces the weakest
  link, generation-time self-assessed plausibility; (2) anchor mappings —
  "does the span support this anchor at this level?" (catches Functional
  dumping); (3) `kind` re-adjudication (cheap 4-way, high structural load).
- **I/O:** input = claim + its quoted spans + the full source turn/feedback
  text; output = verdict `supported` / `downgrade` (+ the level the evidence
  *does* support) / `rejected`, plus a one-sentence reason. Never emits
  content, labels, or scalars.
- **Persistence:** generalize the existing `intention_relations.verification`
  pattern (`unverified | llm_thresholded→judge_supported | llm_downgraded→judge_downgraded |
  human_verified | human_rejected`) to anchor mappings and topics (additive
  columns; naming finalized at implementation).
- **Async execution:** post-turn background job; the turn never waits. Chips
  may display a subtle "검토중 → 확인됨" state in research views only
  (participant UI unchanged — §36).
- **Trust path for the judge itself:** (1) synthesis GT comparison — judge
  verdicts checked against injected persona ground truth (free benchmark);
  (2) human κ on a rubric sample. Deploy on human-study (FS1) data only after
  both look acceptable.

---

## 6. Validation framework

How we know any of this works — measurement theory, two axes:

**Reliability (automated, gates every prompt change):**
- k-run agreement on identical input (test-retest) — defined only because
  outputs are categorical.
- Paraphrase invariance — same meaning, different wording → same levels.
- Both run on the **prompt regression set**: the golden gift-smartwatch
  session, 10–20 hand-labeled PSCon dialogues (expected topics/kinds), and
  negatives mined from the 632 backfilled production topics. No prompt change
  merges without these numbers ("feels better" editing is banned).

**Validity (uses instruments the study design already has):**
- Human criterion: coder κ on rubric samples (rubrics are what make human
  coding possible at all).
- Behavioral: anchor levels must predict accept/reject of `PROBE_RULES`
  diagnostic trade-off products.
- External: motivation levels ↔ FS1 pre-survey (Hedonic/Utilitarian scale)
  correlation; synthesis branch — recovery of injected persona GT.

---

## 7. Implementation notes (for the next round — not done)

1. **Migration pattern (third use of the same trick):** categories become the
   source of truth; existing numeric columns (`confidence`, `score`,
   `motivation_scores`…) become **derived caches** via a fixed level→number
   table so state_builder/frontend/tests keep working during transition.
   The cache numbers are decision-layer utilities (M3) — documented as such
   in `algorithm-audit.md`, sensitivity analysis listed as the honest caveat.
2. Biggest refactor: `state_builder` noisy-OR → M4 count rules. Phase it
   behind the cache so snapshots stay shape-compatible.
3. Judge infra: provider config, background task runner, verification columns.
4. `algorithm-audit.md` entries to add: kind-taxonomy flag, tie-break rules,
   M4 promotion counts ("≥2", channel-diversity), level→utility cache table.

## 8. Open items

- **OQ1** Final rubric level names/criteria per score (§3) — fix with examples
  at implementation.
- **OQ2** Anchor level: derive-from-triple vs separately judged level — pick one.
- **OQ3** Keep or drop relation `strength`.
- **OQ4** GT specification onto Nemotron personas (no generator agent — M7):
  how trait-5/motivation-7 vectors get attached to the 50 sampled personas
  (hand-authored mapping from demographics/facets vs stratified assignment
  design). Prerequisite for synthesis recovery metrics; cross-ref
  `ontology-graph-design.md` §8-1.
- **OQ5** Judge prompt drafts + verdict JSON schema + mock handlers.
