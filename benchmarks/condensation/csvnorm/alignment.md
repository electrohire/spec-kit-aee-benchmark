# Alignment checklist: csvnorm

Completed 2026-09-21 by the task author (also acting as spec-literal
reviewer; the automated gate covers items 1-5, this file records item 6).

1. [x] `reference.py` passes ALL hidden tests and ALL public tests.
2. [x] Every hidden test has a `PINS` entry; every pin names a real
   constraint id.
3. [x] Every constraint id C01-C07 has >= 1 pinning hidden test.
4. [x] `trap.py` (naive `line.split(",")`) PASSES all public tests and FAILS
   hidden tests (`test_c06_quoted_comma`, `test_c06_escaped_quotes`,
   `test_c06_embedded_newline`).
5. [x] spec.md parses under the strict constraint format; task.yaml ids match.
6. [x] Human spec-literal review:
   - Every hidden test follows from the written spec with no extra inference.
     `test_c04_quote_not_first_char` exercises the exact example given in C04
     (`  "x"` strips to `"x"`); the expected output `"""z"""` follows from
     C07's minimal-quoting rule applied to the stripped value, which contains
     literal quotes.
   - Public tests do not exercise subtle constraints C03/C04, the negative
     constraint C05 (order is trivially preserved in 2-row outputs, but no
     test probes reordering), or C06 detail.
   - C03 (BOM stripping) and C04 (quoted-verbatim vs unquoted-strip
     distinction, quote-must-be-first) are the stated-once subtle
     constraints; their first detail sentences are the requirement
     statements.
   - No ambiguity is named for plan.md to resolve. One judgment call is
     recorded: rows with ragged field counts are kept as parsed (no padding
     or truncation); the spec does not promise rectangular output and no
     hidden test depends on ragged-row handling.

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
