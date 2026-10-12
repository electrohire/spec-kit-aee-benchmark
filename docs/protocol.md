# Preregistered pilot protocol (execution settings pending)
Status: protocol and task selection prepared before any scored result.
20 Python SWE-bench Verified test tasks, three independent repeats, three arms:
180 attempts. Seed 20260917. Eligible tasks are the pinned task repository's
Verified/test membership; repository-stratified seeded round-robin selection.
Exclude sympy__sympy-20590 (gold grader smoke) and django__django-11099
(development adapter smoke). Save all excluded and unselected IDs before runs.

Baseline uses ordinary capable agent instructions. Spec Kit uses frozen core
skills; spec_kit_aee adds Evaluator composition and AEE assessments at specify,
plan, tasks and implement. All use mini-SWE-agent 2.4.6 DefaultAgent with the same
provider, settings, tools, hardware limits, issue, initial checkout and ceilings.
Host phase adapter retains one message history and budget. No tier switching.
At most two AEE recovery rounds per phase within the same total ceiling.

Fresh network-disabled Docker containers with no mounts or API keys expose only
the upstream image and treatment assets. Gold/test patches, task repository,
controller, prior sessions and sibling artifacts stay on host. Upstream images
must be inspected for held-out files and pinned by digest before any model calls.
Grade after completion using upstream SWE-bench only and explicit frozen IDs.

Randomly shuffle all task/repeat/arm triples. Repeats are independent sessions,
not claims of seeded provider determinism. No differential human help or prompt
tuning from scored results. Any intervention requires a recorded deviation.

Freeze protocol, source, tasks, dependencies, treatment assets, settings and dated
official prices. Every attempt carries freeze_id. Global and attempt dollar caps
are authorized explicitly. Reserve full model input ceiling plus maximum output
at uncached list price before each request; enforce token ceilings the same way.
This conservative rule may underuse caps. Verify the documented context bound
before setting reservation_bound_verified. No tool fees for plain chat requests.
Cache is a subset of input; reasoning is a subset of output.

Timeout: 1800 seconds per attempt, requests <=120 seconds, shell commands <=60.
Cancellation: Ctrl-C or an experiment CANCEL file; stop at the next safe boundary.
No implicit provider retries. Unknown charges retain full reservation. Malformed
model actions may be corrected within the budget. Errors stop the campaign;
interrupted attempts remain infrastructure failures and are not silently rerun.
Any authorized rerun uses a new campaign ID; report originals and reruns separately.
Retain every attempted task in the cost denominator, including failures/limits.

Report successes/attempts, missing grades, all token categories, all-attempt costs,
cost per attempted and resolved task, latency median/p95, repairs/tools and limit
rate. Undefined ratios are null. Pair task/repetition cells; bootstrap task clusters
with 2000 draws, seed 20260917. Publish excluded incomplete pairs. Unknown grades
are disclosed and never counted as passes. Report internal AEE false acceptance
and unnecessary blocking only when independent grading exists for that patch.

One-time setup and infrastructure/human time are separate. Cold-start total equals
measured setup plus execution; amortization requires a declared number of reuses.
Unknown setup cost means these totals remain unknown. No transcript-based billing.
Combined treatment cannot isolate AEE from Evaluator. Pilot and public benchmark
contamination limit generalization. No leaderboard or article publication.

## Integrity semantics (Spec 003 FR-7, 2026-10-12)

What the integrity mechanisms do and do not prove, stated plainly:

- Event streams (attempts/calls/grades/budget) are append-only hash
  chains: each record written by the runner carries prev_hash/chain_hash,
  and any read verifies the chain. Editing or deleting a chained record
  is detectable at read time. A chain proves internal consistency, not
  authorship: an actor who can rewrite an entire stream can recompute a
  self-consistent chain, so streams are tamper-evident against accidents
  and partial edits, not tamper-proof. Pre-chaining (legacy) records are
  reported as unverified, never silently upgraded.
- A grade counts toward resolved rates only when it is bound to grader
  artifacts: the grade record must reference content-addressed objects
  (the grader log and per-instance reports) that exist in the store and
  hash to their recorded digests, and the recorded grader exit code must
  be zero. Grades without that binding are excluded from the numerator
  and disclosed in the report's integrity section, not dropped silently.
