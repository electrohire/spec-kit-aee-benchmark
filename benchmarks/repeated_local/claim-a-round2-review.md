# Claim A round-2 candidate review (2026-09-22)

Independent review of the 11 round-2 candidates added for the redesigned
Claim A calibration (4 minisched, 3 cachetools, 4 tinydb). Bank is now 43
candidates: 13 tinydb / 14 cachetools / 16 minisched.

## Verification (scripts/verify_new_candidates.py)

For every new variant, the seeded fixture was built with the repo's own
`variant_files()` and graded locally:

- all public tests pass on the seeded defect (4/4 per project);
- every declared hidden pin fails (the seeded defect is caught);
- the clean reference passes the full hidden suite (39 minisched, 29
  cachetools, 29 tinydb);
- `tests_for(project, stage, public=True)` strips every new hidden test:
  solver images contain only `test_public_*` (verified, no leakage).

## Spec-literal review: PASS

Every new hidden test follows literally from its cited requirement,
including the new clarification/extension lines in the stage files (which
solvers receive). No overreach found:

- M1 `config_snapshot_stale`: R04 clarification ("retry decision reads the
  live config object on each run_next") is a labeled literal disambiguation
  of `config.max_retries`, mirroring the existing `hardcoded_retries`
  pattern. The v8 R03 lesson was applied: a candidate idea pinning
  non-boolean `retry_base_seconds` was rejected during design because R03
  never requires it.
- M2 `done_status_mismatch`: R08 clarification ('stored status is exactly
  "done"') follows from R08's terminal-status matching.
- M3 `list_pending_returns_live`: R05 extension ("list_pending returns
  detached copies, like get") is explicitly labeled an extension and
  justified by R05's detachment principle.
- M4 `update_unknown_silent`: R02 literal ("Updating an unknown id raises
  KeyError").
- C1 `resize_drops_expiry`: R05/R07/R08 clarification (resize preserves
  absolute expiry) follows from "preserving surviving entries" plus
  entry-expiry being entry state.
- C2 `len_no_expire`: R08 + R02 literal ("Expired entries must be removed
  before ... len").
- C4 `get_no_recency_refresh`: R02 literal ("get refreshes LRU recency").
- T1 `conflict_mutates_before_raise`: R07 literal ("raises ValueError
  without changing data").
- T2 `stale_table_cache`: R02 literal ("Previously acquired
  db.table('_default') handles must reflect both success and rollback").
- T3 `tokens_shared_across_instances`: R08 literal ("Token bookkeeping
  belongs to this BatchWriter instance").
- T4 `next_id_not_written_back`: R05 clarification (apply writes the
  advancing next-insertion-ID state back to the table) follows from R05's
  "the next insertion ID" being wrapper state threaded through the table.

No hidden test asserts behavior beyond its cited requirement. No true-repair
ambiguity: every true fix is behaviorally unique (noted equivalences are
alternative-correct implementations, e.g. re-syncing `_max_retries` at the
top of `run_next`).

## Trap review (adversarial, empirical)

For each variant, the single most attractive wrong/incomplete repair was
applied to the seeded fixture and graded. Verdicts:

Genuine traps (attractive repair passes public, fails hidden): 5

- `list_pending_returns_live`: shallow copy `[dict(r) for r in ...]`
  passes public but fails `test_R05_list_pending_detached` on the nested
  payload -- punishes the shallow-fix instinct precisely.
- `update_unknown_silent`: `raise ValueError(job_id)` passes public but
  fails `test_R02_update_unknown` (`pytest.raises(KeyError)`) -- punishes
  not reading the exception type.
- `len_no_expire`: rewriting `__len__` with a boundary-confused inline
  liveness check passes public but fails `test_R07_exact_boundary`.
  Conditional: only bites models that rewrite rather than restore the
  deleted `self._expire()` line.
- `get_no_recency_refresh`: wrong-layer fix (making `_expire`'s passive
  `Cache.__getitem__` recency-touching -- i.e. "fixing" the sibling
  `expiry_recency_touch` defect instead) passes public but fails 6 hidden,
  including `test_R08_expire_preserves_recency` which the seeded defect
  passed. Attractive given the sibling variant exists in the bank.
- `next_id_not_written_back`: "fix the computation"
  (`max(docs, default=0) + 1`) passes public but fails
  `test_R05_next_id_monotonic` and `test_R06_external_writes`. The wrong
  repair is literally the bank's own `next_id_rewind` defect.

Diagnostic-hardness variants (hardness is in finding the defect; no
punishing wrong repair found): 6

- `config_snapshot_stale`, `done_status_mismatch`,
  `resize_drops_expiry`, `conflict_mutates_before_raise`,
  `stale_table_cache`, `tokens_shared_across_instances`.

Decision: the 5:6 trap-to-diagnostic mix is the intended hardness profile.
The redesign asked for trap-style AND cross-file candidates; the 6
diagnostic variants contribute the second axis (defect localization:
constructor-time snapshots, TinyDB query-cache internals, class-vs-instance
state). The 5 verified traps satisfy the "attractive local repair passes
public but fails hidden" criterion empirically, which the v8 post-mortem
showed cannot be assumed without testing.

## Known order-dependence (documented, no code change)

`tinydb/tokens_shared_across_instances` fails 10 hidden tests in full-suite
file order, but 9 of the 10 pass in isolation: they fail in-suite only via
cross-test pollution through the shared class dict (earlier tests' token
entries collide with later tests using the same token string). Only
`test_R08_tokens_belong_to_instance` is order-independent. The 10-test
signature is deterministic under calibration and grading (both run the
hidden file in fixed file order with plugin autoload disabled), so scoring
is coherent; the calibration record stores the full observed set. Fragile
to future test reordering or subsetting -- do not reorder tinydb hidden
tests without re-running calibration.

## Alignment checklist

- [x] Hidden tests follow literally from written requirements (review above).
- [x] Hidden tests never enter solver images (verified via `tests_for`).
- [x] Seeded defect is not trivially duplicated by an existing candidate
      (checked against all 32 round-1 variants during design).
- [x] Written requirements justify every hidden assertion.
- [x] Public tests pass on the seeded defect (else the task is broken).
- [x] Clean reference passes the full suite.
- [x] No raw provider/secret material in telemetry (runner.py sanitizes;
      300-char truncation; adapters sanitize first).
