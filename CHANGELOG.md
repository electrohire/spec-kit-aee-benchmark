# Changelog

## Unreleased — malformed claims submissions are model feedback, not a study-halting crash, 2026-10-24

* Fix the defect that halted the Stage B candidate leg (attempt 8, pytest-dev__pytest-5809, Spec Kit + AEE arm, 2026-10-23). A claims bundle whose entries are not the expected objects — a claim written as a plain string, an evidence entry written as a plain string, an evidence field that is not a list, or a "claims" field that is not a list — passed submission handling and then crashed inside claim grounding with AttributeError: 'str' object has no attribute 'get'. The tripwire classified the crash as an unclassified error and stopped the study. The submission handler checked only that a full bundle's "claims" is a list; it never checked the shapes of the entries inside it, and neither did the merged result of a delta. Delta structure errors already had a defined outcome under Workstream A2 (a malformed submission is a model outcome, fed back in-phase); entry shapes did not.
* Submission resolution and claim grounding now validate entry shapes at the boundary and reject a malformed bundle with a specific reason (DeltaFormatError). On the workflow path the runner feeds that reason back inside the phase and the model resubmits — the same defined behavior A2 established — and no assessment is produced from a malformed bundle. Grounding validates too because matched repair submits raw model output to it directly. Nothing is caught and silently skipped.
* Attribution correction: the defect was in this benchmark harness, not in the AEE engine. The engine and evaluator run as subprocesses whose failures surface as named harness errors, never as this crash, and the crashing code is the harness's own submission/grounding path. Engine 1.6.0 does not carry the defect; the Stage B record's description of it as "the candidate engine's AEE recovery defect" was wrong.
* Regression tests: seven new tests in tests/test_needle_workstream_a.py pin the defined behavior for every malformed shape (string claim entries, string evidence entries, non-list evidence field, malformed delta upserts, malformed bundles at grounding, and an attempt-level test where a malformed specify submission is fed back and the resubmission is assessed). Before the fix they fail — the malformed shapes are accepted, and grounding raises the exact production AttributeError; after the fix they pass. No existing test was changed. No inference was run; no frozen study input was touched.

## Unreleased — needle program Workstream A: cut assessment overhead, 2026-10-21

* A1 compact assessment feedback: the coding workflow (runner) now appends a compact projection of each assessment result to the persistent conversation instead of the full composed evaluator result as raw JSON. The projection's key set is exactly outcome, findings, next_action, confidence, uncertainty, gate_outcome, lanes (lane 1 outcome; lane 2 stage counts and claims below explained), and recorded_acts_summary (count, basis types, actor). The full result stays in the run store (assessments record) untouched and schema-valid for audit; workflow.assess() returns the recorded-acts summary as an augmentation only. Measured on the retained current-study-01 AEE attempt records (fixture replay, tests/test_needle_workstream_a.py): the retained set holds six specify-phase assessments across four attempts — the only phases those attempts reached — and the compact payload is smaller on every one: cachetools-20261016 assessment 1: 57,654 → 21,904 characters (−62.0%); cachetools-20261016 assessment 2: 59,820 → 15,785 (−73.6%); cachetools-20261017: 39,000 → 11,946 (−69.4%); tinydb-20261016 assessment 1: 32,501 → 12,190 (−62.5%); tinydb-20261016 assessment 2: 71,354 → 22,685 (−68.2%); tinydb-20261017: 37,123 → 14,415 (−61.2%). Total 297,452 → 98,925 characters (−66.7%). This establishes smaller feedback payloads only; whether models behave identically on compact feedback is a question for a paired live run, not established here.
* A2 delta claim submissions: after an attempt's first assessed phase, phases and repair rounds submit a delta (changed/new claims as full claim objects under "delta.upsert", withdrawals by claim id under "delta.withdraw"); the harness merges it into the attempt's standing bundle, then grounds and assesses the merged bundle. A full bundle remains accepted as a replacement. A malformed delta (including a withdrawal naming an unknown claim id, or a delta on the first assessed phase) is a model outcome: the reason is fed back inside the phase's step flow and the model resubmits — never an unhandled harness exception.
* A3 claim-count discipline: the discipline text (one claim per independently falsifiable requirement, merge duplicates, prefer few and load-bearing) now stands in prompts/adapter.md and in the claims instruction injected for AEE phases. A soft cap of 12 claims per phase bundle earns exactly one in-phase consolidation request (never more than one per phase) before assessment. The assessments store record now carries the per-phase claim count of the assessed bundle. That 12 is the right number, or that fewer claims are better claims, is not established; the counts are instrumentation for the next study.
* Offline verification: maintained suite 305 passed before the change, 318 after (the 13 new Workstream A tests included); no existing test was changed. No inference was run.

## Audited stopped coding preparations, 2026-10-20