- freeze_id is a self-consistent content hash over the manifest. It
  detects accidental modification of listed files and, since FR-7.5,
  additions under frozen paths. It is not a signature: anyone who can
  edit the manifest can recompute a valid freeze_id. Tamper-resistance
  would require anchoring freeze_id outside the repo (Spec 003 FR-4.1);
  this benchmark does not currently anchor, and no claim in any report
  should imply that it does.
- Archived prior runs (host-setup moves a stale run directory aside,
  timestamped, never deleted) are disclosed in aggregate reports with
  their scored-attempt counts. Headline denominators cover the reported
  run only; the archives are provenance, not hidden attempts.
- The spec_kit_aee arm's in-run AEE assessments are produced by the
  pinned AEE engine itself. They are workflow signals (they route
  recovery rounds) and are never grades: the only grades are the
  independent SWE-bench grader's, bound as above. Reports that quote
  assessment outcomes alongside resolutions label which is which.

## Engine 1.5.0 fixture migration (2026-10-12)

Engine 1.5.0 made `stage` a required field on every claim a strict load
accepts (the engine's Spec 004 R1.1). Bundles written before that rule are
refused until each claim names its stage. This section records how this
benchmark's bundles were migrated when the engine pin moved from 1.4.0 to
1.5.0, and what was deliberately not changed.

Stage choice. Every migrated claim is an authored claim with no
verification evidence behind it, so every one is `created` — the first
stage: written down, not yet checked. No fixture claim carries completed
verification evidence, so none was marked `checked` or higher. The migrated
bundles:

- `specs/001-benchmark/claims.json` — all 14 requirement claims (status
  `unsupported`, no evidence).
- `tests/test_diagnostic_termination.py` — the `claims_bundle()` builder
  used by the diagnostic-termination tests.
- `tests/test_matched_repair_port.py` — the D01 draft bundle.
- The runner's own synthesized non-termination claim
  (DIAG-NONTERMINATION-01) in `src/benchmark_runner/matched_repair.py` and
  `scripts/repeated_local.py`. The runner writes this claim itself at the
  moment a phase runs out of actions; nothing has checked it, so it is
  `created` too.

No expected score, status, or verdict in any test was changed. The
migrated claims were never supportable (status `unsupported`, no
evidence), so the stage cap — which limits how far a claim's status may
be reported, given its stage — changes nothing they assert. Verified
against the real 1.5.0 engine (the release commit, c0d8094): the offline
suite went from 309 passed / 12 failed before the migration to 319 passed
/ 2 failed after it, in a local run. The 321-test baseline is the CI count
on engine 1.4.0; the local difference is exactly the two named items
below plus one timing-sensitive provider test that does not touch the
engine and passes or fails with machine load (it failed in the
before-run and passed in the after-run, on identical code).

Not migrated, deliberately:

- The vendored extension template
  `.specify/extensions/aee/templates/aee-claims.json` still has no
  `stage`. Its bytes are pinned by digest in `manifests/versions.json`
  and checked by `scripts/check_pins.py`; editing vendored bytes locally
  would make the digest record untrue. The template gains its stage when
  the extension is re-vendored from its next release. Until then,
  `tests/test_workflow.py::test_real_deterministic_extensions_on_synthetic_claim`
  fails at its first assessment (the template bundle). Its second
  assessment, of `specs/001-benchmark/claims.json`, is migrated here and
  composes (outcome `iterate`, one evaluator).
- `tests/test_assessment_diagnostics.py::test_invalid_claim_kind_retains_subprocess_failure`
  still fails, for a different reason: its assertion requires the word
  `ClaimKind` in the retained engine error text. Engine 1.4.0 produced
  that word through a Python enum traceback; 1.5.0's strict loader reports
  the same failure in plainer words ("field 'kind' has invalid value
  'observed'; valid values: ..."). The failure itself, the non-zero exit,
  and the retained diagnostic are unchanged. Updating the assertion to the
  new wording is a decision for the benchmark owner, not part of this
  migration; the deliberately invalid fixture was left exactly as it was.

Pin record. `pyproject.toml` and `manifests/versions.json` now pin engine
1.5.0, and `uv.lock` was regenerated against the published release (only
the engine entry changed, plus the lockfile format revision the current
uv writes). This note supersedes the 1.4.0 pin note, which read: "PyPI
release 1.4.0 (git tag v1.4.0; commit in aee_engine_commit). Engine main
carries unreleased post-1.4.0 merges (HEAD 1b2ea3f at re-pin time); they
are not measured by this benchmark until a release is cut and this pin is
bumped." That release is 1.5.0, and this migration is the bump it waited
for. Extension and evaluator pins are unchanged; their bumps ride their
own releases.

One runtime consequence, recorded for the next protocol revision: the
claim text the runner asks models to produce at run time (the prompt text
and the vendored claims template) does not yet ask for a `stage`. The
offline suite does not exercise that path, but a real run on engine 1.5.0
will refuse model-produced bundles that omit it. Prompts are part of the
frozen treatment and are not edited here; asking for `stage` in run-time
claim requests belongs in a protocol revision alongside the extension
re-vendor.

### Completion: extension re-vendor and the diagnostics assertion (2026-10-12)

The two residuals named above are now resolved, and the offline suite is
fully green on engine 1.5.0: **321 passed, 0 failed** in a local run of
the full suite (the 321-test CI baseline, reached exactly).

Extension re-vendor. The vendored pair was replaced wholesale with the
release archives, following the established procedure (vendored tree =
the source archive's contents exactly; benchmark-local artifacts —
`aee-config.yml`, `assessments/`, `ledger/`, evaluator `results/` —
preserved):

- AEE extension 1.2.0 @ 527feae → **1.4.0**, tag archive
  `https://github.com/electrohire/spec-kit-aee/archive/refs/tags/v1.4.0.zip`
  (sha256 `14e02e74…`, tag commit `d7d7ce4`), vendored tree digest
  `b71c5a30…`.
- Evaluator extension 1.0.0 @ eee9fef → **1.1.0**, tag archive
  `https://github.com/electrohire/spec-kit-evaluator/archive/refs/tags/v1.1.0.zip`
  (sha256 `07ac2aa1…`, tag commit `8c7e6bb`), vendored tree digest
  `cbcff103…`.

Archive digests were computed locally from the downloaded bytes and are
recorded in `manifests/versions.json` (the earlier `null` entries are
superseded); `scripts/check_pins.py` is green, and the `.registry`
records were updated to the new versions and manifest hashes.

Two consequences of the 1.4.0 extension, both verified against the
vendored bytes. First, its manifest declares the evaluator extension a
required companion and its runner's `assess` refuses (exit 2) when
`.specify/extensions/evaluator/` is absent from the project. The
workflow's `assess()` builds a fresh synthetic project per call, so it
now installs the vendored evaluator tree into that project (the
benchmark-local `results/` directory is not copied, and installed
extension files are excluded from the assessment's artifact record —
the results the run produces there are not). Second, the template
bundle itself is unchanged and still carries no `stage` field; it
loads because the 1.4.0 runner passes the engine's `--lenient` flag,
which defaults the stage on the record: a probe assessment of the
template records `loading_mode: "lenient"` and the claim at
`stage: "created"`, outcome `iterate`. Strict loading still refuses
stageless bundles; the lenient default is the runner's recorded
choice, not an edit to vendored bytes.

Diagnostics assertion.
`test_invalid_claim_kind_retains_subprocess_failure` no longer asserts
the word `ClaimKind` as a traceback artifact, and its exit assertion
is strengthened from "non-zero" to exactly 2. What it asserts now is
the retained diagnostic's load-bearing content on the path the
benchmark actually runs: the vendored runner loads through the
engine's `--lenient` path, whose error for this fixture is the single
line `Error: 'observed' is not a valid ClaimKind` (verified against
the 1.5.0 CLI directly; the strict loader's longer wording — "field
'kind' has invalid value 'observed'; valid values: ..." — is not the
message this path retains). The protective intent is unchanged: an
invalid claim kind fails loudly, the subprocess exit is the hard-error
code, and the retained diagnostic names the offending value and the
field domain that rejected it.

The runtime consequence recorded above is unchanged and stays open:
live-run prompts still do not ask models for a `stage`. That belongs
to a protocol revision; no prompt was edited here.
