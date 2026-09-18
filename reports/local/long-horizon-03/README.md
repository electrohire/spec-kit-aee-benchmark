# Staged TinyDB local study

One real repository, three cumulative milestones, one trajectory per arm. These are dependent checkpoints, not nine independent tasks. Hidden cases were withheld from solver feedback but authored by this study. See the frozen protocol and published response/tool traces.

| Arm | Hidden primary / 3 | Hidden after repairs / 3 | All tokens | Tokens / accepted milestone | Repair rounds | Stage wall seconds |
|---|---:|---:|---:|---:|---:|---:|
| spec_kit | 0 | 0 | at least 8,799,193; 1 unknown call(s) | undefined | 2 (2 blocked by unknown usage) | 2610.7 |
| baseline | 0 | 0 | at least 6,943,953; 1 unknown call(s) | undefined | 0 (0 blocked by unknown usage) | 1667.1 |
| spec_kit_aee | 0 | 0 | at least 7,076,311; 1 unknown call(s) | undefined | 4 (4 blocked by unknown usage) | 1748.7 |

All model phases, failed calls with known usage, and repairs count. API expenditure: $0; hardware, electricity and controller labor unpriced. Functional grading does not prove workflow completion.

| Arm | Stage | Public primary → final | Hidden primary → final | Hidden feature cases final | Regressions | Error |
|---|---:|---|---|---:|---:|---|
| spec_kit | 1 | True → True | False → False | 4/6 | 0 | none |
| spec_kit | 2 | True → True | False → False | 5/8 | 0 | none |
| spec_kit | 3 | False → False | False → False | 5/24 | 0 | TimeoutError: timed out |
| baseline | 1 | True → True | False → False | 4/6 | 0 | none |
| baseline | 2 | True → True | False → False | 6/8 | 0 | none |
| baseline | 3 | True → True | False → False | 21/24 | 0 | TimeoutError: timed out |
| spec_kit_aee | 1 | True → True | False → False | 4/6 | 0 | TimeoutError: timed out |
| spec_kit_aee | 2 | False → False | False → False | 3/8 | 0 | RuntimeError: unknown_usage_stop |
| spec_kit_aee | 3 | False → False | False → False | 3/24 | 0 | RuntimeError: unknown_usage_stop |

## Token and repair accounting

Cached input is included in input, never added again. Values labeled at least exclude calls with unknown native usage. Reservation bounds are configuration limits, not measured usage.

| Arm | Input | Output (includes reasoning) | Cached input | Uncached input | Unknown calls | Total reservation bound |
|---|---:|---:|---:|---:|---:|---:|
| spec_kit | at least 8,729,077 | at least 70,116 | at least 6,519,285 | at least 2,209,792 | 1 | 8,929,681 |
| baseline | at least 6,881,482 | at least 62,471 | at least 6,036,562 | at least 844,920 | 1 | 7,074,750 |
| spec_kit_aee | at least 7,020,360 | at least 55,951 | at least 5,894,715 | at least 1,125,645 | 1 | 7,206,763 |

| Arm | Primary tokens | Repair tokens | Repair rounds with source changes | Hidden milestones fixed by repairs | Evidence-rework rounds |
|---|---:|---:|---:|---:|---:|
| spec_kit | at least 8,799,193 | 0 | 0 | 0 | 0 |
| baseline | at least 6,943,953 | 0 | 0 | 0 | 0 |
| spec_kit_aee | at least 7,076,311 | 0 | 0 | 0 | 0 |

## Inference and context

Native rates use completed calls with returned timing records; HTTP time includes failed calls. HTTP latency is not time to first token. Stage wall time includes tools, preparation, assessment and public grading. Energy is unpriced.

| Arm | Native timing calls | Prompt tokens/s | Decode tokens/s | Median HTTP s | P95 HTTP s | Calls omitting older history | Maximum messages omitted per call |
|---|---:|---:|---:|---:|---:|---:|---:|
| spec_kit | 124 | 1,877.5 | 61.5 | 4.4 | 70.0 | 23 | 38 |
| baseline | 93 | 1,827.4 | 62.9 | 5.8 | 70.9 | 14 | 14 |
| spec_kit_aee | 115 | 1,835.8 | 63.8 | 1.8 | 66.2 | 11 | 42 |

Per-phase and per-stage detail is in `summary.json`; every call remains separately auditable. History omission counts describe each request, not unique lost requirements.

