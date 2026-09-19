# Repeated local study — prospective protocol

This is a new, separately frozen campaign following the failed/interrupted run03.
It does not replace earlier evidence or execute the original SWE-bench pilot.
User authorization: free local inference only; implement all proposed reliability,
workflow, workload, paired repair and repeated-project improvements. Do not update
email or article. No favorable outcome is assumed or required to report results.

## End-to-end comparison

TinyDB 4.9.0 (`19066e03139e904c24410e23901e4b069d715a2e`, MIT) and cachetools 5.5.2
(`c403f9f4185e58090b904c1915345b9ba46d5a08`, MIT). Two seeds: 20260918 and 20260919.
Three arms per project/seed: ordinary capable agent; adapted Spec Kit; adapted
Spec Kit plus actual installed AEE/Evaluator. Total 12 trajectories, 36 dependent
milestones. Milestones are not independent observations. These are two convenience
selected, controller-authored library extensions, not representative production
projects or externally authored tasks. Two seeds provide limited replication,
not a statistically powered superiority claim.

TinyDB: atomic batches, nonmutating preview/strict validation, idempotency.
cachetools: detached tagged LRU storage, intersection invalidation/resize, expiry.
Stage two introduces compatibility requirements and a superseded asserted note.
Stage three restarts the container and clears conversational history while retaining
source and all repository notes. Every arm has identical information and permission
to write notes. The reset is a simulated handoff, not a multi-day human handoff.

Same local Qwen3.6-35B-A3B UD-Q4_K_M weight and llama.cpp b11026 as run03; physical
server context 131072, but request context bounded to 32768 including max output4096.
Model weight SHA-256 remains ac0e2c1189e055faa36eff361580e79c5bd6f8e76bffb4ce547f167d53e31a61.
Both verified GPUs; same 9:14 layer split, q8 KV, one slot, thinking budget2048.
Temperature0.6/top_p0.95/top_k20/min_p0/repeat1/presence0. No paid API or fallback.
Calls are sequential, with cache disabled at the start of every trajectory.
Actual request/native usage/timing and failures are retained; logical cached input
counts once in input and is separately reported from uncached input and output.

Near-context latency calibration runs two uncached requests approaching the 32768
provider limit with output cap4096. Timeout=max(180, min(600, ceil(2*slowest/30)*30))
seconds. Current calibration is about59 seconds/request, producing180 seconds.
Unlike run03, the provider has no hidden120-second adapter ceiling. Unknown native
usage stays null. Budget debit uses full preflight input+output reservation until
usage is known. Wait for the server slot to become idle before continuing after a
failed request; do not overlap uncertain work. Never label reserved tokens as measured.

Budget per stage:160 primary model calls plus up to2 public-feedback repairs of8
calls each, within2400 seconds. Entire project logical-token reservation cap18M.
Each request needs its complete timeout remaining; no almost-expired request starts.
Document phase quotas32 each, implementation32, convergence16, final implementation16;
implementation evidence rework up to16 within the same160-call ceiling. A two-actions-
remaining notice applies to all phases/arms, and the last allocated action is reserved for an honest done report. A second workflow calibration exhausted its evidence-rework allocation on test/document rewrites; this failure is retained. AEE feedback now explicitly distinguishes claim-quality findings from established code defects. These changes precede scoring. Earlier full workflow calibration
failed an8-call constitution quota and is preserved as setup cost. Revised quotas
are set before scored generation. No post-outcome tuning or selective reruns.

Full frozen skills are executed through an explicit JSON/shell adapter. This new
runner replaces mini-SWE-agent's120-second Model adapter; it is an adaptation, not
an official Spec Kit integration. Scripts/templates and generated workflow files
are kept in the same repository. Model-native reasoning is not copied into future
requests. Drop oldest exchanges only at the measured context boundary, logging
counts. Public tool observations are bounded at6000stdout/2000stderr characters;
full command outputs are retained in content-addressed evidence. Compact AEE feedback
includes outcome/findings/recovery, excluding repeated nested metadata; raw output
remains recorded. Planning assessments are advisory. Non-pass/non-warn implementation
assessment gets one evidence-rework opportunity. Missing phases/errors remain failures.

## Calibration and independent grading

Before scored calls: reference implementation passes all stage/public/hidden checks;
unchanged upstream fails new features; unrelated arithmetic calibration completes
all seven phases, four normal AEE assessments, an actual evidence-rework assessment,
and a public-feedback repair after an explicitly injected unscored regression.
The workflow calibration is distinct from feature/grader calibration. Controller
also uses explicit AEE/Evaluator assessments; those are not model performance scores.

Solvers have no host mounts/network/hidden cases. Only approved Python package files
transfer into a fresh nonroot Docker grader. Preserve untouched upstream tests.
Exact expected totals: TinyDB public225/226/227, hidden228/233/239 (223 upstream);
cachetools public218/219/220, hidden221/226/232 (216 upstream). Zero failures/errors/
skips and exact discovery required for full acceptance. Hidden tests run only after
all generation. Source review and regression tracking supplement functional grades.
Both primary and repaired snapshots remain. Public repair sees only public tests.

## Matched repair diagnostic

A separate frozen experiment uses the reference source with three single injected
faults and one clean control per project, crossed with the same two seeds and two
repair treatments:32 repair trajectories across16 matched pairs. Bug definitions
and independent fixture grades are frozen before diagnostic model calls. Do not
supply fault labels, reference code or hidden feedback to the model.

Both arms get the identical source, current requirements, public feedback and a
shared read-only diagnostic/claims bundle (up to8 calls). Diagnostic edits invalidate
that bundle; the original frozen source is restored for both treatments. Ordinary
repair gets the raw diagnostic; guided repair additionally gets the actual AEE/
Evaluator findings derived from that same bundle. Each receives two8-call repair
opportunities within1200seconds, even if public tests pass, since public tests do
not cover every requirement. Clean controls may correctly return unchanged code.
These are ordinary versus AEE-guided repair, not whole Spec Kit treatment arms.

Shared model diagnostic work is counted once in the physical inventory, and charged
in full equally to both arms when comparing per-case end-to-end repair economics.
Report that attribution separately to avoid double-counting physical work. The
actual deterministic AEE runtime is reported separately. No hidden outcome is fed
back; grade every repair snapshot afterward to determine first successful repair.

## Outcomes and interpretation

Primary: accepted milestones/projects; final accepted/fixed diagnostic cases;
all-attempt tokens and seconds per acceptance/fix (undefined when zero); calls,
repair rounds, code-changing rounds, regressions and workflow completion. Separate
cached/uncached prompt tokens, generated tokens and native decode/prefill timing.
Count failed requests, development calibration, setup failures and unknown usages.
Public pass versus hidden pass and workflow completion are distinct outcomes.

Adjudicate concrete defect findings against seeded fault locations and independent
case failures. A generic missing-evidence/unsupported-claim finding is an evidence
gap, not automatically a true or false code-defect detection. Report concrete true
findings, false alarms, unresolved judgments, evidence gaps, and control-case churn
separately. Useful fixes require an observed failed-to-passed transition without
regressions; temporal association does not prove the finding caused the fix.

Retain all previous experiments. Publish fresh report and immutable freeze/source
hashes; no exact native-reasoning replay claim. All result claims cite artifacts.
API expenditure0; electricity/hardware/controller work unpriced. ElectroHire maintains
the evaluated packages and benchmark; independent replication remains absent.

A third calibration exhausted its plan phase while still writing supporting artifacts. Phase quotas were increased to32 with160 primary calls/stage before scored generation; this is preparation cost, not a scored model improvement. All failed calibration requests remain in the inventory.
