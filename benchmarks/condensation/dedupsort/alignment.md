# Alignment checklist: dedupsort

Completed 2026-09-21 by the task author (also acting as spec-literal
reviewer; the automated gate covers items 1-5, this file records item 6).

1. [x] `reference.py` passes ALL hidden tests and ALL public tests.
2. [x] Every hidden test has a `PINS` entry; every pin names a real
   constraint id.
3. [x] Every constraint id C01-C07 has >= 1 pinning hidden test.
4. [x] `trap.py` (dedup by key instead of by element equality) PASSES all
   public tests and FAILS hidden tests (`test_c04_dedup_by_equality_not_key`,
   `test_c03_stable_for_equal_keys`, `test_c03_stable_with_reverse`).
5. [x] spec.md parses under the strict constraint format; task.yaml ids match.
6. [x] Human spec-literal review:
   - Every hidden test follows from the written spec with no extra
     inference. `test_c06_key_called_once_per_element` pins the "once per
     input element" reading of C06 (duplicates still get exactly one call);
     the reference implements that reading.
   - Public tests do not exercise subtle constraints C04/C06 or the
     negative constraint C05 (no mutation probe, no generator, no key
     counter). The public key (`len`) is injective, so the trap passes.
   - C04 (dedup by equality, never by key) and C06 (key called exactly once
     per element) are the stated-once subtle constraints; their first detail
     sentences are the requirement statements.
   - No ambiguity is named for plan.md to resolve. One judgment call is
     recorded: `reverse=True` keeps equal-key elements in original relative
     order (Python `sorted` stability under reverse); the spec's C03 makes
     no exception for reverse, and `test_c03_stable_with_reverse` pins this.

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
