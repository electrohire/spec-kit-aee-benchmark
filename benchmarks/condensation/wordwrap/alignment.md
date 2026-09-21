# Alignment checklist: wordwrap

Completed 2026-09-21 by the task author (also acting as spec-literal
reviewer; the automated gate covers items 1-5, this file records item 6).

1. [x] `reference.py` passes ALL hidden tests and ALL public tests.
2. [x] Every hidden test has a `PINS` entry; every pin names a real
   constraint id.
3. [x] Every constraint id C01-C07 has >= 1 pinning hidden test.
4. [x] `trap.py` (greedy packing without long-word breaking) PASSES all
   public tests and FAILS hidden tests (`test_c03_long_word_broken`,
   `test_c03_long_word_after_partial_line`, `test_c03_pieces_within_width`).
5. [x] spec.md parses under the strict constraint format; task.yaml ids match.
6. [x] Human spec-literal review:
   - Every hidden test follows from the written spec with no extra
     inference. `test_c03_long_word_after_partial_line` pins the "partial
     line is flushed first" sentence of C03 exactly.
   - Public tests do not exercise subtle constraints C03/C06 or the
     negative constraint C05 (no overlong words, no indent-with-breaking,
     no trailing-space probe beyond exact-match).
   - C03 (long words broken, pieces within width, partial line flushed
     first) and C06 (indent prepended to every line, not counted toward
     width) are the stated-once subtle constraints; their first detail
     sentences are the requirement statements.
   - No ambiguity is named for plan.md to resolve. One judgment call is
     recorded: a long word is broken into full-width pieces from the front
     (`"abcdefghij"` at width 4 -> `"abcd","efgh","ij"`); the spec requires
     pieces within the width but does not pin the chopping direction, and
     no hidden test depends on an alternative.

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
