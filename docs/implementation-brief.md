# Local Codex handoff: ElectroHire Spec Kit + AEE benchmark

Prepared for Tristen Pierson (`tbitcs`). Instruction baseline: 2026-09-17.

## Mission and authority

Execute this project, not merely a proposal. Create a **new public GitHub repository under ElectroHire**, preferably `ElectroHire/spec-kit-aee-benchmark`. The user explicitly intends to share this repository in the LinkedIn article. Develop the benchmark project itself using Spec Kit with the Evaluator and AEE extensions. Compare a coding agent without Spec Kit, the same agent with Spec Kit, and the same agent with Spec Kit + Evaluator + AEE. Reuse existing benchmark tasks and graders. Produce reproducible evidence, token economics, a Python walkthrough, and a LinkedIn article grounded in actual results.

The user authorizes creating the public repository, configuring its metadata, implementing and testing the project, committing and pushing public work, and creating a pull request. Use the already authenticated GitHub account `tbitcs`; do not use browser automation or create another account. Public repository creation and publication of the project files are already authorized; do not ask for that permission again. Posting the article to LinkedIn and submitting leaderboard results remain separate actions and are not requested by this handoff.

Do all work that can proceed with existing access. If model credentials, organization permissions, or a spending limit are genuinely missing, finish the implementation, offline verification, and concrete run plan first. Then ask only for the missing item. Do not ask again for permission to create the repository. Never print credentials or copy them into files.

This document is a handoff, not evidence that a remote repository or benchmark run already exists.

## 1. Create and identify the repository

Use a new directory outside any existing repository. Inspect local `AGENTS.md` instructions. On Windows, prefer WSL2/Linux with Docker integration for the benchmark harness; adapt shell commands deliberately rather than mixing PowerShell and Bash syntax.

Check prerequisites: Git, GitHub CLI, Python 3.11+, uv, Codex CLI, and Docker. Check `gh auth status` without revealing tokens, then:

```bash
gh api user --jq .login
gh api orgs/ElectroHire --jq .login
```

If the active identity is wrong and `tbitcs` is already authenticated, use `gh auth switch --user tbitcs`, then verify again. Preserve the configured Git author identity; do not fabricate an email address.

Check whether the intended repository already exists. Distinguish a real not-found response from an authentication or network error. If an unrelated repository occupies the name, choose `spec-kit-aee-benchmark-2026` after checking it is free. Never overwrite or repurpose an unrelated repository. If resuming this exact project, reuse it.

Create the empty remote:

```bash
gh repo create ElectroHire/spec-kit-aee-benchmark --public \
  --description "Reproducible evaluation of Spec Kit and Applied Epistemic Engineering: coding quality, token usage, and cost per resolved task."
```

Initialize the local project with Spec Kit as described below, ensure Git uses `main`, add the verified remote, commit the bootstrap, and push `main`. Do not run a second `git init` if Specify already initialized it. Add topics using the installed `gh repo edit --help` syntax: `spec-kit`, `aee`, `ai-agents`, `swe-bench`, `benchmark`, `token-economics`, `python`, `reproducibility`. Enable issues, disable an unused wiki, and enable deletion of merged branches.

Add README, `.gitignore`, `.editorconfig`, contribution guidance, security reporting guidance, PR template, and a reproducibility issue template. Follow ElectroHire's existing licensing policy if one is available; otherwise record license selection as pending rather than inventing a license grant. Preserve upstream notices. Configure CI and supported branch protection after check names are established; do not require approval by the PR author's own account or silently claim unavailable protections are enabled. Develop substantive work on `feat/benchmark-harness` and open a draft PR to `main` with actual verification results.

## 2. Install and exercise Spec Kit, Evaluator, and AEE

Read upstream instructions and installed CLI help before executing commands. At this instruction baseline, the documented starting sequence is:

