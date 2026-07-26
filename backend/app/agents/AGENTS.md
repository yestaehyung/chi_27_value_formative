# AGENT PIPELINE GUIDE

## SCOPE

This directory owns conversational orchestration for live turns, product feedback,
planning, recommendation, response rendering, simulation users, and the optional
agentic-loop experiment. Keep HTTP parsing in `app/api/` and preference-state
construction in `app/preference_commit/`.

## TURN AND FEEDBACK FLOW

- `service_agent.handle_user_turn` is the canonical live-turn coordinator.
- Persist the incoming user turn, commit it, and release the SQLite write lock
  before awaiting dialogue classification or preference-commit LLM work.
- Dialogue-act classification and `run_preference_commit` may run concurrently
  because classification does not use the database session.
- Build planner context from recent raw turns, full user utterances, feedback,
  the last shown set, and the current snapshot; structured state is intentionally
  lossy and must not replace the source evidence.
- After action execution, persist the agent turn, impressions, and diagnostic
  `LLMCall` rows in a short transaction.
- `handle_feedback` must persist the `FeedbackEvent` before awaiting downstream
  work. `view_detail` and `click` are exploration, not preference evidence: route
  them to the detail-answer flow without creating preference topics.
- Preference-bearing feedback builds same-impression-set pairs, then runs the
  shared preference-commit path. Purchase additionally advances the stage.

## PLANNER CONTRACT

- The LLM action vocabulary is exactly `recommend`, `clarify`, `answer`, `close`.
- `show_conflict` is a separate DB-fact structural guard and takes precedence
  when a direct unresolved conflict exists.
- `recommend` provides a positive, standalone `searchText` plus a
  `constraintsNote` for budgets, requirements, and dislikes.
- The planner never selects or receives product IDs; product choice belongs to
  `recommender`.
- `answer` and `close` require prior recommendations. Do not allow consecutive
  `clarify` actions. Preserve the existing normalization and fallback behavior.

## RECOMMENDER EVIDENCE PURITY

- Ranking may use raw user utterances, explicit topics, and topics whose status
  is `confirmed` or `corrected_by_user`.
- Never rank directly from unconfirmed anchor scores, motivation scores, latent
  hypotheses, rejected topics, or inactive topics.
- Apply hard constraints during retrieval, then semantic constraints during
  reranking. Keep the retrieval pool and rerank diagnostics auditable.
- Do not fill a short compliant result set with excluded products. If no product
  complies, expose only capped near misses and carry each mismatch reason into
  both the reply context and its product card.

## PIPELINE VS AGENTIC

- The default path remains planner -> recommender -> response generator.
- The `VC_TURN_LOOP=agentic` path is an experimental comparison, not a second
  source of product-search or preference semantics.
- Both paths receive the same planner context and share `run_recommendation`.
- Run the direct-conflict guard before either path. Agentic failures must fall
  back to the pipeline without losing the already-persisted user turn.
- Do not pass an agentic response through the pipeline renderer again; the same
  context that called the tool owns its final text.

## ASYNC, PERSISTENCE, AND REPLY GROUNDING

- Never hold an open SQLite write transaction across an LLM or network await.
- Do not use one SQLAlchemy session concurrently from multiple async branches.
- Write source evidence before derived state; write rendered turns and
  impressions only after their content and shown set are final.
- Replies must be grounded in the actual shown products, recent turns, current
  user-visible summary, and explicit conflict or near-miss facts.
- `answer` explains the last shown set without silently starting a new search.
- Keep `related_product_ids`, impression rows, cards, and rendered product claims
  aligned to the same finalized product set.

## FOCUSED VERIFICATION

- Run `VC_LLM_PROVIDER=mock .venv/bin/python -m pytest tests/test_action_decision.py tests/test_agentic_loop.py -q` for planner or loop changes.
- Run `VC_LLM_PROVIDER=mock .venv/bin/python -m pytest tests/test_category_hard_filter.py tests/test_rerank_exclude.py tests/test_reply_grounding.py -q` for retrieval, rerank, cards, or renderer changes.
- Run `VC_LLM_PROVIDER=mock .venv/bin/python -m pytest tests/test_view_detail_interaction.py tests/test_motivation_evidence.py -q` for feedback or evidence-flow changes.
- Add a focused regression test beside the nearest existing behavior test; never use paid providers or simulation sweeps for routine verification.