* Publish the bounded four-attempt reconciliation: 23 physical requests, 241,913 known native tokens, 0 usage unknowns; setup and scored preparation remain separate.
* Preserve frozen source/input/runtime/archive and receipt commitments, original incomplete required-test observations (1 pass / 3,519 unknown each), and all unattempted endpoints. No final delivery, scored AEE exposure, coding savings or payback is established.
* Document the latest model path error and pending explicit stop-policy decision without changing solver files, benchmark policy or starting inference.


## Audited matched classification and authorized completion, 2026-10-20

* Publish 720 independently graded matched HaluEval/RAGTruth judgments, raw/gate views, paired cluster intervals and symmetric 693-row original-worker sensitivity. Results do not establish a consistent material AEE advantage or token payback.
* Preserve original03's worker crash, 711 retained judgments, orphan draft and failed-request unknown. Restore only the existing profile under explicit approval; separately freeze and complete only 9 missing cells, 18 calls, after 3 bounded native checks. No original row is rerun; all 1,487 requests/at least 5,613,402 native tokens/1 usage unknown remain counted.
* Repair 27 malformed bold labels across 10 presentation documents; preserve all measured numbers and non-README evidence bytes. Track presentation provenance and update only 3 README manifest entries. Add a guard for malformed generated bold labels.
* Established coding economics remains pending; no release approval or completion-email claim.


## Unreleased — bounded native matched output v2

* Retain attempt 01's first length stop: 72 graded/1 attempted-ungraded/647 unattempted rows, 185 calls/712,919 native tokens/0 usage unknowns and 54 actual AEE assessments. Model identity was correct; extended rationale exhausted the 1,024-token cap.
* Four negative schema cases exposed unbounded strings. Bound policy/rationale/ quote/uncertainty fields in native JSON for every arm and repeat concise review instructions. Preserve output/context/call budgets, model, labels and graders; a fresh registered v2 attempt requires actual native checks and exact-green CI.
* Correct token accounting so two arms delivering no verified requirements cannot establish payback. Preserve the isolated red counterexample and 13 candidate checks; no empirical savings or treatment efficacy is asserted.

## Unreleased — prospective matched treatments and horizon accounting

* Register a separate baseline/Spec Kit/Spec Kit+AEE source-grounding comparison using unchanged HaluEval/RAGTruth cases and author labels. Real Spec Kit helpers, generated draft policies, AEE/Evaluator feedback and anchored local ledgers are checked alongside physical call, source and token receipts. No matched model results or treatment benefit are asserted yet.
* Add conservative observed token break-even accounting and a prospective FeatureBench Fast v1.1/SWE-EVO adoption plan. Synthetic accounting tests are distinct from empirical savings; incomplete usage, poorer retained quality or missing adjudication cannot establish payback. Products remain parked.

## Results — separate external hallucination detection, 2026-10-19

* Complete 240 native calls and independent source-label/receipt/hash grading: HaluEval 100/120 correct, 17 misses/3 false alarms; RAGTruth 97/120 correct, 11 misses/12 false alarms. No abstentions, invalid decisions or usage unknowns; 213,457 known native tokens. Publish dedicated report/cluster intervals and sanitized receipts without pooling coding or synthetic factbook results. No AEE/Spec Kit efficacy or generated hallucination prevalence is measured.
* Retain the later offline HaluEval JSONL-export parsing failure; fix the format handling and rerun export/audit only, with no new model generation. Coding study 08 remains stopped on its 13-call malformed-argv outcome.

## Unreleased — separate published hallucination datasets

* Pin original HaluEval/RAGTruth revisions, MIT notices and a240-response seeded selection before model calls. Add a separate detector runner with no coding overlap/retries and independent gold/receipt/schedule/usage audit. Keep abstentions and failed/unattempted rows visible. New model results pending; no AEE efficacy, workflow prevalence or full-benchmark score is asserted.

## Unreleased — structured-only current tool protocol

* Preserve study 07's first malformed grep failure and 15 calls. Remove shell actions from current native v6 grammar, enforce literal argv at execution, retain legacy v5 sources/contracts for historical checks, and require fresh four-action native proof plus two fresh v6 latency samples. Apply the same tooling to every arm; no model/cap/grader changes or successful-result claim.

## Unreleased — user-directed fail-fast amendment, 2026-10-19

* Mitigate repeated direct-worker TCP handshakes with persistent connections, preserving literal JSON, model/process checks, timeouts and no retry/fallback. Retain context failures and include external reused setup calls in export. Preserve pipeline 12's zero-generation preflight stop and historical v1 contract; fresh context 13 passes, without claiming the historical timeout cause is solved.
* Accept only the fixed `/testbed/` writer prefix as a workspace alias while preserving canonical/traversal/symlink guards. Retain study 06's7-call failure; replay its unmodified action separately with zero generation, not as scored success.