```bash
uv tool install specify-cli
specify init spec-kit-aee-benchmark --integration codex
cd spec-kit-aee-benchmark
python -m venv .venv
source .venv/bin/activate
python -m pip install "applied-epistemic-engineering>=1.0.0,<2"
specify extension add evaluator --from https://github.com/electrohire/spec-kit-evaluator/archive/refs/tags/v1.0.0.zip
specify extension add aee --from https://github.com/electrohire/spec-kit-aee/archive/refs/tags/v1.0.0.zip
specify extension enable evaluator
specify extension enable aee
specify extension list --json
```

Ensure Codex and extension scripts use the environment containing the AEE engine. Inspect installed command/skill registrations and reload Codex if required. Do not assume extension slash-command spelling is identical across integrations. Record the actual names and invoke them. Installation alone is insufficient: retain successful extension execution evidence.

Pin the resolved Specify version, AEE engine version and dependencies, extension commits/archive checksums, model configuration, and benchmark revisions before scored runs. The broad engine version range above is for bootstrap discovery, not the final experiment lock. Do not upgrade dependencies between arms.

Use the installed Spec Kit constitution, specify, clarify when needed, plan, tasks, analyze/checklist when applicable, implement, and convergence workflow to build this project. Discover the exact commands from the generated skills. Persist requirements, plans, tasks, and validation evidence. Require explicit claim IDs, evidence links, falsification criteria, and unresolved gaps in the project constitution.

Use AEE after specification, planning, task decomposition, and implementation. Inspect the installed adapter's help; its documented Python entry point is `.specify/extensions/aee/scripts/python/run_aee.py`. Validate an assessment on a small fixture before automating it. Use the installed templates for claim schema rather than inventing fields. Invoke Evaluator composition/reporting explicitly and record outcome routing. Optional hooks may be skipped; enabling an extension does not prove hooks ran. Do not rely on a reserved `auto_execute_hooks` setting or assume an `after_verify` hook is triggered by a differently named convergence command.

## 3. Separate project governance from experimental treatments

The **controller repository** is always developed with Spec Kit + Evaluator + AEE. That does not mean all benchmark agents receive these instructions.

| Arm | Solver instructions and workflow |
| --- | --- |
| `baseline` | Ordinary capable coding agent, issue text, repository, tools, and tests; no injected Spec Kit/Evaluator/AEE workflow. It may reason and plan naturally. |
| `spec_kit` | Same model and runner, with the frozen Spec Kit workflow. No Evaluator or AEE extension. |
| `spec_kit_aee` | Same model and runner, with the same Spec Kit workflow plus Evaluator and AEE assessment/routing. |

Use fresh sessions and isolated containers or workspaces outside the controller's instruction ancestry. Prevent discovery of controller `AGENTS.md`, controller skills, prior-arm transcripts, sibling workspaces, and assessment outputs. Preserve identical upstream repository instructions for every arm. Mount only what each solver needs. The grading process must be separate from the solver.

Do not automatically load the controller's skills in benchmark sessions. Do not use another model for one arm. If the runner cannot integrate the workflow faithfully, implement and validate a thin adapter before running the experiment. mini-SWE-agent does not become a Spec Kit runner merely because Specify is installed.

The primary three-arm comparison measures the combined Evaluator+AEE treatment. It cannot isolate AEE from Evaluator. Document this limitation; an optional fourth `spec_kit_evaluator` arm is a separately budgeted follow-up.

## 4. Reuse existing benchmark infrastructure

Primary dataset/grader: **SWE-bench Verified**. It provides real issue-to-patch tasks and independent test evaluation. Start with a frozen 20-task Python pilot, three independent repetitions per arm: **180 task attempts**, plus separately identified smoke tests. This is a pilot, not enough to claim universal superiority.

Use SWE-bench's existing loader, patch format, containers, and grading. Consider mini-SWE-agent as the common runner if its telemetry and adapter interface meet the requirements; otherwise use one instrumented Codex runner consistently across all arms while retaining SWE-bench grading. Do not mix Codex and mini-SWE-agent between arms.

Do not rebuild the grader, task collection, or Docker images from scratch when upstream supplies them. Keep upstream clones outside the controller's source tree or use pinned references; avoid vendoring whole repositories. Aider's exercise benchmark is an optional cheaper integration pilot, not a mandatory second benchmark or substitute for repository-level evidence.

