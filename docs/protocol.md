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
