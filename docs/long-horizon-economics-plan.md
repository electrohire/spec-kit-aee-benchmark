# Prospective short- and long-horizon token economics

Status: researched protocol proposal and tested accounting helper, **not a completed FeatureBench/SWE-EVO comparison or evidence of treatment savings**. Reviewed official sources on 2026-10-19. Product development stays parked. The separately requested [matched HaluEval/RAGTruth comparison](../reports/hallucinations/matched-03-recovered-20261020/README.md) is complete, audited and published; its paired intervals cross zero and it establishes no consistent AEE benefit. The latest upstream attempts stopped before implementation; their costs and partial grades remain retained. Real resource/grade and cold/warm controls pass, but a corrected attempt still requires a fresh source freeze and admission.

## Established evaluation candidates

| Suite | Relevant work | Recommended use | Boundary |
| --- | --- | --- | --- |
| [FeatureBench](https://github.com/LiberCoders/FeatureBench) | Feature-level development with independent tests; Fast has 100 instances and needs no GPU for grading; dataset v1.1 corrects task statements | Start with a prospectively selected small pilot from Fast v1.1, then expand using a frozen selection rule | Independent tasks do not establish persistent-project amortization; publish subset results as a subset, not the full leaderboard score |
| [SWE-EVO](https://github.com/SWE-EVO/SWE-EVO) and [paper](https://arxiv.org/abs/2512.18470) | Release-level software evolution, requirements interpretation and multi-file implementation | Main long-horizon candidate, using its original independent grader | A base-to-release task is not automatically a sequence of separately accepted releases; intermediate observations are our instrumentation |

These replace convenience tasks as the primary proposed evidence for general coding claims. Existing convenience experiments, failures, public readiness exposure and their costs remain published and separately identified. No new inference, external agent, model, service or dependency installation is implied by this research. Pin the actual dataset, repository, image and grader revisions and verify local resource requirements before selecting tasks or launching.

## Three matched arms and two economic questions

Compare the same local model and tool interface under:

1. Generic agent with ordinary notes and tests.
2. Spec Kit with its actual constitution/specification/plan/tasks workflow.
3. Spec Kit plus actual released AEE/Evaluator execution and feedback.

Keep task inputs, initial repository bytes, seed, call/context/output/time caps, test exposure and independent grader identical across arms. AEE's internal assessment is a treatment output, never the independent correctness label. Record all actual treatment work; do not pad the baseline with unnecessary calls to erase the fixed cost of Spec Kit or AEE. Give the baseline comparable access to ordinary persistent notes and the same permitted context capacity.

**Cold start:** How many tokens does a fresh independent feature consume, including setup, implementation, verification and repair? Report task completion, retained tests, false completion and all-attempt cost, including halted work.

**Sustained work:** What happens at increasing observed prefixes of a large evolution task or a prospectively registered compatible change sequence? Preserve each arm's own artifacts and state, without sharing sibling outputs or golden patches. Regrade saved code snapshots in isolated grading containers. Do not feed hidden intermediate grader results back into the solver. Retain all previous requirements and regression tests. Any constructed sequence or intermediate grading is an explicitly named adaptation, not an official benchmark score.

Use predefined checkpoints by elapsed budget/call count for within-task curves, and complete independently graded changes for cumulative project curves. Do not choose a convenient stopping point after seeing a favorable crossover. Separate unchanged-repository continuation from a reset that rebuilds workflow artifacts. In the two-release pilot, carry each arm's actual source and notes into a fresh dependency resource, never the author's intervening implementation. Reuse the controller-managed trusted Spec Kit project, its unaccepted constitution and earlier feature documents; create feature 002 for the next release. The baseline also retains its ordinary notes and creates a distinct second work brief. Reused setup is recorded with zero new model calls, without transferring human acceptance. The same source and tool ceilings remain; do not count saved calls in canned controls as empirical token savings.

## What the ledger must count

Retain unique physical call receipts with native prompt, completion, cached-input and total counters; unknown usage has an explicit reason and gives a lower bound, never a presumed zero. Cached input is a subset of prompt input and is not added twice. Categorize setup, specification/planning, implementation, review/AEE, testing/repair, and context restoration. Include failed setup and abandoned attempts in the study ledger, separate from per-success conditional summaries. Record non-model evaluator CPU time separately; it is not a model token charge.

At each checkpoint publish cumulative tokens, wall time, independently verified requirements retained, regressions, completion declarations and their joined grades. Report tokens per verified requirement and per completed task, with the zero-success denominator left undefined. Missing or partial grades remain visible. For repeated tasks use paired task/seed summaries and uncertainty; dependent checkpoints are not independent samples. Multiple independently generated workflow policies/seeds are needed before generalizing beyond a single policy.

## Observed break-even, with quality held accountable

For two matched arms at prefix k, extra native tokens are cumulative treatment tokens minus cumulative control tokens, including setup. Report first observed cost crossover only where usage and grades are complete, the treatment retains every requirement currently passed by the control, and independently adjudicated unsafe completion claims do not increase. Report sustained crossover separately: it must hold at least two observed checkpoints and at every later measured checkpoint. A later reversal remains visible. Do not extrapolate a payback point outside the measured horizon. "No observed break-even" is a valid result.

The helper `benchmark_runner.horizon_economics` implements these conservative prefix comparisons; its fixtures are synthetic accounting tests, not empirical economic observations. Input authentication, frozen snapshot joins and independent grading remain responsibilities of the experiment's auditor. The helper's requirement and unsafe-claim fields do not authenticate their own provenance.

Native-token crossover is distinct from price-weighted crossover: output and uncached input may have different prices. Any price scenario must retain those counters and explicitly label hypothetical rates. Local API spend is zero, which excludes hardware, energy and labor. No historical freelancer payout, hypothetical price, test pass or internal AEE score establishes money saved.

## Combine evidence without mixing incompatible outcomes

Keep HaluEval and RAGTruth in a separate matched detector experiment. Report accuracy, false acceptances, false alarms, abstentions, recall/precision and all-call token overhead by dataset and treatment. Those labels assess detection of supplied responses, not the rate at which the coding agent invents facts.

For coding, independently adjudicate actual completion declarations against saved source and grader evidence, retaining positive/negative/unknown/ungraded denominators. Generic test failures, AEE findings and abstentions are not by themselves hallucinations. Do not pool detector labels and coding failures.

Present a joint dashboard with separate panels: cumulative cost versus retained correct work; regressions and rework by prefix; factual detection errors versus token overhead; and observed crossover with uncertainty and limitations. This can show a tradeoff (more reliable but more expensive), a dominated treatment, or a genuine observed benefit. The study does not assume which outcome occurs.

## Execution order and admission

Finish the matched external detector harness and its integrity checks first; retain the completed external-01 model-only report. Then pin FeatureBench Fast v1.1 and SWE-EVO, validate independent grading without model calls, and preregister the pilot tasks, checkpoints, full caps and treatment adapters before inference. Run one supervisor on the already authorized local worker. No overlapping study, silent retry or modification of stopped campaigns. First protocol/infrastructure failure halts immediately; preserve its evidence and cost. An affected harness fix needs validation and a fresh registered attempt. Incorrect judgments and failed solutions are measured outcomes and cannot be repaired into passing gold.

Publish the exact sample, cold-start and sustained-work results, all historical attempt costs within explicit inventory boundaries, adaptations, intervals and unresolved limitations. Current detector percentages alone cannot answer whether Spec Kit or AEE pays off.
