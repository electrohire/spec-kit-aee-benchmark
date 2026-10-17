# Spec Kit + AEE benchmark

Compare ordinary coding agents, Spec Kit, and Spec Kit with Evaluator + Applied
Epistemic Engineering on correctness, hallucination management, rework and cost.

**Evidence summary:** current measurements do **not** demonstrate that Spec Kit +
AEE reduces hallucinations or saves tokens or money. Its added planning and
assessment cost must be repaid by measured prevention or recovery of consequential
mistakes. We retain unfavorable results and unknown usage to test this honestly.

## Results and interpretation

<!-- current-results:start -->

### Current-version staged comparison

| Metric | Agent alone | Spec Kit (adapted) | Spec Kit + AEE (adapted) |
|---|---:|---:|---:|
| Final-stage projects delivered | 2/4 | 0/4 | 0/4 |
| Hidden checkpoints accepted | 9/12 | 0/12 | 0/12 |
| Checkpoints without complete test inventory | 0 | 12 | 12 |
| Completed milestone workflows | 9/12 | 0/12 | 0/12 |
| Actual AEE assessments / planned | n/a | n/a | 6/48 |
| All scored tokens | 7,748,458 | ≥8,511,570 (incomplete) | 7,827,107 |
| Unknown token calls | 0 | 1 | 0 |
| Tokens per delivered project | 3,874,229 | undefined/unknown | undefined/unknown |
| False completion / graded positive declarations | 1/9 | 0/0 | 0/0 |
| Unknown completion declarations | 3 | 12 | 12 |
| Source-changing public repair rounds | 0 | 0 | 0 |

**Treatment exposure:** neither structured arm completed a milestone workflow within the fixed 40-minute budgets. AEE was reached at only 6/48 planned checkpoints, all after specification. All 24 structured checkpoints failed test collection: 22 snapshots lack the implementation module; two contain a module that raises `NameError` during import. They remain **ungraded**, not completed failing test inventories. The small successful arithmetic calibration did not establish that full project workflows fit the milestone budget. All 52 public-repair records made zero model calls after their budgets ran out; there is no observed repair efficacy here. These are outcomes of attempted policies under these constraints, not a completed AEE workflow efficacy comparison. A false-completion rate of 0/0 is undefined, not zero hallucinations.

**Insight:** the combined workflow delivered 0 final-stage projects, versus 2 with the agent alone and 0 with Spec Kit. Read this together with all-call tokens and false-completion denominators, rather than treating fewer tokens on failing work as savings.

Two projects × two seeds × three arms, with three dependent milestones each; these are not 36 independent tasks or months of production history. False completion means an explicit positive completion declaration contradicted by independent grading of the exact snapshot. Missing declarations are unknown; a failed test alone is not a hallucination. AEE process findings are not independently labeled detections.

**What it means:** this tests a narrow simulated maintenance/handoff workload and the measured overhead/quality tradeoff. It cannot establish general hallucination reduction, production lifetime savings or an AEE-only causal effect. All API bills were $0; hardware, energy and human work were unpriced. Hypothetical token prices are sensitivity scenarios, not actual savings.

[Full results and paired outcomes](reports/local/current-study-01/README.md) · [Bound grades, completion recovery and cost details](reports/local/current-study-01/lifecycle-report.json) · [Every retained setup call](reports/local/current-study-01/setup-inventory.json) · [Frozen protocol](benchmarks/current_local/PROTOCOL.md)

<!-- current-results:end -->

<!-- historical-results:start -->

| Historical local run | Agent alone | Spec Kit (adapted) | Spec Kit + AEE (adapted) |
|---|---:|---:|---:|
| Six-task primary passes | 5/6 | 2/6 | 1/6 |
| After same-test repairs | 5/6 | 5/6 | 5/6 |
| Tokens including repairs | 4,785 | 117,619 | 135,580 |
| Tokens per repaired-suite pass | 957.00 | 23,523.80 | 27,116.00 |
| TinyDB hidden milestones accepted | 0/3 | 0/3 | 0/3 |
| TinyDB tokens, lower bound | ≥6,943,953 | ≥8,799,193 | ≥7,076,311 |
| TinyDB unknown token calls | 1 | 1 | 1 |

<!-- historical-results:end -->

The small-task insight is that all arms reached 5/6 after feedback, while the
combined arm used 135,580 tokens versus 4,785 for the baseline. In this setting,
extra workflow steps did not repay their token overhead. The longer-study insight
is that passing public tests still left hidden requirements unmet; public success
alone was an inadequate completion signal. Neither observation measures an
independently labeled hallucination rate or establishes long-term savings.

