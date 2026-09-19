# Feature Specification: Reproducible three-arm benchmark

**Feature Branch**: `feat/benchmark-harness`
**Created**: 2026-09-17
**Status**: Accepted for implementation; paid execution gated
**Input**: `docs/implementation-brief.md` (ZIP explicitly excluded by user).

## User Scenarios & Testing

### User Story 1 — Reproduce an experiment (Priority: P1)
A researcher selects tasks, freezes the protocol and runs isolated attempts within
an approved cap. This is the core deliverable.
**Independent Test**: fixture dry run creates all 180 scheduled entries, refuses
changed freezes on resume, and rejects spending without a cap.
**Acceptance Scenarios**: Given a task manifest, repeated selection with the same
seed produces identical IDs. Given a stopped run, only matching attempts resume.

### User Story 2 — Audit cost and correctness (Priority: P1)
A reviewer joins independent grades to complete usage records and inspects
uncertainty, failures and AEE disagreement. Missing evidence stays visible.
**Independent Test**: known synthetic costs, retries and zero-success inputs
produce expected tables without inventing usage.
**Acceptance Scenarios**: Given cumulative usage, normalization does not overcount.
Given zero resolutions, cost per resolution is undefined. Given unknown usage,
reported total cost remains unknown.

### User Story 3 — Learn through a small application (Priority: P2)
A reader runs a maintenance-triage tutorial and follows requirements to tests.
**Independent Test**: CLI boundary and failure tests exercise all six requirements.
**Acceptance Scenarios**: invalid input preserves existing output; valid shuffled
rows yield deterministic JSON.

### Edge Cases
Timeouts, cancellation, unknown billed retries, stale caches, partial grades,
changed manifests, negative/cached token counts, zero resolutions, duplicate IDs,
nonfinite measurements, same input/output path and insufficient disk.

## Requirements

### Functional Requirements
- **REQ-EXP-001**: Freeze 20 eligible Python tasks, excluding gold/development tasks,
  with seed and repository stratification; schedule three repeats across three arms.
- **REQ-EXP-002**: Isolate fresh solver contexts and separate hidden grading.
- **REQ-EXP-003**: Run one instrumented runner/model with faithful treatment phases.
- **REQ-EXP-004**: Enforce global/per-attempt budgets, timeout, cancellation and resume.
- **REQ-DATA-001**: Append real per-call usage with IDs, timestamps, nullable counts,
  reasons, price basis, retry status and content-addressed artifact references.
- **REQ-DATA-002**: Report all-attempt economics and task-clustered paired uncertainty.
- **REQ-AEE-001**: Preserve explicit claims, evidence, contradictions and routing;
  analyze assessment disagreement only after independent grading.
- **REQ-PUB-001**: Publish tested implementation, pinned reproduction instructions,
  sanitized evidence and an article that labels unrun results.
- **REQ-TRIAGE-001**: Read asset_id,vibration_mm_s,temperature_c CSV fields.
- **REQ-TRIAGE-002**: Reject missing/duplicate IDs, missing/nonnumeric/nonfinite
  measurements and negative vibration with useful nonzero errors.
- **REQ-TRIAGE-003**: Flag vibration >=7.1 or temperature >=80, including equality.
- **REQ-TRIAGE-004**: Emit deterministic JSON ordered by asset ID and explicit reasons.
- **REQ-TRIAGE-005**: Preserve input and atomically replace output only after validation.
- **REQ-TRIAGE-006**: Supply help, samples, installation instructions and acceptance tests.

### Key Entities
Frozen experiment, task, arm, attempt, call, artifact, independent grade, claim.

## Success Criteria
- **SC-001**: All offline acceptance tests pass, with published logs and hashes.
- **SC-002**: Every scheduled attempt appears in reports, including failures.
- **SC-003**: A separate real smoke validates telemetry and isolation before a pilot.
- **SC-004**: Readers can reproduce tutorial output using documented commands.

## Assumptions
Budget and model credentials are not supplied. Offline work proceeds first.
Thresholds are synthetic teaching choices, not maintenance or safety guidance.
Three arms estimate the combined Evaluator+AEE treatment, not AEE alone.
Public benchmark contamination and pilot uncertainty prevent universal conclusions.

## Claim boundaries and falsification
All requirements concern this frozen controller and declared environment. Each is
falsified by a counterexample to its stated behavior. `claims.json` records exact
source refs, dependencies and evidence; unsupported execution claims remain gaps.
