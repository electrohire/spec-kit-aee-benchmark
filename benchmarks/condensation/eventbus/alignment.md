# Alignment checklist: eventbus

Completed 2026-09-21 by the task author (also acting as spec-literal
reviewer; the automated gate covers items 1-5, this file records item 6).

1. [x] `reference.py` passes ALL hidden tests and ALL public tests.
2. [x] Every hidden test has a `PINS` entry; every pin names a real
   constraint id.
3. [x] Every constraint id C01-C07 has >= 1 pinning hidden test.
4. [x] `trap.py` (live-list iteration; immediate exception propagation)
   PASSES all public tests and FAILS hidden tests
   (`test_c04_emit_continues_after_raise`,
   `test_c04_emit_error_carries_errors_in_order`,
   `test_c06_register_during_emit_waits`,
   `test_c06_removed_during_emit_still_fires`).
5. [x] spec.md parses under the strict constraint format; task.yaml ids match.
6. [x] Human spec-literal review:
   - Every hidden test follows from the written spec with no extra
     inference. `test_c06_removed_during_emit_still_fires` exercises the
     second half of C06's snapshot rule ("a handler removed during an emit
     still fires in the current emit if its turn has not come yet"), which is
     stated explicitly in the spec.
   - Public tests do not exercise subtle constraints C04/C06 or the negative
     constraint C05 (no raising handlers anywhere in public tests).
   - C04 (error isolation: run all, then raise EmitError) and C06 (snapshot
     iteration) are the stated-once subtle constraints; their first detail
     sentences are the requirement statements.
   - No ambiguity is named for plan.md to resolve. One judgment call is
     recorded: `off` removes ALL registrations of the handler for the event
     (not just the first); the spec says "removes every registration", and
     the hidden tests register each handler once, so this is consistent.

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
