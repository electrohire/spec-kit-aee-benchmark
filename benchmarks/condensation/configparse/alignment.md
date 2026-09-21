# Alignment checklist: configparse

Completed 2026-09-21 by the task author (also acting as spec-literal
reviewer; the automated gate covers items 1-5, this file records item 6).

1. [x] `reference.py` passes ALL hidden tests and ALL public tests.
2. [x] Every hidden test has a `PINS` entry; every pin names a real
   constraint id.
3. [x] Every constraint id C01-C07 has >= 1 pinning hidden test.
4. [x] `trap.py` (recursive interpolation over the working table, 10-pass
   bound) PASSES all public tests and FAILS hidden tests
   (`test_c03_one_level_only`, `test_c03_self_reference_terminates`).
5. [x] spec.md parses under the strict constraint format; task.yaml ids match.
6. [x] Human spec-literal review:
   - Every hidden test follows from the written spec with no extra
     inference. `test_c03_one_level_only` uses the exact example shape from
     C03 (`start-${b.y}-end` with `b.y = ${c.z}`); `test_c03_self_reference_terminates`
     uses C03's self-reference example.
   - Public tests do not exercise subtle constraint C03 (only non-nested
     interpolation) or the negative constraint C04 (no eval-shaped value).
   - C03 (exactly-one-level interpolation) is the stated-once subtle
     constraint; its first detail sentence is the requirement statement.
   - No ambiguity is named for plan.md to resolve. One judgment call is
     recorded: `${ key }` with inner whitespace is tolerated (stripped in
     lookup); the spec does not pin this and no hidden test depends on it.

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
