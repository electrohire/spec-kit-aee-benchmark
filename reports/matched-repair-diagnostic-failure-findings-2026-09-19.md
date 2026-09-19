# Matched-repair diagnostic failure mode — findings (2026-09-19)

Investigation only. No protocol changes, no evidence rewritten, no runs launched.
Constitution (`.specify/memory/constitution.md` v1.3.0) and repo AGENTS.md read first.

## Mechanism (the gate)

`scripts/matched_repair.py:84` runs the diagnose phase with `limit=8` calls and a
1,200s deadline; line 87 gates assessment production on
`summary['done'] and not diagnostic_changed`.

## Empirical outcome

16 `pair.json` files in `reports/local/matched-repair-01/`:

- **15/16**: `done=False`, `completed=False`, `calls=8/8`, `errors=[]`,
  `diagnostic_changed_source=False` → no claims, no evaluation.
- **1/16** (`tinydb-partial_commit-20260918`): `done=True` on call 8 → 8 claims +
  evaluation produced.
- Per-call audit of all 128 `diagnostic/call-*.json` responses: all 15 failures
  issued 8/8 `shell` actions and zero `done` attempts; the success issued 7× shell
  + `done` on the final call.

## Eliminated causes (quantified)

1. **Phase deadline (1200s)** — total diagnostic wall time 9.2–73.9s per pair
   (6–130× under budget). Not a factor.
2. **Provider timeouts / request failures** — `errors` empty in all 16 summaries;
   no timeout or request-error records in any call file. Not a factor.
3. **Token cap** — no `token_cap`/`reserved_token_cap` errors anywhere. Not a factor.
4. **Context selection/truncation** — max preflight input 5,154–11,241 tokens vs
   32,768 budget; `removed_history_messages=0` on all 128 calls. Not a factor.
5. **Source-change gate** — `diagnostic_changed_source=False` in all 16 (the
   "do not edit source" instruction was obeyed). Not a factor.
6. **Claims-schema rejection** — no `ValueError` from `Claim.from_dict` in any
   error list; models never attempted `done` (the one attempt passed). Not a
   factor. Matches `adjudication.md`'s existing characterization
   ("quota/completion failure, not observed claim-parser rejection").

## Confirmed failure mode: non-termination within the 8-action budget

The model exhausts all 8 calls on shell exploration and never emits `done`.
Decisively: the explicit final-call nudge (`scripts/repeated_local.py:179` —
*"Return done now… Do not perform another shell action"*) was **ignored in all
15 failures**; each spent call #8 on another shell command (e.g.
`cachetools-boolean_ttl-20260918/diagnostic/call-0007.json` is a `find` command).

Two sub-patterns among the 15:

- **8/15 pure passive reading loops** (0 code executions) — e.g. cachetools
  trajectories `cat`-ing the same 3–5 files repeatedly.
- **7/15 active experimenters that still didn't terminate** — e.g.
  `tinydb-token_alias-20260918` ran pytest 3× and a `python -c` reproduction
  **on the final call** instead of writing the claims deliverable.

The success case proves the budget is sufficient in principle: behavioral repro
on call 6 → `done` with 8 claims on call 7. The binding constraint is
termination behavior, not budget.

## Likely contributors (interpretive)

- The `done` deliverable is heavy: per-claim
  id/text/kind/status/boundary/depends_on/conflicts_with/falsification_tests/
  source_ref/uncertainty/evidence[] with hash refs, validated by
  `Claim.from_dict` (`scripts/long_horizon.py:34`,
  `scripts/repeated_local.py:185-188`). The model appears to defer this
  expensive step ("one more check") until the budget is gone.
- Termination relies solely on model compliance with two warning messages
  (`repeated_local.py:179,181`) — empirically ineffective (15/16 ignored the
  final one). The harness cannot distinguish "still investigating" from "stuck."

## Recommendations (not implemented)

1. **Structural termination over nudges**: at the final step, constrain the
   action space to `done`-only (or auto-synthesize `done` from the trajectory)
   instead of a request the model demonstrably ignores.
2. **Don't just raise the call budget**: evidence shows non-convergence, not
   budget exhaustion — the success also used all 8 calls. More budget likely
   buys more exploration, not more dones.
3. **Stage the deliverable**: require a draft hypothesis/claims object mid-phase
   (e.g. step 5–6) so the final call isn't a cold start on a heavy schema.
4. **Constitution compliance**: any protocol change needs a new freeze and new
   run IDs (constitution IV); the 15 failures stay in denominators — history
   must not be rewritten.
5. **Model-dependence is untested**: all runs used one model config
   (constitution II); non-termination may be model-specific. Testing another
   model is a new experiment, not a fix.