Read the pinned SWE-bench documentation. At the current instruction baseline, its v5 evaluation setup includes:

```bash
git clone https://github.com/SWE-bench/SWE-bench.git
cd SWE-bench
python -m pip install -e .
git clone --depth 1 https://github.com/SWE-bench/swe-bench-tasks.git ./swe-bench-tasks
swebench dataset check ./swe-bench-tasks
swebench eval verified --gold -i sympy__sympy-20590 \
  --run-id harness-smoke-gold --task-repo ./swe-bench-tasks
```

Pin commits after cloning. The gold run is only a grader smoke test and must happen outside the solver context. Never give the agent reference patches, hidden test patches, or grader results during the scored attempt. Existing repository tests remain available. Do not use the gold-smoke instance in the scored pilot.

Grade solver predictions using the pinned CLI, for example:

```bash
swebench eval verified -p /absolute/path/predictions.jsonl \
  --run-id UNIQUE_ARM_REPEAT_RUN_ID -j 2
```

Confirm the prediction schema with the installed harness. Give **every changed prediction set a unique run ID**: the documented result cache uses run ID and instance ID rather than patch content. Limit grading to the intended task manifest. Record image identifiers and digests. Docker/storage preflight must precede model spending; upstream recommends substantial disk space, RAM, and CPU resources.

## 5. Freeze a fair experimental protocol

Before any scored generation, commit `protocol.md`, `tasks.json`, `versions.json`, prompts, arm configuration, and cost limits. Record their hashes in every run. Select eligible Python tasks deterministically with a recorded seed and preferably repository stratification. Record inclusion/exclusion rules and all excluded IDs before viewing performance. Do not select only cases where AEE appears useful.

Use identical model snapshot, reasoning setting, sampling settings when supported, tool permissions, hardware class, issue text, initial commit, and per-attempt wall-time/token/dollar ceilings. Count specification, planning, assessment, repair, and finalization against each arm's total limit. AEE may change the allocation of work, but it does not get uncounted extra attempts.

Randomize/interleave arm order to reduce time/load bias. Repeat IDs represent independent runs, not guarantees of deterministic model seeds. Freeze the handling of unresolved ambiguity: use the same task-provided facts and no differential human assistance. Record any intervention as a protocol deviation.

Predefine timeouts, tool errors, infrastructure failures, provider retries, and stopping rules. Do not remove failed attempts from the cost denominator. Retain infrastructure failures separately, and document any uniform rerun rule. Never tune prompts using scored results and then silently replace those results. Use distinct development tasks for adapter tuning.

## 6. Capture token economics from real usage

Implement append-only per-call telemetry and per-attempt outcomes. Required fields include experiment/run/arm/task/repeat IDs; phase; call/request ID; model/provider/version; UTC timestamps; duration; input, cached-input, and output tokens; available reasoning-token details; price snapshot ID; cost basis; currency; retry/error status; and artifact paths/hashes. Redact secrets before persisting raw responses. Unknown usage must be `null` with a reason, never zero.

Verify the runner's usage semantics using a smoke call. Normalize cumulative counters by differencing where needed; do not sum cumulative values as per-call usage. Deduplicate by request/call ID and retain billable retries. Record provider billing if available. Do not estimate billed tokens from transcript length and call them measured.

Where cached tokens are a subset of input and reasoning tokens are already included in output, calculate:

```text
model_cost = ((input_tokens - cached_input_tokens) * input_price_per_million
              + cached_input_tokens * cached_price_per_million
              + output_tokens * output_price_per_million) / 1_000_000
              + separately_billed_tool_fees
```

Validate nonnegative counts and `cached_input_tokens <= input_tokens`. Adapt providers with separate cache-write or other billing categories explicitly. Never double-count reasoning tokens. Pin official dated price sources, service tier, discounts, and currency; report list-price estimates as estimates rather than invoice amounts. Subscription-based Codex usage is not automatically attributable API spend. If exact usage is unavailable, mark the limitation and select an instrumented common runner before claiming token-economics results.

