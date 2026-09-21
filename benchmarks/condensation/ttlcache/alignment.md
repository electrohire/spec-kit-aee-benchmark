# Alignment checklist: ttlcache

Completed 2026-09-21 by the task author (also acting as spec-literal
reviewer; the automated gate covers items 1-5, this file records item 6).

1. [x] `reference.py` passes ALL hidden tests and ALL public tests.
2. [x] Every hidden test has a `PINS` entry; every pin names a real
   constraint id.
3. [x] Every constraint id C01-C07 has >= 1 pinning hidden test.
4. [x] `trap.py` (`ttl or default_ttl`; `now >= expiry`) PASSES all public
   tests and FAILS hidden tests (`test_c02_valid_at_exact_instant`,
   `test_c06_ttl_zero_expires_immediately`, `test_c06_ttl_zero_not_default`).
5. [x] spec.md parses under the strict constraint format; task.yaml ids match.
6. [x] Human spec-literal review:
   - Every hidden test follows from the written spec with no extra inference.
     `test_c04_get_refreshes_recency_not_expiry` combines two pinned
     behaviors (recency refresh on get; get never extends expiry) — both are
     stated in C04 ("a successful get refreshes recency but never extends the
     expiry").
   - Public tests do not exercise subtle constraints C02/C06, the negative
     constraint C05, or boundary detail (generous 30s margins; no ttl=0).
   - C02 ("valid AT the exact expiry instant") and C06 ("ttl=0 is an
     immediate expiry, not a missing TTL") are the stated-once subtle
     constraints; their first detail sentences are the requirement
     statements. Note the deliberate interplay: ttl=0 sets expiry = set
     instant, so the entry is valid only at that instant (C02) and expired as
     soon as the clock advances (C06); the hidden tests advance the clock
     before asserting, so both constraints are jointly satisfiable and the
     reference satisfies both.
   - No ambiguity is named for plan.md to resolve; plan.md restates the
     per-constraint implementation, including the explicit warning against
     the `ttl or default_ttl` idiom.

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