* Stop study 04 and preserve its partial evidence/costs. Diagnose incomplete grep actions and runner success bookkeeping. Add literal argv actions and first-error campaign halting, including public/hidden verification; withhold repairs and next trajectories after failure. Preserve legacy policy for historical replay only.
* Require fresh native argv transport and grammar latency proofs plus exact prospective AST/constant registration. No claim of model reliability, completed benchmark results or comparative efficacy follows from the runner correction.

## Unreleased — authorized corrected study 02, 2026-10-18

* Export all 12 stopped-study trajectories/36 checkpoints and independently grade the two retained final snapshots. Preserve incomplete collections as ungraded; report TinyDB's public 225 pass/hidden 227pass1 fail and zero scored AEE exposure. Bind source/grades/graders, retain original-export correction, and generate the prominent README from audited artifacts. No inference, restart or efficacy claim.

* Halt immediately on infrastructure/transport errors, retain bounded failed request/response diagnostics, and preserve the original intervention across alert-write failure. Keep missing usage unknown.501 offline tests pass; retain the initial red cases and failed first audit composition. Study 02 remains stopped with historical server/storage cause unresolved; no retry or model call.

* Record study 02's terminal infrastructure interruption, 192 generation calls and 4,172,224 native tokens without claiming completed scoring or comparative benefit. Preserve 348 input hashes, existing chains and all setup history. Document current successful storage/template diagnostics without asserting an established cause.


* Retain readiness 07's81 calls/1,798,706 native tokens and missing-task intervention. Retire phase-scoped host imperatives while keeping structured observations, errors and model claims; reject stale controls before another model request. Use a phase-neutral completion example. No budget, model or grader change.

* Retain readiness 06 failure and all 45 calls/913,153 native tokens. Parse shell actions before executing any prefix, including rejecting unterminated-heredoc warnings; report observed phase artifact state at bounded progress checkpoints. No extra model calls, budget extension or acceptance relaxation.

* Protocol v4 requires shell command and write_file path/content directly in both native phase grammars. Fresh transport 03 caught v3's optional content field before execution; retain its two calls/221 known tokens. No retry or scoring success is inferred. A new frozen candidate and complete probes remain required.

* Preserve readiness 05's305 calls and the stopped identical-action loop. Add a shared native literal write_file action to avoid nested shell/Python heredoc quoting, with confined bounded UTF-8 data and retained original actions/receipts. The three-action loop guard, budgets and grading remain unchanged. A new preparation requires four actual probes and fresh grammar-bound latency; stale probes/timing are rejected before readiness or scored generation.

* Require typed nonempty claim bundles on claim-phase done/draft native actions; retain strict engine/evidence validation and runtime interruption. Transport 02 exercised actual engine loading; representative 04's missing-claim failure and all calls remain setup evidence. Include previous representative setup costs.

* Use the same native JSON action grammar and per-request non-thinking mode for all treatments, with 8192 output tokens and prospectively declared equal ceilings.
* Require all six isolated representative project×treatment workflows, actual AEE checkpoint exposure, public verification and exercised injected repair before a fresh scored freeze. Bind readiness artifacts/configuration/controller hashes.
* Add one serial preparation → readiness → replay → scoring → export supervisor that stops on intervention without retries, retaining earlier preparation and scored costs.
* Record the user's authorization to merge related green PRs and rerun; no release or external article/email publication is authorized.

## Unreleased — study validity investigation, 2026-10-18

* Identify the 120-minute functional calibration / 40-minute scored-budget mismatch and zero structured implementation-phase calls; mark the requested efficacy and economics comparison unanswered without rewriting historical observations.
* Reject calibration timing/cap mismatches and unexercised repairs. Reserve later phase/repair capacity and reject infeasible budgets before scored inference.
* Stop anomalous executions with durable runtime alerts/source snapshots instead of continuing through zero-call phases; cover malformed-action loops, incomplete handoffs, repeated unchanged actions and safety/budget failures with offline tests.

## 0.1.0 (unreleased)

### Current tooling and evidence refresh — 2026-10-16

* Refresh Specify CLI 1.2.1, AEE engine 1.5.3, AEE extension 1.5.2 and evaluator 1.1.2; regenerate operation skills and lock the latest compatible dependencies.
* Add artifact-bound lifecycle reports for explicit false completion, independent grades, regressions, repairs and token/illustrative-cost economics. Preserve failed calls and unknown usage rather than assigning zero.
* Preserve persistent per-trajectory AEE provenance, machine/human lane feedback, strict block/error gates and actual single-result Evaluator composition.
* Add actual AEE validation, adversarial accounting tests and an Ubuntu-only CI check of README tables against measured artifacts.
* Preregister a fresh two-project/two-seed free-local comparison. Calibration and scoring are gated. The completed 36-checkpoint attempt is published with 24 structured collection failures, incomplete workflow/AEE exposure and all failed/unknown costs; no efficacy or savings benefit is established.
* Clarify historical results and their limits prominently in the README. The original 180-attempt SWE-bench pilot remains unrun.

