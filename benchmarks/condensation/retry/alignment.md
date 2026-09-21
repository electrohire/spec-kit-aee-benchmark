# Alignment checklist: retry

Completed 2026-09-21 by the task author (also acting as spec-literal
reviewer; the automated gate covers items 1-5, this file records item 6).

1. [x] `reference.py` passes ALL hidden tests and ALL public tests.
2. [x] Every hidden test has a `PINS` entry; every pin names a real
   constraint id.
3. [x] Every constraint id C01-C08 has >= 1 pinning hidden test.
4. [x] `trap.py` (sleep-before-every-attempt loop) PASSES all public tests
   and FAILS hidden tests (`test_c01_success_no_sleep`,
   `test_c02_max_attempts_one`, `test_c03_backoff_schedule`,
   `test_c04_non_retryable_propagates`, `test_c05_no_sleep_before_first`,
   `test_c06_exact_sleep_values`). It PASSES `test_c08_no_wrapper_phantom`:
   the phantom constraint is a negative control for this trap (a
   phantom-fixing solver, not the sleep-first trap, is what C08 exists to
   catch).
5. [x] spec.md parses under the strict constraint format; task.yaml ids match.
6. [x] Human spec-literal review:
   - Every hidden test follows from the written spec with no extra
     inference. `test_c06_exact_sleep_values` pins the exact C03 schedule
     values `[0.25, 0.5, 1.0]` for three retries; `test_c02_max_attempts_one`
     pins "1 initial attempt plus up to max_attempts - 1 retries" at the
     boundary.
   - Public tests do not exercise subtle constraints C04/C06 or the
     negative constraint C05: sleeps are discarded (`sleep=lambda s: None`),
     so the sleep-first trap is invisible to them.
   - C04 (selective retry; last exception re-raised unwrapped) and C06
     (exact sleep values in order) are the stated-once subtle constraints;
     their first detail sentences are the requirement statements.
   - No ambiguity is named for plan.md to resolve. One judgment call is
     recorded: `retry_on` given as a non-class, non-tuple (e.g. a list) is
     unspecified; the reference only normalizes a single class, and no
     hidden test depends on other forms.

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