## Evidence and limits

- `summary.json` includes input/output/cache tokens, phase accounting, repairs, tool calls, time, assessment outcomes and stage regressions.
- `results.json` retains every test case and failure, public repair feedback, model phase completions and AEE results.
- Per-arm folders retain generated source snapshots, workflow artifacts, response/usage records and content-addressed shell evidence. Full requests and native reasoning remain local with recorded hashes; exact prompt reconstruction from the public trace is not possible.
- Rework counts refer to explicit public-feedback repair rounds and implementation evidence-rework rounds. Internal debugging remains in phase tokens and shell traces; repeated commands or nonzero exits are not automatically classified as distinct semantic repairs.
- Calibration passed all six test combinations; unchanged upstream failed new features. Smoke is separate and excluded from scored economics.
- A fixed sampling seed is not a guarantee of bitwise deterministic GPU execution. One shuffled run does not remove order effects or establish statistical significance.
- Limited context, call/time ceilings, single-model and adapter behavior constrain interpretation. The previous smaller-model exploration remains separate.
- The combined adapter forwards full composed assessment JSON with nested metadata. Measured token overhead is specific to this adapter, not the minimum intrinsic cost of AEE.
- A 120-second request timeout can interrupt valid slow work. Unknown native usage stops that arm; exact totals remain null, known-call totals are lower bounds, and configured reservation upper bounds are separately labeled rather than imputed as measured usage.
- Two staged pilots and several preliminary smokes exposed integration failures; all costs remain in the separate setup ledger. Run 03 follows a revised full-context freeze. This is iterative benchmark development, not a single pristine preregistered experiment.
- Run 03 freezes workflow scripts/templates and adapter hashes before generation. Run 02 had a disclosed supplemental-provenance limitation; its original evidence remains.
- ElectroHire maintains AEE/Evaluator and the benchmark. No external replication or blinded independent test authorship is claimed.

## Interpretation of this run

All nine hidden milestones failed the strict acceptance rule. Every snapshot passed
all 223 unchanged upstream tests, but every arm missed the retained-handle/cache and
document-ID rollback cases. Final feature coverage was baseline 21/24, Spec Kit
5/24, combined 3/24; related and parameterized cases are not independent answers.
There is no demonstrated correctness or token-saving advantage for the workflow
arms in this study. It does not establish their general effectiveness.

All three arms encountered a 120-second request timeout. Baseline and Spec Kit
reached the third milestone; the combined arm stopped in the first. The unknown
usage rule then prevented further model calls in that arm. Six common repair
attempts were blocked before inference, so this long study contains zero actual
repair model calls. Real supplemental repair results are in the earlier six-task
study; these blocked attempts do not show whether longer-project repairs would work.

The combined arm executed three planning assessments, all `iterate`. It never
reached implementation assessment, evidence rework, convergence, or final
implementation. See `workflow-audit.json` for actual completed phases and tool
activity. Planning findings are not an independent correctness verdict. The
conditional commit/rollback contradiction flag is discussed in
`assessment-interpretation.md`; it is not counted as a confirmed bug caught.

A context/caching example is `baseline/call-081.json`: 124,622 tokens were actually
processed in the prompt stage in 66.145 seconds, before generation. Only 253 input
tokens were reused from cache. Long history can invalidate prefix reuse when older
messages are removed. These adapter and runtime limits materially constrain the
comparison; the passing arithmetic preflight was not a worst-case latency test.

`source-review.md` and `source-archive-integrity.json` record scoped source checks.
The combined source retained seven shadowing TransactionalTinyDB definitions and
six wrapper definitions, a maintainability issue in its interrupted implementation.
No grader/test-discovery bypass was observed in the reviewed changes. This is not
a general security proof. `grade-audit.json` verifies expected test counts and
matching primary/final outcomes. `service-restoration.json` confirms the original
local model service was loaded again after the benchmark server stopped.

Exact measured source bytes and upstream notices are in `frozen-inputs`, indexed by
`frozen-input-map.json`. A reservation upper bound equals known native usage plus
preflight input and the output reservation for each unknown call; it is not an
imputed usage total. Public traces omit native reasoning and full requests, retaining
hashes and all returned usage. Exact historical prompt reconstruction is not possible
from the public trace alone.

Spec Kit stage 2 edited implementation source during the specify phase (call-094.json). Phase labels do not establish faithful semantic execution of every skill.
