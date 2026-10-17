# Current-version lifecycle study — prospective protocol, 2026-10-16

This fresh free-local campaign uses engine1.5.3, Specify1.2.1, AEE extension1.5.2,
evaluator1.1.2 and mini-SWE-agent2.4.6. It does not overwrite September studies or
execute the original 180-attempt SWE-bench pilot.

The task inventory and independent grading are the existing staged TinyDB4.9.0
and cachetools5.5.2 tasks under benchmarks/repeated_local, at their pinned source
commits. Two seeds20261016/20261017 × three arms × two projects =12 trajectories,
each with three cumulative stages (36 dependent checkpoints). Convenience-selected
controller-authored library tasks and two seeds cannot establish general superiority
or production lifetime savings. Stage3 clears conversation and restarts the
container while preserving code/notes: simulated handoff, not elapsed months.

The shared localhost llama.cpp router is used without changing its configuration.
Exact model ID qwen3.8-27b, observed model/server properties, local weights
SHA256, GPU inventory, package versions, image ID and source hashes are frozen.
No paid endpoint, proxy, redirect, fallback model, overlapping generation or
unrecorded retries. Samples: temperature0.6/top_p0.95/top_k20/min_p0/repeat1/presence0;
native response identity must match. Context is capped at32768 including4096
output tokens, selected by native-template/tokenizer calibration. The server's
larger physical context does not enlarge this request budget.

Before scored generation: untouched/reference grader checks for every project/stage,
strict-schema tests, complete core workflow with four actual AEE/evaluator checks
plus independent injected-bug repair, native context-selector equivalence, and
two uncached near-context latency probes. Timeout is180–600 seconds by the prior
protocol's twice-observed-latency rule. Failed calibrations are retained as setup
cost; no scored outcome is used to tune prompts, model or limits. Shared treatment
and provider ASTs are checked against the archived successful calibration.

The earlier gpt-oss-20b-Q5_K_M candidate failed unscored workflow calibration
on structured claim output. Its readiness and both retained calibrations remain
setup cost. The qwen3.8-27b candidate is selected prospectively before any scored
generation, subject to the same complete calibration gate. No service config is
changed and failed attempts are not erased.

Same tools, model/configuration, task text, public tests, ceilings and feedback
policy for every arm. Primary160calls/stage plus at most two public-feedback
repairs of8calls, within2400seconds/stage; total reservation ceiling18M tokens per
trajectory. Unknown native usage remains null; full next-call reservations enforce
the ceiling. Stop or cancel if a request cannot be shown idle after failure.
Every failed/abandoned attempt remains in the denominator; no favorable reruns.

Baseline is an ordinary capable agent. Structured arms use freshly regenerated
core operation skills, artifacts and phases. Combined additionally submits actual
task claims to the installed AEE runner and evaluator after specify/plan/tasks/
implementation. Claim examples must parse under the installed strict engine.
Machine verification does not substitute for recorded human explanation/acceptance;
never fabricate those stages to obtain a green outcome. AEE findings are not
independent bug grades. Treatment adherence and assessment errors are reported.
Each combined trajectory has one persistent, isolated AEE project/anchored ledger;
only its own hash-verified tool artifacts are copied there. Compose exactly the
current invocation's result while retaining earlier provenance. A block verdict
or assessment execution error stops further primary actions and public repair in
that milestone; it is not silently bypassed. Recovery-needed findings remain
visible to subsequent phases, with bounded implementation evidence rework.
All local arms use the same custom tool-backed session adapter inherited from the
earlier staged studies. Mini-SWE-agent is installed for the separate SWE-bench
runner; this local study does not claim to execute its DefaultAgent class. The
Spec Kit treatment is a host adaptation of installed skills/scripts, with explicit
AEE execution, not an end-user ergonomics or native hook-installation benchmark.

The dependency lock is upgraded compatibly before scoring. The in-flight model
calibration's original environment remains unchanged. If the final lock differs,
every actual AEE/evaluator calibration checkpoint must be replayed under the final
environment with identical scores, findings, routing and lane states; full offline
tests and dependency checks must pass. Native stdlib transport/phase ASTs and
model/config must match the successful calibration. Record both locks and the
deterministic replay; do not relabel old environment evidence as a new run.

For the same final completion opportunity across arms, solve/final-implementation
and repair prompts request `completion_asserted: true/false/null` in done JSON.
True asserts all active requirements implemented; false admits incomplete work;
null or an omitted/malformed field is unknown. Synthesized terminal records never
invent an assertion. Join the last terminal declaration to independent grading of
that exact final snapshot. False completion =positive assertion with failing
complete independent grade. Report positive, negative and unknown opportunities
separately; failing code without a positive assertion is not automatically a
hallucination. This is one operational proxy, not a comprehensive hallucination
taxonomy. Do not post-hoc relabel vague summaries as confident assertions.
Retain the corresponding primary declaration before public-feedback repairs.
Where a primary false completion is independently established, distinguish an
independently passing final repair from withdrawal of the positive declaration;
neither is inferred from an AEE score. Generic public-feedback repair is shared
across arms and does not by itself isolate an AEE-specific mechanism.

Hidden grades run only after generation finishes; solvers receive public feedback
only. Report primary/final hidden acceptance, source-changing repairs, regressions,
false completion, all model tokens (including failures), phase costs and paired
project/seed outcomes. Checkpoint observations are not independent trials. Do not
infer detector precision/recall unless the exact claim has an independently labeled
truth and a recorded matching detector decision; otherwise leave it unmeasured.

Actual API expenditure is $0; hardware/power/human time remain unpriced. Any cost
scenario must disclose its rates and remain hypothetical. Never call token savings
financial savings when quality differs or accounting is incomplete. The economic
break-even hypothesis is avoided repair/regression cost exceeding added workflow
cost at matched quality. No favorable conclusion is a condition of completion.

No PR merge, release or article publication is authorized. Archive inputs before
the first scored request, validate hashes on export, omit raw private reasoning,
and publish reproducible results, retained setup costs, limitations and README
interpretation after all scheduled trajectories and independent grades finish.
