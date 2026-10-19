# Tasks: Benchmark

## Phase 1: Setup

* [x] T001 Bootstrap installed skills, constitution and upstream pins.
* [x] T002 Lock package dependencies in pyproject.toml and uv.lock.

## Phase 2: Foundation

* [x] T003 Implement append-only store and accounting in src/benchmark_runner/.
* [x] T004 Test schema, unknowns, cached/cumulative usage and retry reservations.

## Phase 3: US1 — Reproducible experiment

* [x] T005 [US1] Implement selection, freeze, schedule and preflight.
* [x] T006 [US1] Implement isolated common provider runner with cancellation/resume.
* [x] T007 [US1] Execute frozen Spec Kit phases and AEE/Evaluator routing.
* [x] T008 [US1] Delegate grading to pinned SWE-bench with unique run IDs.

## Phase 4: US2 — Audit

* [x] T009 [US2] Implement all-attempt reports, paired cluster bootstrap and tables.
* [x] T010 [US2] Test adapters, isolation, failure/resume and report invariants.

## Phase 5: US3 — Tutorial

* [x] T011 [US3] Build examples/maintenance_triage/ with boundary/error tests.

## Phase 6: Publication

* [x] T012 Add CI, reusable controller skills, reproduction docs and article.
* [x] T013 Publish offline evidence, execute convergence and open draft PR.
* [ ] T014 Run real smoke after budget/credentials/preflight, then frozen pilot.

Dependencies: foundation before US1/US2; tutorial can be developed independently.
MVP: reproducible offline dry-run and correct accounting, followed by integration.
Parallel opportunities: research of upstream harness while controller is specified.
Tests are required by the brief. T014 remains gated; do not check it from mocks.

2026-10-19 stopped-study postmortem exports 36 rows and four independent grader
invocations on two final snapshots. Cachetools collection is incomplete;
TinyDB 225 public passes do not imply hidden acceptance. Full-inventory proxy
unknown 1/ungraded 35, zero scored AEE exposure. T014 and valid paired studies remain
unfinished. No generation, resume, retry or source tuning from hidden outcomes.

2026-10-19: Prospective first-error infrastructure guard and bounded diagnostics
validated with 501 offline cases and 59 focused receipt-bound cases. Actual AEE
and one Evaluator composed iterate; study 02 remains stopped, T014 unfinished.
See the incident's prospective-guard-followup.md for retained failures and limits.


## Established-suite maintenance and release integration (2026-10-19)

* [x] Replace active custom-task maintenance with explicit thin-adapter test inventory; preserve old evidence/tests as opt-in archive.
* [x] Document separate upstream hallucination, coding correctness and all-call economics panels with Mermaid I/O and release diagrams.
* [x] Register prospective practical margins/paired cluster policy; fail closed on incomplete/unmatched/unknown data and absent accepted baseline.
* [x] Implement exact-build request packaging, protected index/hash verification and recomputed release decision; synthetic boundary tests are not empirical improvements.
* [ ] Complete active matched 03 independent grading/audits and publish paired findings.
* [ ] Validate upstream FeatureBench/SWE-EVO graders/resources and frozen candidate adapter, then execute established coding economics.
* [ ] Admit first complete matched product baseline and connect serial local worker execution to queued exact-build requests.
* [ ] Execute a real candidate release comparison and publish approval before any release is allowed.