Report for each arm: attempts, resolved count/rate, raw token categories, total model cost, cost per attempted task, **total cost across all attempts / resolved attempts**, latency distribution, repair/tool-call counts, and limit-hit rate. Zero resolved attempts yields undefined/infinite cost per resolved task, never zero. Include paired absolute and percentage differences against baseline and Spec Kit, with undefined ratios handled explicitly. Use task-clustered bootstrap uncertainty so repetitions of the same task are not treated as independent tasks.

Report one-time setup separately from per-task execution. Provide both cold-start and clearly defined amortized economics; charge per-task spec preparation to that arm. Account for all model work triggered by AEE, not just the deterministic engine. Engine execution itself consumes compute/time even when it consumes no model tokens. Report infrastructure and human time separately. Do not manufacture cache savings, success rates, or benchmarks.

## 7. AEE evidence and independent grading

Retain stable requirement/claim IDs, dependency links, assumptions, evidence references, contradictory observations, assessment outcomes, recovery actions, and unresolved gaps. A test command's stdout, exit status, timestamp, and content hash can support a claim only within its actual scope. A model assertion or an agent-written test passing is not independent proof of correctness.

Keep AEE's internal assessment score separate from SWE-bench resolution. Analyze false acceptance (favorable assessment but failed independent grade) and unnecessary blocking (unfavorable assessment but a patch passes). AEE scores are not calibrated probabilities of truth. Do not feed independent held-out grading back into an ongoing scored attempt. Post-run analysis may join the two streams after completion.

## 8. Build a small Python teaching application

Create a maintenance-triage CLI under `examples/maintenance_triage/` for the article. This example illustrates multi-requirement development and is **not** the independent benchmark. Use synthetic data and explicitly illustrative thresholds; do not describe it as a validated maintenance or safety system.

Requirements with stable IDs:

1. Read CSV containing asset ID, vibration in mm/s, and temperature in degrees C.
2. Reject missing fields, duplicate asset IDs, nonnumeric/nonfinite measurements, and negative vibration with useful errors and nonzero exit codes.
3. Flag an asset when vibration is at least 7.1 mm/s or temperature is at least 80 C; include threshold-boundary tests.
4. Produce deterministic JSON ordered by asset ID with explicit flag reasons.
5. Leave input unchanged and write output atomically; failed validation must not damage an existing output.
6. Provide CLI help, sample input/output, installation instructions, and automated acceptance tests.

Create spec, plan, tasks, code, tests, and a requirement-to-evidence table using the actual workflow. Use a dependency-light Python implementation. Measure performance only if a reproducible performance requirement is defined; do not invent throughput claims.

Inspect any existing local user-provided skills before reuse; the prior shared `skills.md` contents were not included in this handoff. Do not claim to have recovered them. For new reusable Codex skills, follow the locally applicable skill-authoring guidance, use the correct `SKILL.md` casing and required metadata, and commit their sources. Keep root `AGENTS.md` concise; use narrowly scoped skills for running experiments, evidence checks, and article generation. Do not let these controller skills contaminate baseline sessions.

## 9. Required repository outputs

Create a maintainable Python package with locked dependencies and documented command entry points. Suggested structure (adapt to conventions without omitting responsibilities):

```text
README.md
AGENTS.md
START_HERE.md
CHANGELOG.md
pyproject.toml
uv.lock
.agents/skills/
.specify/
specs/
configs/arms/
configs/experiment.yaml
manifests/tasks.json
manifests/versions.json
src/benchmark_runner/
tests/
examples/maintenance_triage/
docs/protocol.md
docs/reproduction.md
docs/token-accounting.md
docs/decisions.md
docs/limitations.md
docs/linkedin-article.md
reports/
.github/workflows/ci.yml
```

