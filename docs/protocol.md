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
