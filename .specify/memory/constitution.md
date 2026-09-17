<!-- Sync impact: unfilled template -> 1.0.0. Five principles adopted.
Added experiment constraints and development gates. No template changes required. -->
# ElectroHire Benchmark Constitution

## Core Principles

### I. Claims require evidence
Every substantive claim MUST have a stable ID, source, boundary, falsification
criterion, dependencies and evidence links. Assertions MUST remain distinct from
observations. Unsupported and contradictory claims MUST remain in the gap register.

### II. Treatment isolation
Solvers MUST receive only issue facts, upstream instructions and their frozen
treatment. Controller instructions, sibling attempts and held-out grading MUST be
inaccessible. All arms MUST use one model configuration and runner.

### III. Honest accounting
All model work and failed attempts MUST count. Unknown usage MUST be null with a
reason. Cached tokens MUST not be charged twice. Zero resolutions MUST not imply
zero cost per resolution. Internal AEE scores MUST remain separate from grading.

### IV. Reproducibility before spending
Protocol, revisions, prompts, task selection and limits MUST be frozen before
scored generation. Paid work MUST have explicit user authorization for its cap.
Changes require new run IDs; resumption MUST reject changed configurations.

### V. Independent validation
CI MUST exercise accounting, failures, isolation, phase routing and reports with
labeled fixtures. A real smoke run MUST precede integration claims. SWE-bench
grading MUST run separately after solver completion. The tutorial is illustrative.

## Experiment Constraints
Use the 20-task, three-repeat, three-arm pilot. The combined treatment cannot
isolate Evaluator from AEE. Publish no private source material or credentials.
No LinkedIn posting, leaderboard submission or PR merge is authorized.

## Development Workflow
Apply constitution, specification, plan, tasks, implementation and convergence
in sequence. Run AEE explicitly after specification, plan, tasks and implementation;
compose Evaluator results and record routing. Optional hook registration is not
execution evidence. Use a draft PR and record actual checks and unresolved gaps.

## Governance
Amend through a reviewed commit with rationale and semantic version increment.
Every PR MUST report compliance and deviations. The provided implementation brief
defines scope; this constitution constrains evidence and execution, not user intent.

**Version**: 1.0.0 | **Ratified**: 2026-09-17 | **Last Amended**: 2026-09-17