Provide documented commands for preflight, task selection, dry run, running each arm, grading, aggregation, and article-table generation. Implement them; do not leave pseudocode disguised as an executable runner. Preserve prompts, solver patches, grading results, telemetry, and sanitized transcripts in a manifest-addressed artifact store. Keep credentials, environments, Docker images, large datasets, and raw sensitive logs out of Git. Commit compact summaries, hashes, and retrieval/reproduction instructions. Publish sanitized, redistributable evidence needed to reproduce the article through the public repository or versioned release assets, with checksums. Retain sensitive raw logs locally and disclose any evidence that cannot be distributed. Link upstream datasets with their revisions and licenses instead of copying restricted material. Check staged files and Git history for credentials before the first public push.

CI must test schema validation, cache-token accounting, cumulative usage normalization, failures/retries, zero-success economics, deterministic task selection, isolation, adapter phase execution, and report generation. Use mocked model responses in CI; synthetic fixtures must be labeled. Require a real smoke run before claiming end-to-end integration. Do not automatically launch paid benchmarks on pull requests.

## 10. Execution, budget, and article

Implement a global dollar cap, per-attempt cap, timeout, cancellation, and resumability before paid runs. Resume only matching frozen configurations; never overwrite previous evidence. Use an existing explicit user budget if available. This handoff supplies no dollar ceiling: do not invent permission for unlimited API spending. If none exists, complete the offline project and present a concrete capped smoke/pilot proposal for approval. Do not request API keys in chat; use the local credential mechanism.

After budget and credentials are available, run smoke tests, then the frozen pilot. Make a measured cost projection before any larger study. The default pilot is 180 attempts; expansion to 100–500 tasks is a future decision, not automatic scope.

Draft a LinkedIn article titled approximately **“Does Specification-Driven Development Pay for Itself? Measuring Spec Kit and AEE.”** Include installation and enabling, a short Python walkthrough, real code snippets, how Codex manages reusable skills, the experimental design, actual results and cost tables, limitations, and reproduction links. State ElectroHire's connection to Evaluator/AEE as a conflict-of-interest disclosure. Separate observed results from hypotheses. Explain that SWE-bench evaluates existing-repository repairs, while the app demonstrates greenfield development. A small pilot cannot establish general performance. Discuss public-benchmark contamination as a limitation.

If paid runs are blocked, produce a useful article draft with the results section clearly marked **not run** and omit numeric savings claims. Keep detailed code and transcripts in the repository, with selected excerpts in the article. Do not publish the article automatically.

## 11. Completion and handoff

Before finishing, verify the remote owner is ElectroHire, visibility is PUBLIC, and the repository is accessible without authentication. Verify its URL, branch, pushed commit, PR URL, metadata, CI, installed extension versions, and evidence that the extensions executed. Add the verified public repository URL and commit-pinned code/results links to the LinkedIn article. Report which results are measured, which are synthetic fixtures, and which work remains blocked. Do not call the benchmark complete if only the scaffolding exists.

`START_HERE.md` must let another Codex session resume: goal, current status, exact commands, pinned environment, latest experiment manifest, artifact locations, decisions, unresolved gaps, and next action. Commit this handoff to `docs/implementation-brief.md`. Leave the draft PR reviewable and do not merge automatically.

## Primary references

- [Spec Kit](https://github.com/github/spec-kit) and [extension reference](https://github.com/github/spec-kit/blob/main/docs/reference/extensions.md).
- [ElectroHire Evaluator extension](https://github.com/electrohire/spec-kit-evaluator).
- [ElectroHire AEE extension and engine installation](https://github.com/electrohire/spec-kit-aee).
- [SWE-bench harness and current setup](https://github.com/SWE-bench/SWE-bench).
- [SWE-bench task definitions](https://github.com/SWE-bench/swe-bench-tasks).
- [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent).
- [Aider benchmark instructions](https://github.com/Aider-AI/aider/blob/main/benchmark/README.md).
- [GitHub CLI repository creation](https://cli.github.com/manual/gh_repo_create).
- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing).

Recheck current upstream documentation locally, then freeze the tested versions. Prefer verified installed behavior over stale command examples, and record any deviations from this brief.
