# Alignment checklist: toposort

Completed 2026-09-21 by the task author (also acting as spec-literal
reviewer; the automated gate covers items 1-5, this file records item 6).

1. [x] `reference.py` passes ALL hidden tests and ALL public tests.
2. [x] Every hidden test has a `PINS` entry; every pin names a real
   constraint id.
3. [x] Every constraint id C01-C07 has >= 1 pinning hidden test.
4. [x] `trap.py` (Kahn's with a LIFO stack worklist) PASSES all public tests
   and FAILS hidden tests (`test_c04_tie_break_sorted`,
   `test_c04_tie_break_with_deps`, `test_c06_disconnected`).
5. [x] spec.md parses under the strict constraint format; task.yaml ids match.
6. [x] Human spec-literal review:
   - Every hidden test follows from the written spec with no extra
     inference. `test_c04_tie_break_with_deps` pins the "several nodes
     simultaneously available -> smallest first" rule with a non-trivial
     graph.
   - Public tests do not exercise subtle constraints C04/C06 or the
     negative constraint C05 (no tie-breaking probe, no disconnected
     components, no mutation check). The trap's LIFO order happens to agree
     with sorted order on chains/diamonds, so it passes public tests.
   - C04 (deterministic smallest-first tie-breaking) and C06 (disconnected
     components all included, interleaved by tie-break) are the stated-once
     subtle constraints; their first detail sentences are the requirement
     statements.
   - No ambiguity is named for plan.md to resolve. One judgment call is
     recorded: duplicate edges (`{"a": ["b", "b"]}`) count once toward
     indegree; the spec does not pin this and no hidden test depends on it
     (the reference dedups defensively).

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
