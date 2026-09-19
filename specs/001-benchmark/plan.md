# Implementation Plan: Reproducible benchmark
**Branch**: feat/benchmark-harness | **Date**: 2026-09-17
**Spec**: [spec.md](spec.md)

## Summary
Python controller with an instrumented common coding loop, upstream Docker images,
deterministic treatment phases and independent SWE-bench grading.

## Technical Context
Python >=3.11, stdlib HTTP (no hidden retries), PyYAML, jsonschema, AEE 1.0.2;
pytest and uv.lock. Linux/Docker for live runs; Windows supports offline commands.
Model, dated prices and authorized caps remain unset until run approval.

## Constitution Check
Claims have IDs, boundaries and falsification. Network-disabled, unmounted solver
containers cannot see controller or grading artifacts. Persist conservative
reservations before each request. Unknown charges retain reservations.
No benchmark superiority is claimed. All setup and per-task costs remain separate.

## Project Structure
src/benchmark_runner/: accounting, store, selection, provider, isolation, workflow,
orchestration, grading, reports, CLI. examples/maintenance_triage/: teaching CLI.
tests/: labeled synthetic fixtures. reports/: measured offline checks.

## Phase 0 — Research
See research.md. Stock mini-SWE-agent stops after overspending and hides retries;
use one thin instrumented agent across all arms. Reuse upstream tasks/images/grader.

## Phase 1 — Design
See data-model.md and contracts/cli.md. Inject frozen core skills only into spec
arms. Explicit AEE assessments and bounded recovery use the same model. Keep phase
artifacts outside /testbed so they are excluded from patches. A serialized runner
and experiment lock prevent budget races.

## Verification
Test accounting, schema, reservations, retries, resume, deterministic selection,
container arguments, phase execution, reports and all tutorial requirements.
Real API/Docker smoke remains required; fixtures cannot establish integration.

## Complexity Tracking
Custom runner is justified by pre-request reservations and observable per-call
usage. No grader reimplementation; no credentials inside solver containers.
