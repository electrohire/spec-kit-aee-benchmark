# Requirement-to-evidence matrix

## October controller refresh and lifecycle reporting

- [Current dependency checks](../docs/current-tooling.md): latest public engine,
  Spec Kit extensions and CLI installed; 106 dependencies compatible.
- [Lifecycle contract](../docs/lifecycle-protocol.md) and
  [adversarial importer tests](../tests/test_lifecycle.py): hashed independent
  grades, exact expected-case discovery, false completion, unsupported citations,
  detector denominators, failed/unknown costs, regressions and matched trajectories.
- [Generated README table](../scripts/readme_results.py) checked against historical
  measured summaries in CI. Synthetic tests are not comparative benchmark results.
- [Free readiness probe](feasibility/local-20261016/result.json): one call,
  102 measured input+output tokens, expected identity, $0 API spend. This is not
  complete-workflow calibration or long-term savings evidence.
- [Latest offline run](latest-offline.json) records tests plus actual AEE/evaluator
  composition at specify, plan, tasks and implementation. Their claim judgments
  remain distinct from independent test grades. Initial deliberately unsupported
  composite controller claim received `iterate`; its atomic draft replacements
  retain uncertainty rather than fabricating evidence of efficacy.
- [Focused actual AEE audit](aee-validation/current-20261017-04/summary.json):
  51 tests passed; seven of seven narrow machine observations above threshold,
  zero evidence-verification findings, and one actual AEE result composed by
  Evaluator. Human acceptance remains explicitly absent; overall `iterate` is
  not converted to a fabricated pass.

The [current-version attempt](local/current-study-01/analysis.md) completed all 36
checkpoints; 12final hidden test inventories completed and 24 structured snapshots
failed collection and remain ungraded. Actual AEE coverage was 6/48 planned
checkpoints, all specification. No completed-workflow efficacy benefit follows.
Historical hallucination rates were not annotated and remain unmeasured. The user explicitly
requested Ubuntu-only benchmark CI; no cross-platform coverage is claimed here.


## GPU continuation evidence

- [Measurement index and ledger](local/README.md): 1,001 benchmark-model calls,
  at least 33,983,869 tokens, three unknown native usages, $0 API expenditure.
- [Small exploration and repairs](local/gpu-20260917/README.md): actual model calls,
  separately frozen common repairs, all failures and feedback-exposure limits.
- [Staged TinyDB study](local/long-horizon-03/README.md): frozen inputs and hashes,
  actual isolated tool work, nine primary/final hidden grades, exact test counts,
  source/workflow review, native usage, timeouts and blocked repair rounds.
- [Workflow audit](local/long-horizon-03/workflow-audit.json): actual phases and
  three planning AEE/Evaluator assessments. No implementation assessment or
  evidence-rework run completed. This is not full successful workflow validation.
- [Grade audit](local/long-horizon-03/grade-audit.json): all expected tests discovered;
  all 223 upstream tests pass in every snapshot. No hidden milestone fully passes.
- [Restoration](local/long-horizon-03/service-restoration.json): original local model
  loaded after the owned benchmark server stopped.

Controller deviations: the long supplement reused existing Spec Kit/AEE
infrastructure rather than executing a fresh sequential controller planning cycle.
Two interrupted integration pilots preceded the final freeze; all costs remain.
The user explicitly authorized the changed workload and free local inference.
Constitution 1.2 records that scope after the run; frozen 1.1 bytes remain available.
Public traces omit full requests/native reasoning and cannot reproduce exact prompts.
The original SWE-bench pilot remains unrun; its historical matrix follows.

## Historical offline matrix

Latest command, timestamp, exit status and SHA-256: [latest-offline.json](latest-offline.json).
Its run directory holds append-only assessments, raw and normalized composition,
human-readable reports and immutable objects. All model responses in tests are synthetic.

| Requirements | Evidence | Scope / unresolved gap |
|---|---|---|
| REQ-EXP-001 | manifests/tasks.json; scripts/select_upstream.py; tests/test_experiment.py; reports/dataset-check.txt | Actual upstream 500-task membership, 20 selected; no outcome-based selection |
| REQ-EXP-002 | tests/test_experiment.py and test_workflow.py | Allowlisted args/phase injection; real container audit pending |
| REQ-EXP-003 | tests/test_workflow.py | Actual mini class with mocked provider; real smoke pending |
| REQ-EXP-004 | tests/test_accounting.py and test_experiment.py | Reservations, caps, lock and freeze; live cancellation pending |
| REQ-DATA-001 | tests/test_provider.py and test_accounting.py | Mock HTTP usage, schema, retries and unknowns; real semantics pending |
| REQ-DATA-002 | tests/test_reporting.py | Synthetic economics, clustered repeats, undefined ratios; no pilot data |
| REQ-AEE-001 | reports/offline/ and tests/test_workflow.py | Actual deterministic engine/composition; outcomes iterate; independent grades absent |
| REQ-PUB-001 | docs/, CI and draft PR | Article remains not run |
| REQ-TRIAGE-001 | tests/test_triage.py | CSV fields and sample |
| REQ-TRIAGE-002 | test_validation_preserves_output, test_header_same_path_and_atomic_failure | Missing/duplicate/nonnumeric/nonfinite/negative cases |
| REQ-TRIAGE-003 | test_boundaries_and_order | Both exact thresholds and below-threshold values |
| REQ-TRIAGE-004 | test_boundaries_and_order | Stable sorting, reasons, repeated output bytes |
| REQ-TRIAGE-005 | preservation and simulated replace-failure tests | Input unchanged, old output intact, atomic os.replace |
| REQ-TRIAGE-006 | test_help; examples/maintenance_triage/README.md | Help/sample/installation/acceptance tests |

Test authors and implementation author are not independent. SWE-bench grading is
the independent correctness stream and has not run. AEE assessment is not a grade.
