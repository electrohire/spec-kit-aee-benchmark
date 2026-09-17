# Does Specification-Driven Development Pay for Itself? Measuring Spec Kit and AEE
**Draft — benchmark results not run. Do not publish as a completed study.**

A specification workflow costs time and tokens. The useful question is whether
those costs buy more correctly resolved tasks, or less rework. We built a
reproducible experiment to measure that tradeoff rather than assume it.

The public [ElectroHire benchmark repository](https://github.com/electrohire/spec-kit-aee-benchmark)
contains the protocol, task selection, instrumented runner, tests and teaching
example. The experiment compares one model and runner across ordinary coding,
Spec Kit, and Spec Kit plus Evaluator and Applied Epistemic Engineering (AEE).

## What is ready, and what is not
Offline tests exercise accounting, failure handling, isolation arguments, actual
mini-SWE-agent phase execution with synthetic model responses, and deterministic
AEE/Evaluator execution. These are implementation checks, not coding performance.
The scored pilot and real model smoke are **not run**. There is no success-rate
improvement, token saving or cost-saving number to report.

| Treatment | Planned attempts | Scored results | Model cost |
|---|---:|---|---|
| Ordinary agent | 60 | Not run | Not measured |
| Spec Kit | 60 | Not run | Not measured |
| Spec Kit + Evaluator + AEE | 60 | Not run | Not measured |

## Installing the workflow
```bash
uv tool install specify-cli==1.0.0
specify init my-project --integration codex --integration-options=--skills
python -m pip install applied-epistemic-engineering==1.0.2
specify extension add evaluator --from https://github.com/electrohire/spec-kit-evaluator/archive/refs/tags/v1.0.0.zip
specify extension add aee --from https://github.com/electrohire/spec-kit-aee/archive/refs/tags/v1.0.0.zip
specify extension enable evaluator
specify extension enable aee
specify extension list
```
Use Python 3.12 for this pinned Evaluator release. In Codex skills mode the
installed names include $speckit-constitution, $speckit-specify, $speckit-plan,
$speckit-tasks, $speckit-implement and $speckit-converge. We execute AEE explicitly
after the relevant phases and compose/report its outcomes. Installation and hook
registration alone are not evidence that assessments ran.

## A small Python walkthrough
Our maintenance-triage CLI is deliberately simple: read synthetic asset readings,
reject malformed data, flag illustrative threshold crossings, and atomically
write deterministic JSON. Requirements have stable IDs and acceptance tests.
It is not a validated maintenance or safety system.

```python
reasons = []
if vibration >= 7.1:
    reasons.append("vibration_mm_s >= 7.1")
if temperature >= 80:
    reasons.append("temperature_c >= 80")
```

The interesting requirements are at the boundaries: equality must flag, NaN must
fail, duplicate IDs must fail, and validation failure must preserve an existing
output. Those details become claims with falsification tests and evidence links.
A passing test supports its actual scope; it does not prove every claim.
Run it with:
```bash
uv run maintenance-triage examples/maintenance_triage/sample.csv output.json
uv run pytest tests/test_triage.py -q
```

Codex discovers reusable skills through SKILL.md files with name and description
metadata. This repository adds narrow skills for experiments, evidence review and
article drafting. Its root AGENTS.md stays short. Those controller instructions
must never leak into baseline solver sessions.

## The experiment
We selected 20 Python tasks deterministically from the 500-task SWE-bench Verified
set, stratifying by repository before any results. Three independent repetitions
per arm produce 180 attempts. SWE-bench independently grades patches after solvers
finish. The tutorial illustrates greenfield development; SWE-bench measures
repairs to existing repositories. They answer different questions.

Fresh isolated containers and frozen prompts keep treatments separate. All phases,
assessments and repairs count against the same ceilings. The primary three-arm
study measures the combined Evaluator+AEE treatment, not AEE alone.

## Measuring economics honestly
We record provider-native input, cached input and output tokens per request.
Reasoning tokens already included in output are not charged twice. Unknown usage
stays unknown. Failed attempts stay in the denominator:
**cost per resolved task = cost of all attempts / resolved attempts**.
Zero resolutions do not imply zero cost. List-price estimates are not invoices,
and subscription-based Codex usage is not automatically attributable API spend.

The analysis pairs tasks and repetitions and bootstraps task clusters, rather than
pretending repeated runs are independent tasks. Setup, infrastructure and human
time are separate. AEE's internal assessment is compared to the independent grade
only after the attempt ends, including false acceptance and unnecessary blocking.

## Limits and next step
A pilot cannot establish general superiority. Public benchmarks may overlap model
training data. Workflow fidelity and usage semantics still need a real smoke run.
The next step is a capped, authorized smoke, followed by the frozen pilot if its
gates pass. The repository records missing budget, credentials and infrastructure
evidence rather than filling the results table with estimates.

**Disclosure:** ElectroHire maintains the Evaluator/AEE projects being studied.
That connection is a conflict of interest; independent grading, frozen protocols
and public evidence are intended to make the work inspectable.
