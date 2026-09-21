# Alignment checklist: pathresolve

Completed 2026-09-21 by the task author (also acting as spec-literal
reviewer; the automated gate covers items 1-5, this file records item 6).

1. [x] `reference.py` passes ALL hidden tests and ALL public tests.
2. [x] Every hidden test has a `PINS` entry; every pin names a real
   constraint id.
3. [x] Every constraint id C01-C07 has >= 1 pinning hidden test.
4. [x] `trap.py` (unconditional `..` pop, dropping leading relative `..`)
   PASSES all public tests and FAILS hidden tests
   (`test_c04_leading_dotdot_kept`, `test_c04_dotdot_beyond_root`,
   `test_c07_dotdot`).
5. [x] spec.md parses under the strict constraint format; task.yaml ids match.
6. [x] Human spec-literal review:
   - Every hidden test follows from the written spec with no extra
     inference. `test_c05_no_os_path` statically checks the staged module
     source for `os.path`/`pathlib` use, pinning the negative constraint in
     an automatable way.
   - Public tests do not exercise subtle constraints C04/C06 or the negative
     constraint C05 (no leading `..`, no doubled/edge slashes beyond one
     case, no source check).
   - C04 (leading `..` kept on relative paths, dropped on absolute) and C06
     (no empty segments from edge slashes) are the stated-once subtle
     constraints; their first detail sentences are the requirement
     statements.
   - No ambiguity is named for plan.md to resolve. One judgment call is
     recorded: `".."` alone resolves to `".."` (C07 defers to C04's rule);
     `a/../..` is `..` by the same rule, though no hidden test pins it.

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
