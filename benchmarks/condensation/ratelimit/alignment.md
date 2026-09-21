# Alignment checklist: ratelimit

Completed 2026-09-21 by the task author (also acting as spec-literal
reviewer; the automated gate in `scripts/check_condensation_alignment.py`
covers items 1-5, this file records item 6).

1. [x] `reference.py` passes ALL hidden tests and ALL public tests
   (verified by the automated gate).
2. [x] Every hidden test has a `PINS` entry; every pin names a real
   constraint id from spec.md (verified by the automated gate).
3. [x] Every constraint id C01-C07 has >= 1 pinning hidden test (verified by
   the automated gate).
4. [x] `trap.py` (integer-truncated refill) PASSES all public tests and FAILS
   at least one hidden test (`test_c06_no_truncation`; verified by the
   automated gate).
5. [x] spec.md parses under the strict constraint format; task.yaml ids match
   spec.md ids exactly (verified by the automated gate).
6. [x] Human spec-literal review:
   - Every hidden test follows from the written spec with no extra
     inference. `test_c04_allow_does_not_sleep` uses the injected fake clock
     and asserts the clock value is unchanged, which follows directly from
     "It must not sleep, wait, retry, or perform any I/O" (an implementation
     that slept would advance a real clock; with the fake clock the only
     observable is that allow returns without the test's own clock moving —
     this is the standard observable for "returns immediately").
   - Public tests do not exercise subtle constraints C02/C06, the negative
     constraint C05, or boundary detail: they use generous refill margins
     and a single key.
   - The spec names no ambiguity for plan.md to resolve; plan.md restates the
     per-constraint implementation approach. No hidden test depends on an
     unresolved ambiguity.
   - C02 and C06 are the stated-once subtle constraints; their first detail
     sentences are the requirement statements, so the light summary preserves
     them while dropping rationale.

## Addendum 2026-09-21: spec rewrite for summarizer budgets

spec.md was rewritten so every constraint's first detail sentence is a terse,
complete requirement statement (rationale, examples, and edge cases moved to
following sentences) and constraint titles were shortened to 2-4 words; this
was required for the light/aggressive summaries to fit their 50%/20% word
budgets. No constraint changed in meaning, no behavior pinned by hidden tests
changed, and no hidden or public test was modified in this rewrite (one
already-pinned example was copied verbatim into the spec detail where noted
in the design negative record). The task author re-confirmed items 1-6
against the rewritten spec; the independent-reviewer requirement remains
open (see design doc).