The six-task experiment used older document-adapted workflows. Its supplemental
repairs received the same tests as feedback, so they are not independent evidence
of an AEE-specific recovery advantage. The TinyDB study used one project and three
dependent milestones per arm. These are observations about those configurations,
not a universal ranking of tools or measurements of the refreshed versions below.

**Hallucination results:** a comparable independently labeled hallucination rate
was not collected in those studies. It is **unmeasured**, not zero. A failing
solution is not automatically a hallucination; false completion requires an
actual completion claim contradicted by independent acceptance evidence.

**Money results:** all arms had $0 local API expenditure. Hardware, energy and
human labor were unpriced. Equal zero API bills do not establish financial savings.

## Where the combined workflow could earn its overhead

Spec Kit supplies requirements, planning and implementation structure. AEE adds
explicit claims, evidence references, uncertainty and recovery routes; Evaluator
provides the common result envelope. These mechanisms can support investigation
and accountability when agents change a project repeatedly or hand it off.
AEE records uncertainty; it does not certify truth or correctness.

The economic hypothesis is: **avoided repair and regression cost must exceed
added planning and assessment cost at comparable quality**. The measurements here
do not establish that break-even point or assign a dollar value to auditability.

## Hallucination and lifecycle reporting

The [prospective protocol](docs/lifecycle-protocol.md) defines common claim
opportunities across arms, independent truth labels, false completion, citation
existence, detector precision/recall, repairs, regressions, paired trajectories
and all-call token economics.

```sh
uv sync --locked --group dev
uv run pytest -q
uv run python scripts/check_pins.py
uv run aee-bench lifecycle-report path/to/campaign.json path/to/report.json
```

The importer produces JSON and Markdown tables. It checks artifact hashes and
source-snapshot binding, retains unknown/missing denominators, and separates actual
API spend from hypothetical price scenarios. It does not label arbitrary prose
automatically or launch a fresh lifecycle study. Its [tests](tests/test_lifecycle.py)
are synthetic fixtures, not efficacy results. Claim-level recovery requires
independently graded before/after snapshots; a flag alone is not a recovered error.

## Historical evidence

**Status: runtime measurements, the six-task exploration and repairs, and the
staged TinyDB comparison are complete.** Read the [measurement index and complete
token ledger](reports/local/README.md), [small-task results](reports/local/gpu-20260917/README.md),
and [longer-project results](reports/local/long-horizon-03/README.md).

The long study produced no complete hidden milestone passes. Final feature coverage
was 21/24 baseline, 5/24 Spec Kit, 3/24 combined; all three arms timed out and have
incomplete exact usage. Six reserved long-study repair attempts were blocked before
inference. The earlier small-task repairs ran and brought all arms to 5/6.
These measurements do not demonstrate a workflow correctness or token-saving advantage.
The original SWE-bench pilot (20 tasks × 3 repetitions × 3 arms) remains unrun.

The controller uses Spec Kit, Evaluator and AEE. Solver treatments are isolated.
The maintenance-triage example is illustrative and is not benchmark evidence.

See `START_HERE.md` for the current handoff and `docs/implementation-brief.md`
for the user-provided requirements. License selection is pending: the organization
has multiple licenses and no organization-wide grant has been established.
Upstream components retain their own notices.

Quickstart: `uv sync --locked --group dev` then `uv run pytest -q`. Python 3.12.6 is pinned.
See [the article draft](docs/linkedin-article.md), [verification](reports/verification.md) and [reproduction](docs/reproduction.md).

## Current controller tooling

Specify CLI **1.2.1**, PyPI distribution `applied-epistemic-engineering` **1.5.3**
(import/CLI `aee`), Spec Kit extension `aee` **1.5.2**, companion `evaluator`
**1.1.2**, mini-SWE-agent **2.4.6**. See [pins](manifests/versions.json).
Historical freezes/results remain unchanged and do not measure this refresh.
Benchmark CI runs on Ubuntu only, as requested.

Ordinary users install the engine with
`python -m pip install applied-epistemic-engineering`, or the integration with
`specify extension add aee`. AEE provisions its
engine/evaluator dependencies. Benchmark reproduction uses exact archive pins;
catalog/trust limitations belong in [reproduction troubleshooting](docs/reproduction.md).

No paid inference is authorized. `scripts/local_feasibility.py` performs one
capped, free loopback readiness request, changing no server configuration.
Readiness is not scored workflow evidence. A fresh efficacy study needs a separate
frozen model/configuration, task inventory, budgets and independent grader preflight.
