# Claim B condensation experiment: offline build report

2026-09-21. Branch `feat/claim-b-condensation`. No paid model calls were
made; no RUN gate was invoked.

## 1. What was built

| Deliverable | Path |
|---|---|
| Experiment design | `docs/claim-b-condensation.md` |
| Deterministic summarizer | `scripts/condense.py` |
| Condensation runner (mock solvers) | `scripts/run_condensation.py` |
| Offline grader | `scripts/grade_condensation.py` |
| Alignment gate | `scripts/check_condensation_alignment.py` |
| 10-task bank (spec/plan/ref/trap/tests/phase2/alignment each) | `benchmarks/condensation/<task>/` |
| Offline test suite | `tests/test_condensation.py` |
| Freeze manifest (96 files, `budget_authorization: PENDING`) | `manifests/freeze-condensation-v1.json` |

Task bank: ratelimit, ttlcache, csvnorm, eventbus, configparse, dedupsort,
pathresolve, wordwrap, toposort, retry. Every task ships a phase-1 spec, a
phase-2 prompt, hidden tests pinning every constraint, a reference
implementation, a trap (or ambiguity) that passes public tests but fails
hidden tests, and a completed grader-spec alignment checklist.

## 2. Offline verification (all green)

- Full repo suite: **197 passed** (`tests/`, GPU tests excluded — they need
  hardware; nothing in this build touches them).
- Condensation suite: **84 passed** (`tests/test_condensation.py`),
  including summarizer determinism, budget compliance, ID coverage,
  treatment-isolation file lists, and end-to-end mock reference/trap
  campaigns with exact expected grades.
- Alignment gate: **10/10 PASS**. Every hidden test has a `PINS` entry
  naming a real constraint; every constraint has >= 1 pinning test;
  reference passes all public+hidden; trap passes public but fails hidden;
  every task has >= 2 subtle and >= 1 negative/phantom constraint.
- Summarizer budgets: all 10 light summaries <= 50% of spec words, all 10
  aggressive summaries <= 20% of spec words (fail-closed on overrun).

## 3. Cost estimate for the paid campaign (not authorized)

Campaign shape (from the design doc): per task, 1 shared phase-1 attempt
(<= 4 calls) + 6 phase-2 cells (<= 8 calls each) = <= 52 calls. 10 tasks:
**<= 520 calls, 70 attempts**.

Priced on gpt-6-astra ($10/$1/$50 per MTok input/cached/output):

- Expected (measured v8.1 rate ~$0.037/call): 520 x $0.037 = **~$19**.
  Padded planning range: **$19-25**.
- Token-model cross-check (~3000 input tokens at 60% cache hit, ~1500
  output): ~$0.09/call -> ~$46. This is conservative; the measured rate
  reflects real v8.1 contexts and is the primary anchor.
- Worst-case reservation bound ($0.9626/call at full 32768+4096 ceilings):
  ~$500. Not the expected spend.
- Per-attempt cap $25: not binding (a phase-2 attempt is <= 8 calls, under
  $1 at expected rates). Global $100 cap: not binding at expected spend.
- Remaining under the global cap: **$70.05** ($29.95 measured through v8.1).
  Expected campaign spend is ~27-36% of remaining budget.

Spend authorization is **PENDING**. The host RUN gate still requires
Tristen's typed RUN per phase before any paid call.

## 4. Preserved negatives (append-only, in the design doc)

- `ratelimit`: first fractional-token hidden test did not trigger the trap
  (no refill between clock advances); test corrected, gate re-run PASS.
- `wordwrap`: hidden expected chunks wrong for `cdefghij`; test fixed,
  gate re-run PASS.
- `csvnorm`: first gate run failed — `test_c04_quoted_verbatim` input had
  no comma, so quoted output was not required by C07; input fixed, gate
  re-run PASS.
- Summarizer budgets: first full run failed 30/84 (all light summaries over
  50%); all ten specs rewritten with terse first-sentence requirements and
  2-4-word titles; no pinned behavior changed; re-run all green.
- `retry` C08 phantom constraint added explicitly (no wrapper types), with
  plan.md naming the phantom "fix".

## 5. Open items before any spend

1. **Independent spec-literal review**: the alignment checklist's human
   item was completed by the task author. A separate reviewer must check
   all ten tasks before the paid campaign (v8 lesson). This is a pre-spend
   gate, not part of this build.
2. **Pilot with a real model**: confirm the traps actually trap a frontier
   model and the summary arm actually degrades. Also a pre-spend gate.
3. **Budget authorization**: `budget_authorization: PENDING` in the freeze
   manifest. Tristen's typed RUN per phase is the spend confirmation.
4. Local-model (Claim A) infra proceeds in parallel; this build does not
   block it.