### Initial harness

Offline controller, thin mini-SWE-agent phase adapter, tutorial and reproducibility protocol. No scored SWE-bench pilot results yet; separate historical local explorations are linked from the README and keep their original freezes.

Prospective scored-study admission now counts model runtime interventions as failed trajectories, preserving dependent checkpoints and costs while retaining campaign-wide infrastructure stops. User directed immediate scored benchmarking; no solver/grader/budget changes.

## Prospective study 03 preparation

* Fresh serial pipeline 10, exact infrastructure migration, preserved stopped 02.
* Twelve real-model labelled factbook diagnostic, separated from workflow efficacy.
* Product coverage work parked; no new results claimed before execution.

## Completed labelled diagnostic (2026-10-19)

See [real-model receipts and label-quality findings](reports/local/labelled-factbooks-10-20261019/README.md):12 calls/2037 known native tokens/0 usage unknown, 10of12 original-labelagreement, two challengedunknownfixtures. Main paired study 03 remains running; no completed paired efficacy conclusion. Active source stays frozen in its original checkout.

### Prospective correction of two diagnostic fixtures

The user explicitly requested fixing issues found during tests and rerunning. The published v1 corpus and results remain immutable. `hallucination-cases-v2.json` changes only the facts for case-09 and case-11: absence of a completed execution record replaces an explicit unfinished-run counterexample; an incomplete empty citation inventory replaces the explicit mismatching digest. Labels, claims, other ten cases, oracle, model, seed and diagnostic caps stay unchanged. This repairs ambiguous unknown controls; it does not rewrite v1 model outcomes. Fourteen targeted mission checks pass locally (36 including affected infrastructure/current-run checks).

After the existing pipeline 10 has stopped generating and its final grading/export/audit is handled, inspect processes/status/model-qualified slots and run exactly once in a fresh directory using the merged corrected source: `python scripts/labelled_hallucinations.py artifacts/current-hallucination-11 --corpus-version 2`. Do not interleave inference with the active campaign, modify its frozen checkout, overwrite old diagnostic artifacts, or silently rerun failed software trajectories. Publish v2 receipts and compare with v1, retaining the post-outcome fixture-correction disclosure. This authorization covers genuine harness/test fixes and affected reruns; model failures remain measured results.

## Study 03 infrastructure stop (2026-10-19)

[Retained results and independent grades](reports/local/current-study-03-router-stop/README.md). Pipeline 10 ended 13:45:11UTC/09:45:11Eastern. No generation active. RouterHTTP500 body: proxy error: Could not establish connection.98calls1,908,355 known native tokens/0 generation usage unknown; 2attempted34 unattempted rows. Exactrequest/responsecaptured; present-dayzero-generationreplaypassesbutunderlyingcauseunresolved. No auto retry/resume, sharedservicechange or v2 diagnostic generation. ActualNoeRelayruntime/router.stderr.log found; captured proxy connection failure to existing qwen worker port 50467; underlyingcauseunresolved. No completed paired benchmark or efficacy conclusion.


* Prospective client-only route to the existing operator-approved qwen worker, with process/port/model/path guards and fresh direct-route admission. No fallback, service change, task/cap/grader change or stopped-run resume. Pipeline 11 serially includes corrected diagnostic corpus 2. Historical router failure cause remains unresolved.


* Publish the authorized corpus 2 real-model corrective diagnostic: 12/12 bounded labels, 0 invalid, 12 calls/1974 known tokens/0 usage unknowns, 368 frozen inputs verified. Original corpus 1 retained; post-outcome fixture correction and limits explicit. Software study 04 still active; no completed paired result claimed.


* Fix final setup export collisions across readiness runs with matching directory basenames. Retain every archive and physical-call receipt; repeated identical path arguments export once. No token/grade/metric/solver change. Three regressions red before, 51 focused cases green after; real five-source 378-call zero-inference export rehearsal passed. Active study 04 source remains frozen; use corrected reporting only after scoring has ended.

* Matched 02 immediate calibration halt retained: 16 calls/56615 native/0 unknown/0 scored. Diagnose pinned-server repetition>2000 expansion; prospectivev3 explicit split grammar retains schemas/caps. No server change or treatment efficacy claim.

* Established upstream task/label/grade policy replaces custom-task maintenance; preserve historical evidence. Add harness/results Mermaid I/O guide and prospective content-bound build/release comparison with explicit practical margins, strict uncertainty handling and no accepted baseline yet.
